from django.db import models


class SelfAuditSettings(models.Model):
    """Plugin settings (a single row)."""

    singleton = models.BooleanField(default=True, unique=True)
    language = models.CharField(max_length=8, default="en")
    datetime_format = models.CharField(max_length=32, default="%d.%m.%Y %H:%M:%S")
    min_severity = models.CharField(max_length=16, default="low")
    default_period = models.CharField(max_length=16, default="today")
    group_by = models.CharField(max_length=16, default="object")
    report_header = models.CharField(max_length=200, blank=True, default="")
    track_system = models.BooleanField(default=True)
    severity_netbox = models.CharField(max_length=16, default="high")
    severity_plugin_added = models.CharField(max_length=16, default="critical")
    severity_plugin_removed = models.CharField(max_length=16, default="critical")
    severity_plugin_version = models.CharField(max_length=16, default="medium")
    # E-mail (like LibreNMS Email Options)
    smtp_host = models.CharField(max_length=255, blank=True, default="")
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_security = models.CharField(max_length=16, default="starttls")
    smtp_username = models.CharField(max_length=255, blank=True, default="")
    smtp_password = models.TextField(blank=True, default="")
    smtp_from = models.CharField(max_length=255, blank=True, default="")
    smtp_from_name = models.CharField(max_length=255, blank=True, default="")
    smtp_timeout = models.PositiveIntegerField(default=10)
    smtp_auto_tls = models.BooleanField(default=False)
    smtp_auth = models.BooleanField(default=False)
    # Scheduled audit e-mail
    audit_email_enabled = models.BooleanField(default=False)
    audit_email_recipients = models.TextField(blank=True, default="")
    audit_email_frequency = models.CharField(max_length=16, default="daily")
    audit_email_weekday = models.PositiveSmallIntegerField(default=0)
    audit_email_time = models.CharField(max_length=5, default="07:00")
    audit_send_empty = models.BooleanField(default=False)
    audit_email_attach_pdf = models.BooleanField(default=True)  # replaced by audit_email_delivery (1.0.6)
    audit_email_delivery = models.CharField(max_length=8, default="pdf")  # "body" or "pdf"
    audit_pdf_password = models.TextField(blank=True, default="")
    last_sent = models.DateTimeField(null=True, blank=True)
    # Heartbeat of the background check (written by every run of the job)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    watchdog_enabled = models.BooleanField(default=True)
    watchdog_minutes = models.PositiveSmallIntegerField(default=10)
    health_endpoint_enabled = models.BooleanField(default=True)
    echo_reply = models.DateTimeField(null=True, blank=True)  # answer of the manual "check now" job
    # NetBox version and plugins seen at the last check
    system_snapshot = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "NetBoxSelf Audit settings"

    @classmethod
    def load(cls):
        settings = cls.objects.first()
        if settings is None:
            settings = cls.objects.create()
        return settings


class SelfAuditRule(models.Model):
    """One watched field (or create/delete event) of one NetBox object type."""

    object_type = models.CharField(max_length=100)  # "app_label.model", e.g. "dcim.device"
    field = models.CharField(max_length=150)  # model field, "cf:<custom field>", "__create__" or "__delete__"
    severity = models.CharField(max_length=16, default="medium")
    message = models.TextField(blank=True, default="")
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("object_type", "field")
        constraints = [
            models.UniqueConstraint(fields=("object_type", "field"), name="netbox_self_audit_rule_unique"),
        ]

    def __str__(self):
        return f"{self.object_type}.{self.field}"


class SelfAuditSystemEvent(models.Model):
    """NetBox version or installed plugin change."""

    time = models.DateTimeField()
    kind = models.CharField(max_length=16)  # "netbox", "plugin_added", "plugin_removed", "plugin_version"
    name = models.CharField(max_length=150, blank=True, default="")
    old = models.CharField(max_length=100, blank=True, default="")
    new = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        ordering = ("-time",)

    def __str__(self):
        return f"{self.kind} {self.name} {self.old} -> {self.new}"
