from django import template

register = template.Library()


@register.filter(name="tr")
def translate(key, lang):
    """{{ "ui.generate"|tr:lang }}"""
    from ..i18n import tr

    return tr(key, lang or "en")


@register.simple_tag
def trf(key, lang, **values):
    """{% trf "ui.changes_count" lang total=report.total %}"""
    from ..i18n import tr

    return tr(key, lang or "en", **values)
