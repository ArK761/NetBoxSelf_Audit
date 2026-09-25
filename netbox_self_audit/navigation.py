from django.utils.functional import lazy

from netbox.plugins import PluginMenu, PluginMenuItem


def _menu_label(key: str) -> str:
    """Menu label in the language chosen in the plugin (evaluated at render time)."""
    from .i18n import language_of, tr

    try:
        from .models import SelfAuditSettings

        lang = language_of(SelfAuditSettings.objects.first())
    except Exception:  # database not ready (migrations, startup)
        lang = "en"
    return tr(key, lang)


menu_label = lazy(_menu_label, str)

audit_item = PluginMenuItem(link="plugins:netbox_self_audit:audit", link_text=menu_label("menu.audit"))
rules_item = PluginMenuItem(link="plugins:netbox_self_audit:rules", link_text=menu_label("menu.rules"))
settings_item = PluginMenuItem(link="plugins:netbox_self_audit:settings", link_text=menu_label("menu.settings"))
email_item = PluginMenuItem(link="plugins:netbox_self_audit:email", link_text=menu_label("menu.email"))

menu = PluginMenu(
    label="NetBoxSelf Audit",
    groups=(("NetBoxSelf Audit", (audit_item, rules_item, settings_item, email_item)),),
    icon_class="mdi mdi-shield-search",
)

menu_items = (audit_item, rules_item, settings_item, email_item)
