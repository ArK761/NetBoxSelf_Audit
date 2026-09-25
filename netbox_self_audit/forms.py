import re

from django import forms
from django.core.validators import validate_email

from .common import DATETIME_FORMAT_CHOICES, frequencies, severities, smtp_securities, weekdays
from .i18n import LANGUAGES, language_of, tr
from .models import SelfAuditSettings


class EmailForm(forms.ModelForm):
    """E-mail delivery of the audit (separate page, similar to LibreNMS Email Options)."""

    # Labels and help texts are set in __init__ in the configured language.
    audit_email_enabled = forms.BooleanField(required=False)
    smtp_from_name = forms.CharField(required=False)
    smtp_from = forms.CharField(required=False)
    smtp_host = forms.CharField(required=False)
    smtp_port = forms.IntegerField(min_value=1, max_value=65535)
    smtp_timeout = forms.IntegerField(min_value=1, max_value=300)
    smtp_security = forms.ChoiceField(choices=smtp_securities())
    smtp_auto_tls = forms.BooleanField(required=False)
    smtp_auth = forms.BooleanField(required=False)
    smtp_username = forms.CharField(required=False)
    smtp_password_input = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
    )
    audit_email_recipients = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "security@example.com, soc@example.com"}),
    )
    audit_email_frequency = forms.ChoiceField(choices=frequencies())
    audit_email_weekday = forms.TypedChoiceField(choices=weekdays(), coerce=int)
    audit_email_time = forms.CharField(widget=forms.TimeInput(attrs={"type": "time"}))
    audit_send_empty = forms.BooleanField(required=False)
    audit_email_attach_pdf = forms.BooleanField(required=False)
    audit_pdf_protect = forms.BooleanField(required=False)
    audit_pdf_password_input = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = SelfAuditSettings
        fields = (
            "smtp_from_name",
            "smtp_from",
            "smtp_host",
            "smtp_port",
            "smtp_timeout",
            "smtp_security",
            "smtp_auto_tls",
            "smtp_auth",
            "smtp_username",
            "audit_email_enabled",
            "audit_email_recipients",
            "audit_email_frequency",
            "audit_email_weekday",
            "audit_email_time",
            "audit_send_empty",
            "audit_email_attach_pdf",
        )

    LABELS = {
        "audit_email_enabled": ("form.enabled", None),
        "smtp_from_name": ("form.from_name", "form.from_name_help"),
        "smtp_from": ("form.from_email", "form.from_email_help"),
        "smtp_host": ("form.smtp_host", "form.smtp_host_help"),
        "smtp_port": ("form.smtp_port", None),
        "smtp_timeout": ("form.smtp_timeout", None),
        "smtp_security": ("form.security", None),
        "smtp_auto_tls": ("form.auto_tls", "form.auto_tls_help"),
        "smtp_auth": ("form.auth", None),
        "smtp_username": ("form.username", None),
        "smtp_password_input": ("form.password", "form.password_help"),
        "audit_email_recipients": ("form.recipients", "form.recipients_help"),
        "audit_email_frequency": ("form.frequency", None),
        "audit_email_weekday": ("form.weekday", None),
        "audit_email_time": ("form.time", "form.time_help"),
        "audit_send_empty": ("form.send_empty", "form.send_empty_help"),
        "audit_email_attach_pdf": ("form.attach_pdf", None),
        "audit_pdf_protect": ("form.pdf_protect", None),
        "audit_pdf_password_input": ("form.pdf_password", "form.pdf_password_help"),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lang = lang = language_of(self.instance)
        for name, (label, help_text) in self.LABELS.items():
            self.fields[name].label = tr(label, lang)
            self.fields[name].help_text = tr(help_text, lang) if help_text else ""
        self.fields["smtp_security"].choices = smtp_securities(lang)
        self.fields["audit_email_frequency"].choices = frequencies(lang)
        self.fields["audit_email_weekday"].choices = weekdays(lang)
        for field in self.fields.values():
            widget = field.widget
            if getattr(widget, "input_type", "") == "checkbox":
                widget.attrs.setdefault("class", "form-check-input")
                widget.attrs.setdefault("role", "switch")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")
        self.order_fields(
            [
                "smtp_from_name",
                "smtp_from",
                "smtp_host",
                "smtp_port",
                "smtp_timeout",
                "smtp_security",
                "smtp_auto_tls",
                "smtp_auth",
                "smtp_username",
                "smtp_password_input",
                "audit_email_enabled",
                "audit_email_recipients",
                "audit_email_frequency",
                "audit_email_weekday",
                "audit_email_time",
                "audit_send_empty",
                "audit_email_attach_pdf",
                "audit_pdf_protect",
                "audit_pdf_password_input",
            ]
        )
        self.fields["audit_pdf_protect"].initial = bool(self.instance.audit_pdf_password)

    def clean_audit_email_recipients(self):
        value = self.cleaned_data.get("audit_email_recipients", "") or ""
        addresses = [address.strip() for address in re.split(r"[,;\s]+", value) if address.strip()]
        for address in addresses:
            try:
                validate_email(address)
            except forms.ValidationError as exc:
                raise forms.ValidationError(tr("form.err_email", self.lang, address=address)) from exc
        if self.cleaned_data.get("audit_email_enabled") and not addresses:
            raise forms.ValidationError(tr("form.err_need_recipient", self.lang))
        return ", ".join(addresses)

    def clean_audit_email_time(self):
        value = (self.cleaned_data.get("audit_email_time") or "").strip()[:5]
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", value):
            raise forms.ValidationError(tr("form.err_time", self.lang))
        return value

    def clean_smtp_from(self):
        value = (self.cleaned_data.get("smtp_from") or "").strip()
        if value:
            try:
                validate_email(value)
            except forms.ValidationError as exc:
                raise forms.ValidationError(tr("form.err_from", self.lang)) from exc
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("audit_pdf_protect") and not cleaned.get("audit_pdf_password_input") and not self.instance.audit_pdf_password:
            self.add_error("audit_pdf_password_input", tr("form.err_pdf_password", self.lang))
        if cleaned.get("smtp_auth") and not (cleaned.get("smtp_username") or "").strip():
            self.add_error("smtp_username", tr("form.err_username", self.lang))
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        password = self.cleaned_data.get("smtp_password_input")
        if password:
            instance.smtp_password = password
        if not instance.smtp_auth:
            instance.smtp_username = ""
            instance.smtp_password = ""
        if not self.cleaned_data.get("audit_pdf_protect"):
            instance.audit_pdf_password = ""
        elif self.cleaned_data.get("audit_pdf_password_input"):
            instance.audit_pdf_password = self.cleaned_data["audit_pdf_password_input"]
        if commit:
            instance.save()
        return instance



PERIOD_KEYS = ("today", "yesterday", "last7")


class SettingsForm(forms.ModelForm):
    """Basic settings: language, formats, report defaults."""

    language = forms.ChoiceField(choices=LANGUAGES)
    datetime_format = forms.ChoiceField(choices=DATETIME_FORMAT_CHOICES)
    min_severity = forms.ChoiceField(choices=severities())
    default_period = forms.ChoiceField(choices=())
    report_header = forms.CharField(required=False, max_length=200)
    track_system = forms.BooleanField(required=False)

    class Meta:
        model = SelfAuditSettings
        fields = ("language", "datetime_format", "min_severity", "default_period", "report_header", "track_system")

    LABELS = {
        "language": ("form.language", None),
        "datetime_format": ("form.datetime_format", None),
        "min_severity": ("form.min_severity", "form.min_severity_help"),
        "default_period": ("form.default_period", None),
        "report_header": ("form.report_header", "form.report_header_help"),
        "track_system": ("form.track_system", "form.track_system_help"),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lang = lang = language_of(self.instance)
        for name, (label, help_text) in self.LABELS.items():
            self.fields[name].label = tr(label, lang)
            self.fields[name].help_text = tr(help_text, lang) if help_text else ""
        self.fields["min_severity"].choices = severities(lang)
        self.fields["default_period"].choices = [(key, tr(f"ui.{key}", lang)) for key in PERIOD_KEYS]
        self.fields["report_header"].widget.attrs["placeholder"] = tr("form.report_header_placeholder", lang)
        for field in self.fields.values():
            widget = field.widget
            if getattr(widget, "input_type", "") == "checkbox":
                widget.attrs.setdefault("class", "form-check-input")
                widget.attrs.setdefault("role", "switch")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")

    def save(self, commit=True):
        instance = super().save(commit=False)
        if "track_system" in self.changed_data and instance.track_system:
            # Start again from the current state: changes made while tracking was off are not reported.
            instance.system_snapshot = {}
        if commit:
            instance.save()
        return instance
