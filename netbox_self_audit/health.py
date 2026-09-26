"""Heartbeat of the background check: is the NetBoxSelf Audit job in netbox-rq still running?"""

from __future__ import annotations

from datetime import timedelta

from .common import format_time
from .i18n import language_of, tr


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
    minutes = max(1, int(getattr(settings, "watchdog_minutes", 10) or 10))
    if now - last > timedelta(minutes=minutes):
        return False, tr("health.stale", lang, time=format_time(last, settings), minutes=minutes)
    return True, tr("health.ok", lang, time=format_time(last, settings))
