import logging

from django.utils import timezone

from netbox.jobs import JobRunner, system_job

from .models import SelfAuditSettings

logger = logging.getLogger("netbox.plugins.netbox_self_audit")


@system_job(interval=1)
class SelfAuditJob(JobRunner):
    """Every minute: record NetBox version / plugin changes and send the scheduled audit e-mail."""

    class Meta:
        name = "NetBoxSelf Audit"

    def run(self, *args, **kwargs):
        from . import mail, rules

        settings = SelfAuditSettings.load()
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
            logger.info("Audit e-mail sent (period %s, %s changes, to %s)", period, result["total"], ", ".join(mail.recipients(settings)))
        else:
            logger.info("Audit e-mail not sent (period %s): %s", period, result.get("reason_en", result["reason"]))
