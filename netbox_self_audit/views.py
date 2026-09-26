import json
from datetime import date, datetime, timedelta
from urllib.parse import quote

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

from . import activity, mail, rules
from .common import SEVERITY_RANK, date_format, format_time, seconds, severities, severity_label
from .health import ECHO_TIMEOUT, check_worker_now, heartbeat_status
from .forms import PERIOD_KEYS, EmailForm, SettingsForm
from .i18n import language_of, tr
from .models import SelfAuditRule, SelfAuditSettings


def _login(request):
    return redirect(f"{reverse('login')}?next={request.path}")


def _render(request, template, context):
    """Render a plugin page with the heartbeat warning (shown when the background check stopped)."""
    settings = SelfAuditSettings.load()
    ok, message = heartbeat_status(settings)
    return render(request, template, {**context, "health_ok": ok, "health_message": message})


def health_view(request):
    """Plain-text status for monitoring (e.g. LibreNMS HTTP service): 200 "OK" or 503 "ERROR". No login needed.

    Can be switched off in Settings; then the address does not exist (404).
    """
    settings = SelfAuditSettings.load()
    if not settings.health_endpoint_enabled or not settings.watchdog_enabled:
        raise Http404
    ok, message = heartbeat_status(settings)
    response = HttpResponse(("OK" if ok else "ERROR") + "\n" + message + "\n", content_type="text/plain; charset=utf-8", status=200 if ok else 503)
    response["Cache-Control"] = "no-store"
    return response


# --------------------------------------------------------------------------
# Watched fields (rules)
# --------------------------------------------------------------------------

def rules_view(request):
    if not request.user.is_authenticated:
        return _login(request)
    settings = SelfAuditSettings.load()
    lang = language_of(settings)
    here = reverse("plugins:netbox_self_audit:rules")

    if request.method == "POST" and request.POST.get("action") == "delete_type":
        key = request.POST.get("type", "")
        deleted, _ = SelfAuditRule.objects.filter(object_type=key).delete()
        messages.success(request, tr("self.deleted", lang, type=rules.type_label(key), count=deleted))
        activity.record("rules_deleted", user=request.user, type=rules.type_label(key), count=deleted)
        return redirect(here)

    if request.method == "POST" and request.POST.get("action") == "rules":
        key = request.POST.get("type", "")
        if rules.model_for(key) is None:
            messages.error(request, tr("self.unknown_type", lang))
            return redirect(here)
        existing = {rule.field: rule for rule in SelfAuditRule.objects.filter(object_type=key)}
        keys = list(rules.EVENTS) + [name for name, _label, _kind in rules.discover_fields(key)]
        watched = 0
        for field in keys:
            rule = existing.get(field)
            if request.POST.get(f"watch__{field}") != "on":
                if rule is not None:
                    rule.delete()
                continue
            severity = request.POST.get(f"sev__{field}", "medium")
            values = {
                "severity": severity if severity in SEVERITY_RANK else "medium",
                "message": (request.POST.get(f"msg__{field}") or "").strip(),
                "enabled": True,
            }
            SelfAuditRule.objects.update_or_create(object_type=key, field=field, defaults=values)
            watched += 1
        messages.success(request, tr("self.rules_saved", lang, type=rules.type_label(key), count=watched))
        activity.record("rules_saved", user=request.user, type=rules.type_label(key), count=watched)
        if request.POST.get("next") == "overview":
            return redirect(here)
        return redirect(f"{here}?type={quote(key)}")

    selected = request.GET.get("type", "")
    rows = []
    if selected and rules.model_for(selected) is not None:
        saved = {rule.field: rule for rule in SelfAuditRule.objects.filter(object_type=selected)}
        sections = [(tr("self.events", lang), [(field, rules.field_label(selected, field, lang), "event") for field in rules.EVENTS])]
        sections.extend(rules.field_sections(selected, lang))
        for title, items in sections:
            if not items:
                continue
            rows.append({"section": title})
            for field, label, kind in items:
                rule = saved.get(field)
                rows.append({
                    "field": field,
                    "label": label,
                    "kind": kind,
                    "watched": rule is not None,
                    "severity": rule.severity if rule else ("high" if kind == "event" else "medium"),
                    "message": rule.message if rule else "",
                    "default": tr(rules.default_message(field), lang),
                    "presets": rules.presets(field, lang),
                })
    elif selected:
        selected = ""

    by_type: dict[str, dict] = {}
    for rule in SelfAuditRule.objects.all():
        by_type.setdefault(rule.object_type, {})[rule.field] = rule
    overview = []
    for key, type_rules in by_type.items():
        order = list(rules.EVENTS) + [name for name, _label, _kind in rules.discover_fields(key)]
        fields = sorted(type_rules, key=lambda field: order.index(field) if field in order else len(order))
        overview.append({
            "key": key,
            "label": rules.type_label(key),
            "count": len(type_rules),
            "rules": [
                {
                    "label": rules.field_label(key, field, lang),
                    "severity": type_rules[field].severity,
                    "severity_label": severity_label(type_rules[field].severity, lang),
                }
                for field in fields
            ],
        })
    overview.sort(key=lambda item: item["label"].lower())
    for item in overview:
        item["confirm"] = tr("self.delete_confirm", lang, type=item["label"])
    return _render(request, "netbox_self_audit/rules.html", {
        "settings": settings,
        "lang": lang,
        "groups": rules.watchable_types(),
        "selected": selected,
        "selected_label": rules.type_label(selected) if selected else "",
        "rows": rows,
        "overview": overview,
        "selected_confirm": tr("self.delete_confirm", lang, type=rules.type_label(selected)) if selected else "",
        "severities": severities(lang),
        "placeholders": ", ".join("{" + name + "}" for name in rules.PLACEHOLDERS),
        "unsaved_text": mark_safe(json.dumps(tr("self.unsaved", lang))),
        "ask_save": mark_safe(json.dumps(tr("self.ask_save", lang))),
        "ask_discard": mark_safe(json.dumps(tr("self.ask_discard", lang))),
        "overview_url": here,
        "samples": mark_safe(json.dumps({
            "user": "admin", "object": "XXXX", "object_type": rules.type_label(selected) if selected else "",
            "old": tr("self.sample_old", lang), "new": tr("self.sample_new", lang), "added": "PC4, PC5", "removed": "PC2",
            "changes": tr("self.chg_value", lang, old=tr("self.sample_old", lang), new=tr("self.sample_new", lang)),
            "action": "update",
        }, ensure_ascii=False)),
        "placeholder_list": list(rules.PLACEHOLDERS),
        "preview_label": mark_safe(json.dumps(tr("self.preview", lang))),
    })


# --------------------------------------------------------------------------
# Audit page
# --------------------------------------------------------------------------

def _default_period(settings) -> str:
    period = getattr(settings, "default_period", "today") or "today"
    return period if period in PERIOD_KEYS else "today"


def _period(request, settings):
    """Return (since, until, label) for the selected period (local time)."""
    period = request.GET.get("period") or _default_period(settings)
    today = timezone.localtime().date()
    day_format = date_format(settings)
    lang = language_of(settings)

    def midnight(day):
        return timezone.make_aware(datetime(day.year, day.month, day.day))

    def parse_day(value):
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    if period == "yesterday":
        day = today - timedelta(days=1)
        return midnight(day), midnight(today), tr("period.yesterday", lang, day=day.strftime(day_format))
    if period == "day":
        day = parse_day(request.GET.get("day")) or today
        return midnight(day), midnight(day + timedelta(days=1)), tr("period.day", lang, day=day.strftime(day_format))
    if period == "range":
        start = parse_day(request.GET.get("from")) or today
        end = parse_day(request.GET.get("to")) or today
        if end < start:
            start, end = end, start
        return midnight(start), midnight(end + timedelta(days=1)), tr("period.range", lang, start=start.strftime(day_format), end=end.strftime(day_format))
    if period == "last7":
        start = today - timedelta(days=6)
        return midnight(start), midnight(today + timedelta(days=1)), tr("period.last7", lang, start=start.strftime(day_format), end=today.strftime(day_format))
    if period == "all":
        return None, None, tr("period.all", lang)
    return midnight(today), midnight(today + timedelta(days=1)), tr("period.today", lang, day=today.strftime(day_format))


def _chosen_recipients(request, settings, lang):
    """Recipients ticked in a send dialog plus additional typed addresses; None (with a message) when invalid."""
    configured = mail.recipients(settings)
    chosen = [address for address in request.POST.getlist("to") if address in configured]
    try:
        extra = mail.parse_addresses(request.POST.get("to_extra", ""))
    except ValueError as exc:
        messages.error(request, tr("ui.invalid_address", lang, address=exc))
        return None
    to = chosen + [address for address in extra if address not in chosen]
    if not to:
        messages.error(request, tr("ui.no_recipient_selected", lang))
        return None
    return to


def audit_view(request):
    if not request.user.is_authenticated:
        return _login(request)
    settings = SelfAuditSettings.load()
    lang = language_of(settings)
    since, until, label = _period(request, settings)
    types = [key for key in request.GET.getlist("type") if key]
    min_severity = request.GET.get("severity") or settings.min_severity
    if min_severity not in SEVERITY_RANK:
        min_severity = "low"
    view = rules.view_of(settings, request.GET.get("view"))
    back = f"{request.path}?{request.GET.urlencode()}"

    if request.method == "POST" and request.POST.get("action") == "check_worker":
        try:
            answered, took = check_worker_now(settings, user=request.user)
        except Exception as exc:
            messages.error(request, tr("check.failed", lang, error=exc))
            activity.record("check_failed", ok=False, user=request.user, error=exc)
            return redirect(back)
        settings.refresh_from_db()
        _ok, last = heartbeat_status(settings)
        if answered:
            messages.success(request, tr("check.ok", lang, time=seconds(took, lang)) + " " + last)
            activity.record("check_ok", user=request.user, seconds=round(took, 2))
        else:
            messages.error(request, tr("check.no_answer", lang, seconds=ECHO_TIMEOUT) + " " + last)
            activity.record("check_failed", ok=False, user=request.user, error=f"no answer within {ECHO_TIMEOUT} s")
        return redirect(back)

    if request.method == "POST" and request.POST.get("action") == "send_email":
        delivery = "body" if request.POST.get("delivery") == "body" else "pdf"
        protect = request.POST.get("pdf_protect") == "on"
        password = (request.POST.get("pdf_password") or settings.audit_pdf_password) if protect else ""
        if delivery == "pdf" and protect and not password:
            messages.error(request, tr("form.err_pdf_password", lang))
            return redirect(back)
        to = _chosen_recipients(request, settings, lang)
        if to is None:
            return redirect(back)
        try:
            result = rules.send_report(
                settings, since, until, label, to=to, force=True, delivery=delivery, pdf_password=password,
                types=types or None, min_severity=min_severity, view=view,
            )
            if result["sent"]:
                messages.success(
                    request,
                    tr("self.sent", lang, period=label, recipients=", ".join(to))
                    + " " + tr("self.took_sentence", lang, time=seconds(result.get("duration", 0), lang)),
                )
                activity.record(
                    "send_manual", user=request.user, recipients=", ".join(to), period=label, delivery=delivery,
                    total=result["total"], seconds=round(result.get("duration", 0), 2),
                )
            else:
                messages.warning(request, result["reason"])
        except Exception as exc:
            messages.error(request, tr("ui.audit_send_failed", lang, error=exc))
            activity.record("send_failed", ok=False, user=request.user, recipients=", ".join(to), period=label, error=exc)
        return redirect(back)

    watched = sorted({rule.object_type for rule in SelfAuditRule.objects.filter(enabled=True)})
    context = {
        "settings": settings,
        "lang": lang,
        "period": request.GET.get("period") or _default_period(settings),
        "day": request.GET.get("day", ""),
        "date_from": request.GET.get("from", ""),
        "date_to": request.GET.get("to", ""),
        "period_label": label,
        "type_choices": [(key, rules.type_label(key)) for key in watched] + [("netbox.system", tr("self.system_type", lang))],
        "selected_types": types,
        "severities": severities(lang),
        "min_severity": min_severity,
        "min_severity_label": severity_label(min_severity, lang),
        "has_rules": bool(watched),
        "generated": "generate" in request.GET or "export" in request.GET,
        "recipients": ", ".join(mail.recipients(settings)),
        "recipient_list": mail.recipients(settings),
        "pdf_password_set": bool(settings.audit_pdf_password),
        "default_delivery": settings.audit_email_delivery,
        "view": view,
    }
    if not context["generated"]:
        return _render(request, "netbox_self_audit/audit.html", context)

    report = rules.build_report(settings, since, until, label, types or None, min_severity)
    context["duration"] = seconds(report["duration"], lang)
    subject, _text, _html = rules.render_report(settings, report, view)
    for entry in report["entries"]:
        entry["when_display"] = format_time(entry["when"], settings)
    export = request.GET.get("export")
    stamp = timezone.localtime().strftime("%Y-%m-%d_%H-%M")
    if export in ("pdf", "html"):
        activity.record("export", user=request.user, format=export.upper(), period=label, total=report["total"])
    if export == "pdf":
        from .pdf import build_pdf

        response = HttpResponse(build_pdf(settings, report, subject, view=view), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="netbox-self-audit_{stamp}.pdf"'
        return response
    if export == "html":
        response = HttpResponse(rules.html_document(settings, report, view), content_type="text/html; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="netbox-self-audit_{stamp}.html"'
        return response

    query = request.GET.copy()
    query.pop("view", None)
    query.pop("export", None)
    context.update({
        "report": report, "subject": subject, "query": request.GET.urlencode(), "base_query": query.urlencode(),
        "tree": rules.group_tree(report["entries"]) if view == "object" else [],
    })
    return _render(request, "netbox_self_audit/audit.html", context)


# --------------------------------------------------------------------------
# Activity log
# --------------------------------------------------------------------------

def log_view(request):
    if not request.user.is_authenticated:
        return _login(request)
    from django.core.paginator import Paginator

    from .models import SelfAuditLog

    settings = SelfAuditSettings.load()
    lang = language_of(settings)
    entries = SelfAuditLog.objects.all()
    group = request.GET.get("group", "")
    if group in activity.GROUPS:
        entries = entries.filter(event__in=[event for event, name in activity.EVENT_GROUPS.items() if name == group])
    result = request.GET.get("result", "")
    if result in ("ok", "error"):
        entries = entries.filter(ok=(result == "ok"))
    for name, lookup in (("from", "time__date__gte"), ("to", "time__date__lte")):
        try:
            entries = entries.filter(**{lookup: date.fromisoformat(request.GET.get(name, ""))})
        except ValueError:
            pass
    page = Paginator(entries, 50).get_page(request.GET.get("page"))
    rows = [
        {
            "time": format_time(entry.time, settings),
            "user": entry.user or tr("log.system", lang),
            "event": tr(f"log_event.{entry.event}", lang),
            "ok": entry.ok,
            "text": activity.message(entry, lang),
        }
        for entry in page.object_list
    ]
    query = request.GET.copy()
    query.pop("page", None)
    return _render(request, "netbox_self_audit/log.html", {
        "lang": lang,
        "rows": rows,
        "page": page,
        "groups": [(key, tr(f"log_group.{key}", lang)) for key in activity.GROUPS],
        "group": group,
        "result": result,
        "date_from": request.GET.get("from", ""),
        "date_to": request.GET.get("to", ""),
        "query": query.urlencode(),
        "retention": settings.log_retention_days,
    })


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

def settings_view(request):
    if not request.user.is_authenticated:
        return _login(request)
    instance = SelfAuditSettings.load()
    if request.method == "POST":
        form = SettingsForm(request.POST, instance=instance)
        if form.is_valid():
            saved = form.save()
            messages.success(request, tr("set.saved", language_of(saved)))
            activity.record("settings_saved", user=request.user, fields=", ".join(form.changed_data) or "-")
            return redirect("plugins:netbox_self_audit:settings")
    else:
        form = SettingsForm(instance=instance)
    return _render(request, "netbox_self_audit/settings.html", {"form": form, "lang": language_of(instance)})


# --------------------------------------------------------------------------
# E-mail settings
# --------------------------------------------------------------------------

def email_view(request):
    if not request.user.is_authenticated:
        return _login(request)
    instance = SelfAuditSettings.load()
    lang = language_of(instance)
    here = reverse("plugins:netbox_self_audit:email")

    if request.method == "POST" and request.POST.get("action") == "test_email":
        to = _chosen_recipients(request, instance, lang)
        if to is None:
            return redirect(here)
        try:
            mail.send_test_email(instance, to=to)
            messages.success(request, tr("ui.test_sent", lang, recipients=", ".join(to)))
            activity.record("test_mail", user=request.user, recipients=", ".join(to))
        except Exception as exc:
            messages.error(request, tr("ui.test_failed", lang, error=exc))
            activity.record("test_failed", ok=False, user=request.user, recipients=", ".join(to), error=exc)
        return redirect(here)

    if request.method == "POST":
        form = EmailForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, tr("ui.email_saved", lang))
            activity.record("email_saved", user=request.user, fields=", ".join(name for name in form.changed_data if "password" not in name) or "-")
            return redirect(here)
    else:
        form = EmailForm(instance=instance)
    return _render(request, "netbox_self_audit/email.html", {
        "form": form,
        "last_sent": format_time(instance.last_sent, instance) if instance.last_sent else "",
        "password_set": bool(instance.smtp_password),
        "recipient_list": mail.recipients(instance),
        "pdf_password_set": bool(instance.audit_pdf_password),
        "lang": lang,
    })
