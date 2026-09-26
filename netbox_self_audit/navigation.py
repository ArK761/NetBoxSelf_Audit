from django.utils.functional import lazy

from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem


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


def _item(name: str, label: str, icon: str, color: str) -> PluginMenuItem:
    """Menu item with a small coloured icon button (NetBox does not allow coloured menu text)."""
    link = f"plugins:netbox_self_audit:{name}"
    return PluginMenuItem(
        link=link,
        link_text=menu_label(label),
        buttons=(PluginMenuButton(link=link, title=menu_label(label), icon_class=icon, color=color),),
    )


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
