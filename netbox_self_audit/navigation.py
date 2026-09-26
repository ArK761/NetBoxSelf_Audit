from django.utils.functional import lazy
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

from netbox.plugins import PluginMenu, PluginMenuItem


def _menu_label(key: str, icon: str, color: str) -> SafeString:
    """Coloured menu label with an icon, in the language chosen in the plugin (evaluated at render time).

    NetBox renders the menu text with {{ item.link_text }}, so a SafeString is shown as HTML; only our fixed
    markup is marked safe, the translated text itself is escaped.
    """
    from .i18n import language_of, tr

    try:
        from .models import SelfAuditSettings

        lang = language_of(SelfAuditSettings.objects.first())
    except Exception:  # database not ready (migrations, startup)
        lang = "en"
    return mark_safe(f'<span class="text-{color}"><i class="{icon} me-1" aria-hidden="true"></i>{escape(tr(key, lang))}</span>')


menu_label = lazy(_menu_label, SafeString)


def _item(name: str, label: str, icon: str, color: str) -> PluginMenuItem:
    return PluginMenuItem(link=f"plugins:netbox_self_audit:{name}", link_text=menu_label(label, icon, color))


audit_item = _item("audit", "menu.audit", "mdi mdi-file-search-outline", "blue")
rules_item = _item("rules", "menu.rules", "mdi mdi-eye-outline", "orange")
log_item = _item("log", "menu.log", "mdi mdi-history", "red")
settings_item = _item("settings", "menu.settings", "mdi mdi-cog-outline", "green")
email_item = _item("email", "menu.email", "mdi mdi-email-outline", "cyan")

menu_items = (audit_item, rules_item, log_item, settings_item, email_item)

menu = PluginMenu(
    label="NetBoxSelf Audit",
    groups=(("NetBoxSelf Audit", menu_items),),
    icon_class="mdi mdi-shield-search",
)
