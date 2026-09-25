"""E-mail delivery (own SMTP settings, independent of NetBox's e-mail configuration) and the schedule."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .common import date_format
from .i18n import language_of, tr


def parse_addresses(raw: str) -> list[str]:
    """Split and validate e-mail addresses; raises ValueError with the first invalid address."""
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    addresses = []
    for address in re.split(r"[,;\s]+", raw or ""):
        address = address.strip()
        if not address:
            continue
        try:
            validate_email(address)
        except ValidationError as exc:
            raise ValueError(address) from exc
        if address not in addresses:
            addresses.append(address)
    return addresses


def recipients(settings) -> list[str]:
    raw = getattr(settings, "audit_email_recipients", "") or ""
    return [address.strip() for address in re.split(r"[,;\s]+", raw) if address.strip()]


def from_address(settings) -> str:
    from email.utils import formataddr

    from django.conf import settings as django_settings

    address = (
        (getattr(settings, "smtp_from", "") or "").strip()
        or getattr(django_settings, "DEFAULT_FROM_EMAIL", "")
        or getattr(django_settings, "SERVER_EMAIL", "")
    )
    name = (getattr(settings, "smtp_from_name", "") or "").strip()
    return formataddr((name, address)) if name and address and "<" not in address else address


def _deliver(settings, message) -> None:
    """Send a Django EmailMessage.

    With an SMTP server configured in the plugin the message is sent directly with
    smtplib (independent of NetBox's own e-mail configuration, which may use Django
    MAILERS); without it, NetBox's default e-mail configuration is used.
    """
    import smtplib
    import ssl
    from email.utils import parseaddr

    host = (getattr(settings, "smtp_host", "") or "").strip()
    if not host:
        message.send(fail_silently=False)
        return

    security = getattr(settings, "smtp_security", "none") or "none"
    port = getattr(settings, "smtp_port", 0) or (465 if security == "ssl" else 587 if security == "starttls" else 25)
    timeout = getattr(settings, "smtp_timeout", 10) or 10
    context = ssl.create_default_context()
    if security == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
    try:
        server.ehlo()
        if security == "starttls" or (
            security == "none" and getattr(settings, "smtp_auto_tls", False) and server.has_extn("starttls")
        ):
            server.starttls(context=context)
            server.ehlo()
        if getattr(settings, "smtp_auth", False) and getattr(settings, "smtp_username", ""):
            server.login(settings.smtp_username, getattr(settings, "smtp_password", "") or "")
        envelope_from = parseaddr(message.from_email)[1] or message.from_email
        # send_message() accepts both the legacy and the modern (Django 6) message classes.
        server.send_message(message.message(), from_addr=envelope_from, to_addrs=message.recipients())
    finally:
        try:
            server.quit()
        except smtplib.SMTPException:
            server.close()


def send_test_email(settings, to: list[str] | None = None) -> None:
    from django.core.mail import EmailMessage
    from django.utils import timezone

    lang = language_of(settings)
    to = to or recipients(settings)
    if not to:
        raise ValueError(tr("mail.no_recipients", lang))
    now = timezone.localtime().strftime(getattr(settings, "datetime_format", "%d.%m.%Y %H:%M:%S"))
    server = (getattr(settings, "smtp_host", "") or "").strip() or tr("mail.netbox_settings", lang)
    body = tr("mail.test_body", lang, time=now, server=server, recipients=", ".join(to))
    message = EmailMessage(subject=tr("mail.test_subject", lang), body=body, from_email=from_address(settings), to=to)
    _deliver(settings, message)


def scheduled_period(settings, now: datetime):
    """Return (slot, since, until, label) when the scheduled audit e-mail is due, else None."""
    from django.utils import timezone

    try:
        hour, minute = (int(part) for part in (settings.audit_email_time or "07:00").split(":", 1))
    except ValueError:
        return None
    local_now = timezone.localtime(now)
    slot = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local_now < slot:
        return None
    last_sent = getattr(settings, "last_sent", None)
    if last_sent is not None and last_sent >= slot:
        return None

    today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_format = date_format(settings)
    frequency = getattr(settings, "audit_email_frequency", "daily") or "daily"
    if frequency == "weekly":
        if local_now.weekday() != (getattr(settings, "audit_email_weekday", 0) or 0):
            return None
        since = timezone.make_aware(datetime.combine((today - timedelta(days=7)).date(), datetime.min.time()))
        last_day = (today - timedelta(days=1)).date()
        return slot, since, today, tr("period.week", language_of(settings), start=since.strftime(day_format), end=last_day.strftime(day_format))
    if frequency == "monthly":
        if local_now.day != 1:
            return None
        previous = (today - timedelta(days=1)).date().replace(day=1)
        since = timezone.make_aware(datetime.combine(previous, datetime.min.time()))
        return slot, since, today, tr("period.month", language_of(settings), month=previous.strftime("%m/%Y"))
    yesterday = (today - timedelta(days=1)).date()
    since = timezone.make_aware(datetime.combine(yesterday, datetime.min.time()))
    return slot, since, today, tr("period.yesterday", language_of(settings), day=yesterday.strftime(day_format))


# --------------------------------------------------------------------------
# Audit generated on demand from the stored configuration history
# --------------------------------------------------------------------------
