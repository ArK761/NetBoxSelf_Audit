from netbox.plugins import PluginConfig


class NetBoxSelfAuditConfig(PluginConfig):
    name = "netbox_self_audit"
    verbose_name = "NetBoxSelf Audit"
    description = "Audit of changes made in NetBox itself: watched fields, severities, PDF and e-mail reports."
    version = "1.0.3"
    base_url = "self-audit"
    min_version = "4.7.0"
    max_version = "4.7.99"
    menu = "navigation.menu"

    def ready(self):
        super().ready()
        from . import jobs  # noqa: F401


config = NetBoxSelfAuditConfig
