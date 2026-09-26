"""Heartbeat of the background check: is the NetBoxSelf Audit job in netbox-rq still running?"""

from __future__ import annotations

from datetime import timedelta

from .common import format_time
from .i18n import language_of, tr


# The job runs every minute, but not to the second: a shorter limit would raise false alarms.
WATCHDOG_MINUTES = (5, 10)
ECHO_TIMEOUT = 15  # seconds to wait for netbox-rq in the manual check


def check_worker_now(settings, user=None) -> tuple[bool, float]:
    """Send a test job to netbox-rq and wait for its answer. Returns (answered, seconds)."""
    import time

    from django.utils import timezone

    from .jobs import SelfAuditEchoJob

    sent = timezone.now()
    started = time.monotonic()
    SelfAuditEchoJob.enqueue(user=user)
    while time.monotonic() - started < ECHO_TIMEOUT:
        settings.refresh_from_db(fields=["echo_reply"])
        if settings.echo_reply and settings.echo_reply >= sent:
            return True, time.monotonic() - started
        time.sleep(0.3)
    return False, time.monotonic() - started


def heartbeat_status(settings, now=None) -> tuple[bool, str]:
    """(ok, message) about the last run of the background job."""
    from django.utils import timezone

    lang = language_of(settings)
    if not getattr(settings, "watchdog_enabled", True):
        return True, tr("health.disabled", lang)
    last = getattr(settings, "last_heartbeat", None)
    if last is None:
        return False, tr("health.never", lang)
    now = now or timezone.now()
    minutes = int(getattr(settings, "watchdog_minutes", 10) or 10)
    minutes = minutes if minutes in WATCHDOG_MINUTES else 10
    if now - last > timedelta(minutes=minutes):
        return False, tr("health.stale", lang, time=format_time(last, settings), minutes=minutes)
    return True, tr("health.ok", lang, time=format_time(last, settings))
