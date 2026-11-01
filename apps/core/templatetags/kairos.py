from django import template
from django.utils.html import format_html_join

from apps.core.currencies import format_money, format_totals

register = template.Library()


@register.filter
def money(amount, code):
    """{{ lead.estimated_value|money:lead.currency }} → 'PKR 450,000'"""
    return format_money(amount, code)


@register.filter
def totals(value):
    """{{ column.totals|totals }} → 'PKR 450,000 · USD 2,000'"""
    return format_totals(value or {})


@register.simple_tag(takes_context=True)
def nav_active(context, *prefixes):
    """'is-active' when the current URL starts with any of the given prefixes."""
    path = context["request"].path
    return "is-active" if any(path.startswith(p) for p in prefixes) else ""


@register.simple_tag(takes_context=True)
def query_with(context, **changes):
    """Current query string with some parameters replaced (empty value removes)."""
    params = context["request"].GET.copy()
    for key, value in changes.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.filter
def get_item(mapping, key):
    """{{ usage|get_item:item.pk }}"""
    return mapping.get(key) if mapping else None


@register.filter
def totals_lines(text):
    """"PKR 700 · USD 90" with each currency on its own line, so no line ends on a stray dot."""
    if not text:
        return ""
    return format_html_join("", "<span class=\"total-line\">{}</span>", ((part,) for part in str(text).split(" · ")))
