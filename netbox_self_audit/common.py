"""Severities, choices and formatting shared by the pages, reports and e-mails."""

from __future__ import annotations

from .i18n import tr


SEVERITY_KEYS = ("low", "medium", "high", "critical")
SEVERITY_RANK = {key: rank for rank, key in enumerate(SEVERITY_KEYS)}
SEVERITY_COLOR = {"low": "#6c757d", "medium": "#d39e00", "high": "#fd7e14", "critical": "#dc3545"}

DATETIME_FORMAT_CHOICES = (
    ("%d.%m.%Y %H:%M:%S", "24.09.2026 18:06:06 (EU)"),
    ("%d/%m/%Y %H:%M:%S", "24/09/2026 18:06:06 (EU slash)"),
    ("%Y-%m-%d %H:%M:%S", "2026-09-24 18:06:06 (ISO-like)"),
    ("%d.%m.%Y %H:%M", "24.09.2026 18:06 (EU, no seconds)"),
    ("%Y-%m-%dT%H:%M:%S", "2026-09-24T18:06:06 (ISO 8601)"),
)


def severities(lang: str = "en") -> list[tuple[str, str]]:
    return [(key, tr(f"severity.{key}", lang)) for key in SEVERITY_KEYS]


def severity_label(key: str, lang: str = "en") -> str:
    return tr(f"severity.{key}", lang)


def frequencies(lang: str = "en") -> list[tuple[str, str]]:
    return [(key, tr(f"frequency.{key}", lang)) for key in ("daily", "weekly", "monthly")]


def weekdays(lang: str = "en") -> list[tuple[int, str]]:
    return [(day, tr(f"weekday.{day}", lang)) for day in range(7)]


def delivery_choices(lang: str = "en") -> list[tuple[str, str]]:
    return [("body", tr("form.delivery_body", lang)), ("pdf", tr("form.delivery_pdf", lang))]


def smtp_securities(lang: str = "en") -> list[tuple[str, str]]:
    return [(key, tr(f"security.{key}", lang)) for key in ("none", "ssl", "starttls")]


def format_time(value, settings) -> str:
    from django.utils import timezone

    try:
        return timezone.localtime(value).strftime(getattr(settings, "datetime_format", "") or "%d.%m.%Y %H:%M:%S")
    except (TypeError, ValueError):
        return timezone.localtime(value).strftime("%d.%m.%Y %H:%M:%S")


def date_format(settings) -> str:
    return (getattr(settings, "datetime_format", "") or "%d.%m.%Y").split(" ")[0].split("T")[0]
