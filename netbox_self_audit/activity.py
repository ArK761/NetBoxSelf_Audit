"""Activity log of the plugin (who sent which audit to whom, checks, exports, settings changes)."""

from __future__ import annotations

import logging

from .common import seconds
from .i18n import tr

logger = logging.getLogger("netbox.plugins.netbox_self_audit")

# event -> group shown in the filter on the Log page
EVENT_GROUPS = {
    "send_manual": "email", "send_auto": "email", "send_auto_skipped": "email", "send_failed": "email",
    "test_mail": "email", "test_failed": "email",
    "check_ok": "check", "check_failed": "check", "stale_cleared": "check",
    "export": "export",
    "settings_saved": "settings", "email_saved": "settings", "rules_saved": "settings", "rules_deleted": "settings",
}
GROUPS = ("email", "check", "export", "settings")
RETENTION_DAYS = (30, 90, 180, 365)


def record(event: str, ok: bool = True, user=None, **params) -> None:
    """Write a log entry; never breaks the action that is being logged."""
    from django.utils import timezone

    from .models import SelfAuditLog

    try:
        name = ""
        if user is not None and getattr(user, "is_authenticated", False):
            name = user.get_username()
        clean = {key: (value if isinstance(value, (int, float, bool)) or value is None else str(value)) for key, value in params.items()}
        SelfAuditLog.objects.create(time=timezone.now(), user=name, event=event, ok=ok, params=clean)
    except Exception:
        logger.exception("Writing the NetBoxSelf Audit log failed (%s)", event)


def message(entry, lang: str) -> str:
    """Translated text of a log entry."""
    params = {key: ("" if value is None else value) for key, value in (entry.params or {}).items()}
    if isinstance(params.get("seconds"), (int, float)):
        params["seconds"] = seconds(params["seconds"], lang)
    if params.get("delivery") in ("body", "pdf"):
        params["delivery"] = tr(f"form.delivery_{params['delivery']}", lang)
    try:
        return tr(f"log.{entry.event}", lang, **params)
    except (KeyError, IndexError, ValueError):
        return f"{entry.event} {params}"


def cleanup(settings) -> int:
    """Delete entries older than the retention; returns the number deleted."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import SelfAuditLog

    days = int(getattr(settings, "log_retention_days", 180) or 180)
    days = days if days in RETENTION_DAYS else 180
    deleted, _ = SelfAuditLog.objects.filter(time__lt=timezone.now() - timedelta(days=days)).delete()
    return deleted
