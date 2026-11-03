from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.activity.services import open_follow_ups
from apps.clients.models import Client, ClientStatus, Package
from apps.core.features import FEATURES
from apps.core.models import AgencySettings
from apps.invoices.models import Invoice
from apps.pipeline.models import OPEN_STAGES, Lead

from . import insights

# Most specific first. (path prefix, key, number, band)
SECTIONS = [
    ("/pipeline/", "pipeline", "02", "pipeline"),
    ("/clients/packages/", "packages", "04", "packages"),
    ("/clients/", "clients", "03", "clients"),
    ("/activity/follow-ups/", "follow-ups", "05", "follow-ups"),
    ("/invoices/", "invoices", "06", "today"),
    ("/activity/timeline/", "timeline", "07", "today"),
    ("/insights/", "insights", "08", "pipeline"),
    ("/settings/", "settings", "09", "settings"),
]


def _section(path):
    for prefix, key, number, band in SECTIONS:
        if path.startswith(prefix):
            return {"key": key, "number": number, "band": band}
    return {"key": "today", "number": "01", "band": "today"}


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _summary(key, *, agency, open_leads, pipeline_text, overdue, due_today, overdue_follow_ups):
    """The one live line under each section's title."""
    if key == "pipeline":
        return f"{_plural(open_leads, 'open lead')} · {pipeline_text} in play"
    if key == "clients":
        return f"{Client.objects.filter(status=ClientStatus.ACTIVE).count()} active"
    if key == "packages":
        return _plural(Package.objects.filter(is_active=True).count(), "package")
    if key == "follow-ups":
        return f"{overdue_follow_ups} overdue · {due_today} today"
    if key == "invoices":
        return f"{_plural(overdue, 'overdue invoice')}"
    if key == "settings":
        return agency.name
    return ""


def shell(request):
    """What the status line, rail and block header need on every page."""
    if not request.user.is_authenticated:
        return {}
    today = timezone.localdate()
    agency = AgencySettings.load()
    code = agency.default_currency
    open_leads = Lead.objects.filter(is_junk=False, stage__in=OPEN_STAGES)
    pipeline = open_leads.filter(currency=code).aggregate(s=Sum("estimated_value"))["s"] or Decimal(0)
    pipeline_text = f"{code} {insights.compact(pipeline)}"
    follow_ups = open_follow_ups().filter(due_date__lte=today).values_list("due_date", flat=True)
    due_today = sum(1 for d in follow_ups if d == today)
    overdue_follow_ups = len(follow_ups) - due_today
    overdue = Invoice.objects.filter(is_paid=False, due_date__lt=today).count()
    section = _section(request.path)
    return {
        "features": FEATURES,
        "shell": {
            "today": today,
            "due_today": due_today,
            "overdue_invoices": overdue,
            "pipeline": pipeline_text,
            "section": section,
            "summary": _summary(section["key"], agency=agency, open_leads=open_leads.count(),
                                pipeline_text=pipeline_text, overdue=overdue, due_today=due_today,
                                overdue_follow_ups=overdue_follow_ups),
        },
    }
