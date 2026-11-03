"""The owner's overview: pipeline, clients, follow-ups and money owed."""

from datetime import timedelta

from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from apps.activity import services as activity_services
from apps.clients.models import Client, ClientStatus
from apps.core.currencies import format_totals
from apps.invoices.models import Invoice
from apps.pipeline.models import OPEN_STAGES, Lead, Stage, StageChange

from . import insights

QUIET_DAYS = 21  # an active client with no contact for this long is flagged


def _sum_by_currency(rows):
    totals = {}
    for currency, amount in rows:
        if amount:
            totals[currency] = totals.get(currency, 0) + amount
    return totals


def _ranked(rows, limit=6):
    """[(label, count)] → rows with a bar width (% of the largest), largest first."""
    rows = sorted(((label, n) for label, n in rows if n), key=lambda r: -r[1])
    top = rows[0][1] if rows else 0
    return [{"label": label, "count": n, "pct": round(n * 100 / top) if top else 0} for label, n in rows[:limit]]


def _finding(*parts):
    """The one sentence under the title: what needs the owner today. `parts` are (count, singular, plural)."""
    items = [f"{n} {one if n == 1 else many}" for n, one, many in parts if n]
    if not items:
        return "Nothing needs you right now."
    return (", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else items[0]) + "."


def _stage_parts(stage_counts):
    return [{"key": s.value, "label": Stage(s).label, "count": stage_counts.get(s.value, 0)} for s in OPEN_STAGES]


def _payment_ring(active, today):
    """Active clients by whether their invoices are paid."""
    overdue_ids = set(Invoice.objects.filter(is_paid=False, due_date__lt=today).values_list("client_id", flat=True))
    unpaid_ids = set(Invoice.objects.filter(is_paid=False).values_list("client_id", flat=True))
    counts = {"red": 0, "yellow": 0, "green": 0}
    for pk in active.values_list("pk", flat=True):
        counts["red" if pk in overdue_ids else "yellow" if pk in unpaid_ids else "green"] += 1
    return insights.ring([{"key": "red", "label": "Overdue invoice", "count": counts["red"]},
                          {"key": "yellow", "label": "Invoice unpaid", "count": counts["yellow"]},
                          {"key": "green", "label": "All paid", "count": counts["green"]}])


def dashboard(request):
    now = timezone.now()
    today = timezone.localdate()
    d30, d60, d90 = (now - timedelta(days=n) for n in (30, 60, 90))

    leads = Lead.objects.filter(is_junk=False)
    open_leads = leads.filter(stage__in=OPEN_STAGES)

    new_30 = Lead.objects.filter(created_at__gte=d30).count()
    new_prev = Lead.objects.filter(created_at__gte=d60, created_at__lt=d30).count()
    junk_30 = Lead.objects.filter(created_at__gte=d30, is_junk=True).count()

    # Win rate over the last 90 days: of leads closed in that time, how many were won.
    closed = (StageChange.objects.filter(changed_at__gte=d90, to_stage__in=[Stage.WON, Stage.LOST])
              .values("lead").distinct())
    won_90 = Lead.objects.filter(pk__in=closed, stage=Stage.WON).count()
    lost_90 = Lead.objects.filter(pk__in=closed, stage=Stage.LOST).count()
    win_rate = round(won_90 * 100 / (won_90 + lost_90)) if (won_90 + lost_90) else None

    active = Client.objects.filter(status=ClientStatus.ACTIVE)
    unpaid = Invoice.objects.filter(is_paid=False)
    overdue = unpaid.filter(due_date__lt=today).select_related("client").order_by("due_date")

    by_source = (Lead.objects.filter(created_at__gte=d90, is_junk=False)
                 .values_list("source__name").annotate(n=Count("pk")))
    lost_reasons = (Lead.objects.filter(stage=Stage.LOST, stage_entered_at__gte=d90, lost_reason__isnull=False)
                    .values_list("lost_reason__name").annotate(n=Count("pk")))

    quiet = []
    for client in activity_services.with_last_contact(active).order_by("company"):
        days = activity_services.days_since(client.last_contact_at)
        if days is None:
            # Never contacted: count from when they became a client.
            days = (today - client.start_date).days
        if days >= QUIET_DAYS:
            client.days_quiet = days
            quiet.append(client)
    quiet.sort(key=lambda c: -c.days_quiet)

    buckets = activity_services.follow_up_buckets()
    due_follow_ups = buckets["overdue"] + buckets["today"]

    overdue_count = overdue.count()
    contact_id = request.GET.get("contact", "")
    contact_client = active.filter(pk=contact_id).first() if contact_id.isdigit() else None
    stage_counts = dict(open_leads.values_list("stage").annotate(n=Count("pk")))

    return render(request, "dashboard/dashboard.html", {
        "finding": _finding((overdue_count, "invoice overdue", "invoices overdue"),
                            (len(due_follow_ups), "follow-up due", "follow-ups due"),
                            (len(quiet), "client gone quiet", "clients gone quiet")),
        "money_panels": insights.money_panels(today),
        "funnel": insights.funnel(today),
        "weekly_leads": insights.weekly_leads(today),
        "calendar": insights.activity_calendar(today, client=contact_client),
        "contact_client": contact_client,
        "contact_clients": active.order_by("company"),
        "income_panels": insights.income_shares(),
        "payment_ring": _payment_ring(active, today),
        "stage_ring": insights.ring(_stage_parts(stage_counts)),
        "today": today,
        "pipeline_value": format_totals(_sum_by_currency(open_leads.values_list("currency", "estimated_value"))),
        "open_count": open_leads.count(),
        "hot_count": open_leads.filter(temperature="hot").count(),
        "new_30": new_30,
        "new_delta": new_30 - new_prev,
        "junk_30": junk_30,
        "win_rate": win_rate,
        "won_90": won_90,
        "lost_90": lost_90,
        "active_count": active.count(),
        "monthly_value": format_totals(_sum_by_currency(active.values_list("currency", "monthly_fee"))),
        "unpaid_value": format_totals(_sum_by_currency(unpaid.values_list("currency", "total"))),
        "unpaid_count": unpaid.count(),
        "overdue_count": overdue_count,
        "overdue": overdue[:6],
        "by_source": _ranked(by_source),
        "lost_reasons": _ranked(lost_reasons),
        "due_follow_ups": due_follow_ups[:8],
        "has_overdue_follow_up": bool(buckets["overdue"]),
        "due_follow_ups_more": max(len(due_follow_ups) - 8, 0),
        "upcoming_count": len(buckets["upcoming"]),
        "quiet": quiet[:6],
        "quiet_days": QUIET_DAYS,
        "has_anything": Lead.objects.exists() or Client.objects.exists(),
        "stage_counts": stage_counts,
        "stages": [(s, Stage(s).label) for s in OPEN_STAGES],
    })


def insights_page(request):
    today = timezone.localdate()
    key, first, last = insights.insight_range(request.GET, today)
    return render(request, "dashboard/insights.html", {
        "range_key": key, "first": first, "last": last, "ranges": insights.RANGES,
        "money_panels": insights.money_panels(today),
        "income_panels": insights.income_shares(),
        "source_funnels": insights.source_funnels(first, last),
        "win_loss": insights.win_loss_by_source(first, last),
        "lost_reasons": insights.lost_reason_rows(first, last),
        "durations": insights.stage_durations(first, last),
        "first_contact": insights.first_contact(first, last),
    })
