"""The numbers behind the charts. Everything here is plain data; the templates draw it.

Money never adds up across currencies, so each money chart is built once per currency.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from math import ceil, floor, log10

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.activity.models import Activity, ActivityKind
from apps.clients.models import Client, ClientStatus
from apps.core.currencies import format_money
from apps.core.models import AgencySettings
from apps.invoices.models import Invoice
from apps.pipeline.models import OPEN_STAGES, Lead, Stage, StageChange

MONTHS = 12
WEEKS = 12
FUNNEL_DAYS = 90
FUNNEL_STAGES = [*OPEN_STAGES, Stage.WON]
AGE_BUCKETS = (("not_due", "Not due yet"), ("late_30", "1–30 days late"),
               ("late_60", "31–60 days late"), ("late_more", "Over 60 days late"))


def _pct(part, whole):
    return round(float(part) * 100 / float(whole), 1) if whole else 0


def compact(amount):
    """Axis labels: 950, 300K, 1.2M."""
    amount = float(amount)
    for size, suffix in ((1_000_000, "M"), (1_000, "K")):
        if amount >= size:
            value = amount / size
            return f"{value:.0f}{suffix}" if value == int(value) else f"{value:.1f}{suffix}"
    return f"{amount:.0f}"


def nice_ticks(top, intervals=4, whole=False):
    """Round axis steps, with the highest one above `top` so the tallest mark never hits the edge."""
    top = float(top)
    if top <= 0:
        return [0]
    rough = top / intervals
    if whole and rough < 1:
        rough = 1  # counts have no fractions
    magnitude = 10 ** floor(log10(rough))
    multiples = (1, 2, 5, 10) if whole else (1, 2, 2.5, 5, 10)
    step = next(m * magnitude for m in multiples if m * magnitude >= rough)
    return [step * n for n in range(floor(top / step) + 2)]


def month_start(day, back=0):
    index = day.year * 12 + day.month - 1 - back
    return date(index // 12, index % 12 + 1, 1)


def _money_by_month(since):
    """{currency: {month: amount}} for what was billed and what came in, since a date."""
    billed, collected = defaultdict(dict), defaultdict(dict)
    rows = (Invoice.objects.filter(issue_date__gte=since).annotate(month=TruncMonth("issue_date"))
            .values_list("currency", "month").annotate(n=Sum("total")))
    for currency, month, amount in rows:
        billed[currency][month] = amount
    rows = (Invoice.objects.filter(is_paid=True, paid_at__gte=since).annotate(month=TruncMonth("paid_at"))
            .values_list("currency", "month").annotate(n=Sum("total")))
    for currency, month, amount in rows:
        collected[currency][month] = amount
    return billed, collected


def _ageing(today):
    """{currency: {bucket: (amount, count)}} of everything still unpaid."""
    result = defaultdict(lambda: defaultdict(lambda: [Decimal(0), 0]))
    for currency, due, owed in Invoice.objects.filter(is_paid=False).values_list("currency", "due_date", "total"):
        late = (today - due).days
        key = "not_due" if late <= 0 else "late_30" if late <= 30 else "late_60" if late <= 60 else "late_more"
        result[currency][key][0] += owed
        result[currency][key][1] += 1
    return result


def _collection_note(months, code):
    """One sentence on the last three finished months (the current one is still running)."""
    finished = months[-4:-1]
    billed = sum(m["billed"] for m in finished)
    collected = sum(m["collected"] for m in finished)
    if not billed:
        return ""
    span = f"{finished[0]['full']} to {finished[-1]['full']}"
    rate = round(float(collected) * 100 / float(billed))
    if rate >= 100:
        return f"You collected everything you billed from {span}."
    return f"You collected {rate}% of what you billed from {span}."


def money_panels(today=None):
    """One panel per currency in use, the agency's main currency first."""
    today = today or timezone.localdate()
    months = [month_start(today, back) for back in range(MONTHS - 1, -1, -1)]
    billed, collected = _money_by_month(months[0])
    ageing = _ageing(today)
    fees = defaultdict(Decimal)
    for currency, fee in Client.objects.filter(status=ClientStatus.ACTIVE).values_list("currency", "monthly_fee"):
        fees[currency] += fee or 0

    main = AgencySettings.load().default_currency
    used = {main, *billed, *collected, *ageing, *fees}
    panels = []
    for code in sorted(used, key=lambda c: (c != main, -sum(billed[c].values(), Decimal(0)), c)):
        peak = max([*billed[code].values(), *collected[code].values(), Decimal(0)])
        ticks = nice_ticks(peak)
        top = ticks[-1] or 1
        rows = []
        for month in months:
            b, c = billed[code].get(month, Decimal(0)), collected[code].get(month, Decimal(0))
            rows.append({"label": f"{month:%b}", "full": f"{month:%B}", "billed": b, "collected": c,
                         "billed_pct": _pct(b, top), "collected_pct": _pct(c, top),
                         "tip": f"{month:%B %Y}\nBilled {format_money(b, code)}\nCollected {format_money(c, code)}",
                         "current": month == months[-1]})
        buckets = ageing.get(code, {})
        owed = sum((buckets[k][0] for k in buckets), Decimal(0))
        ages = [{"key": key, "label": label, "amount": buckets[key][0], "count": buckets[key][1],
                 "text": format_money(buckets[key][0], code), "pct": _pct(buckets[key][0], owed)}
                for key, label in AGE_BUCKETS if key in buckets]
        panels.append({
            "code": code, "months": rows, "has_money": bool(peak),
            "ticks": [{"label": compact(t), "pct": _pct(t, top)} for t in ticks],
            "recurring": format_money(fees[code], code) if fees[code] else "",
            "collected_now": format_money(rows[-1]["collected"], code),
            "billed_now": format_money(rows[-1]["billed"], code),
            "owed": format_money(owed, code), "owed_amount": owed, "ages": ages,
            "open_count": sum(a["count"] for a in ages),
            "late_count": sum(a["count"] for a in ages if a["key"] != "not_due"),
            "note": _collection_note(rows, code),
        })
    return panels


def ring(parts):
    """Slices for a thin ring drawn with pathLength=100. `parts` are dicts with a `count`."""
    total = sum(p["count"] for p in parts)
    slices, start = [], 0.0
    drawn = [p for p in parts if p["count"]]
    gap = 1.6 if len(drawn) > 1 else 0  # the small break between slices
    for part in drawn:
        size = part["count"] * 100 / total
        slices.append({**part, "dash": round(max(size - gap, .5), 2), "rest": round(100 - max(size - gap, .5), 2),
                       "offset": round(-(start + gap / 2), 2)})
        start += size
    return {"total": total, "slices": slices, "parts": parts}


def funnel(today=None, days=FUNNEL_DAYS):
    """How far the leads that came in lately got: each counts for every stage up to the furthest it reached."""
    today = today or timezone.localdate()
    order = {stage.value: i for i, stage in enumerate(FUNNEL_STAGES)}
    since = timezone.now() - timedelta(days=days)
    furthest = {pk: order.get(stage, 0) for pk, stage in
                Lead.objects.filter(created_at__gte=since, is_junk=False).values_list("pk", "stage")}
    for pk, before, after in (StageChange.objects.filter(lead__in=furthest).values_list("lead", "from_stage", "to_stage")):
        furthest[pk] = max(furthest[pk], order.get(before, 0), order.get(after, 0))

    rows, previous = [], None
    first = len(furthest)
    for stage in FUNNEL_STAGES:
        count = sum(1 for reached in furthest.values() if reached >= order[stage.value])
        rows.append({"key": stage.value, "label": Stage(stage).label, "count": count, "pct": _pct(count, first),
                     "share": round(count * 100 / previous) if previous else None})
        previous = count

    note = ""
    steps = [(a, b) for a, b in zip(rows, rows[1:]) if a["count"] >= 3]
    if steps:
        worst = min(steps, key=lambda s: s[1]["count"] / s[0]["count"])
        note = (f"Biggest drop: only {worst[1]['share']}% of {worst[0]['label']} leads "
                f"reach {worst[1]['label']}.")
    return {"rows": rows, "total": first, "days": days, "note": note}


def week_start(day):
    return day - timedelta(days=day.weekday())


def weekly_leads(today=None, weeks=WEEKS):
    """New leads per week, junk left out, this week last."""
    today = today or timezone.localdate()
    this_week = week_start(today)
    starts = [this_week - timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]
    counts = defaultdict(int)
    since = timezone.now() - timedelta(weeks=weeks + 1)
    for created in Lead.objects.filter(created_at__gte=since, is_junk=False).values_list("created_at", flat=True):
        counts[week_start(timezone.localtime(created).date())] += 1
    ticks = nice_ticks(max([counts[s] for s in starts] + [1]), whole=True)
    top = ticks[-1]
    rows = [{"label": f"{s.day} {s:%b}", "count": counts[s], "pct": _pct(counts[s], top), "current": s == this_week,
             "tip": f"Week of {s.day} {s:%b}\n{counts[s]} new lead{'' if counts[s] == 1 else 's'}"} for s in starts]
    best = max(rows, key=lambda r: r["count"])
    return {"rows": rows, "ticks": [{"label": f"{t:.0f}", "pct": _pct(t, top)} for t in ticks],
            "total": sum(r["count"] for r in rows), "best": best if best["count"] else None}


def activity_calendar(today=None, weeks=WEEKS, client=None):
    """Calls, meetings and messages per day, as week columns for a calendar heatmap."""
    today = today or timezone.localdate()
    first = week_start(today) - timedelta(weeks=weeks - 1)
    rows = Activity.objects.filter(occurred_at__date__gte=first).exclude(kind=ActivityKind.NOTE)
    if client is not None:
        rows = rows.filter(client=client)
    per_day = defaultdict(int)
    for when in rows.values_list("occurred_at", flat=True):
        per_day[timezone.localtime(when).date()] += 1
    peak = max(per_day.values(), default=0)

    columns, last_month = [], None
    for w in range(weeks):
        start = first + timedelta(weeks=w)
        cells = []
        for d in range(7):
            day = start + timedelta(days=d)
            n = per_day[day] if day <= today else None
            level = 0 if not n else ceil(n * 4 / peak)
            tip = "" if n is None else f"{day.day} {day:%b}: {n or 'No'} contact{'' if n == 1 else 's'}"
            cells.append({"count": n, "level": level, "tip": tip, "today": day == today})
        month = f"{start:%b}" if start.month != last_month else ""
        last_month = start.month
        columns.append({"month": month, "cells": cells, "start": start,
                        "total": sum(c["count"] or 0 for c in cells)})

    total = sum(c["total"] for c in columns)
    finished = columns[:-1]  # this week isn't over yet
    quietest = min(finished, key=lambda c: c["total"]) if total and finished else None
    note = ""
    if quietest:
        s = quietest["start"]
        note = f"Quietest week: {s.day} {s:%b}, with {quietest['total']} contact{'' if quietest['total'] == 1 else 's'}."
    return {"columns": columns, "total": total, "note": note, "weeks": weeks}


def income_shares(limit=6):
    """Who the recurring income comes from, per currency, and how much rests on the biggest three."""
    fees = defaultdict(list)
    for client in Client.objects.filter(status=ClientStatus.ACTIVE, monthly_fee__gt=0).order_by("-monthly_fee", "company"):
        fees[client.currency].append(client)
    main = AgencySettings.load().default_currency
    panels = []
    for code in sorted(fees, key=lambda c: (c != main, c)):
        clients = fees[code]
        total = sum(c.monthly_fee for c in clients)
        top = clients[0].monthly_fee
        rows = [{"label": c.company, "url": c.get_absolute_url(), "text": format_money(c.monthly_fee, code),
                 "pct": _pct(c.monthly_fee, top), "share": round(float(c.monthly_fee) * 100 / float(total))}
                for c in clients[:limit]]
        note = ""
        if len(clients) > 3:
            share = round(float(sum(c.monthly_fee for c in clients[:3])) * 100 / float(total))
            note = f"Your three biggest clients bring in {share}% of your {code} income."
        panels.append({"code": code, "rows": rows, "note": note, "total": format_money(total, code),
                       "count": len(clients), "more": max(len(clients) - limit, 0)})
    return panels
