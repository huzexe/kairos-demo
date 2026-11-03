from django import template
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join

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


@register.simple_tag
def icon(name, size=""):
    """{% icon "pipeline" %} → the icon from the sprite. Size is "16" or "24"; the default is 20."""
    size_class = f" i-{size}" if size else ""
    return format_html('<svg class="i{}" aria-hidden="true"><use href="{}#{}"/></svg>',
                       size_class, static("icons/sprite.svg"), name)


SOURCE_ICONS = {"Instagram": "instagram", "Referral": "referral", "Paid Ads": "ads",
                "Cold Outreach": "outreach", "Hot Outreach": "outreach"}


@register.filter
def source_icon(name):
    """The icon for a default lead source; any source the owner adds gets a generic one."""
    return SOURCE_ICONS.get(name, "source")


KIND_ICONS = {"call": "call", "meeting": "meeting", "message": "message", "note": "note"}


@register.filter
def kind_icon(kind):
    """The timeline marker for a call, meeting, message or note."""
    return KIND_ICONS.get(kind, "other")


AGE_WARN_DAYS = 7
AGE_DANGER_DAYS = 14
AGE_FULL_DAYS = 21


@register.inclusion_tag("includes/ageing.html")
def ageing_bar(days):
    """The thin bar on a lead card: fills with days in stage, then turns warn and danger."""
    days = days or 0
    tone = "is-danger" if days >= AGE_DANGER_DAYS else "is-warn" if days >= AGE_WARN_DAYS else ""
    return {"days": days, "tone": tone, "fill": min(round(days * 100 / AGE_FULL_DAYS), 100)}


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
