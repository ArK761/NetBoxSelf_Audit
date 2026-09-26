import logging

from django.utils import timezone

from netbox.jobs import JobRunner, system_job

from .models import SelfAuditSettings

logger = logging.getLogger("netbox.plugins.netbox_self_audit")

# A run takes seconds; a job still "running" (or overdue) after this long was interrupted,
# e.g. by a restart of netbox-rq, and would block NetBox from scheduling the job again.
STALE_AFTER_MINUTES = 10


@system_job(interval=1)
class SelfAuditJob(JobRunner):
    """Every minute: record NetBox version / plugin changes and send the scheduled audit e-mail."""

    class Meta:
        name = "NetBoxSelf Audit"

    @classmethod
    def clear_stale_jobs(cls, instance=None) -> int:
        """Mark interrupted runs as errored so that a new run can be scheduled. Returns the number of jobs."""
        from datetime import timedelta

        from django.db.models import Q

        now = timezone.now()
        limit = now - timedelta(minutes=STALE_AFTER_MINUTES)
        stale = cls.get_jobs(instance).filter(
            Q(status="running", started__lt=limit)
            | Q(status="running", started__isnull=True, created__lt=limit)
            | Q(status__in=("pending", "scheduled"), scheduled__lt=limit)
        )
        count = stale.update(status="errored", completed=now, error="Interrupted run (e.g. netbox-rq restart), cleared by NetBoxSelf Audit")
        if count:
            logger.warning("Cleared %s interrupted NetBoxSelf Audit job(s)", count)
        return count

    @classmethod
    def enqueue_once(cls, instance=None, schedule_at=None, interval=None, *args, **kwargs):
        # Called by NetBox when netbox-rq starts: an interrupted run must not block the schedule.
        try:
            cls.clear_stale_jobs(instance)
        except Exception:
            logger.exception("Clearing interrupted NetBoxSelf Audit jobs failed")
        return super().enqueue_once(instance, schedule_at, interval, *args, **kwargs)

    def run(self, *args, **kwargs):
        from . import mail, rules

        settings = SelfAuditSettings.load()
        # Heartbeat first, so that an error in a later step does not look like a stopped background check.
        settings.last_heartbeat = timezone.now()
        settings.save(update_fields=["last_heartbeat"])
        if settings.track_system:
            try:
                recorded = rules.check_system(settings)
                if recorded:
                    logger.info("NetBox version / plugin change recorded (%s events)", recorded)
            except Exception:
                logger.exception("NetBox version / plugin check failed")

        if not settings.audit_email_enabled or not mail.recipients(settings):
            return
        due = mail.scheduled_period(settings, timezone.now())
        if due is None:
            return
        slot, since, until, label = due
        period = f"{since.isoformat(timespec='minutes')}..{until.isoformat(timespec='minutes')}"
        # Mark the slot first so that a slow or failing SMTP server does not
        # cause the same audit to be sent again every minute.
        settings.last_sent = slot
        settings.save(update_fields=["last_sent"])
        try:
            result = rules.send_report(settings, since, until, label)
        except Exception:
            logger.exception("Audit e-mail failed (period %s)", period)
            return
        if result["sent"]:
            logger.info(
                "Audit e-mail sent (period %s, %s changes, to %s, took %.1f s)",
                period, result["total"], ", ".join(mail.recipients(settings)), result.get("duration", 0),
            )
        else:
            logger.info("Audit e-mail not sent (period %s): %s", period, result.get("reason_en", result["reason"]))
