"""Timeline and follow-up queries shared by leads, clients and the dashboard."""

from datetime import timedelta

from django.db.models import OuterRef, Q, QuerySet, Subquery
from django.utils import timezone

from .models import CONTACT_KINDS, Activity, FollowUp


def timeline_filter(*, lead=None, client=None) -> Q:
    """
    Which activities/follow-ups belong on a page.

    A client's page also shows everything from the lead it was won from, so
    the sales conversations aren't lost after conversion.
    """
    if client is not None:
        q = Q(client=client)
        if client.lead_id:
            q |= Q(lead_id=client.lead_id)
        return q
    return Q(lead=lead)


def timeline(*, lead=None, client=None) -> QuerySet:
    return (Activity.objects.filter(timeline_filter(lead=lead, client=client))
            .select_related("logged_by", "lead", "client"))


def last_contact(*, lead=None, client=None):
    """When we last actually spoke (call, meeting or message); None if never."""
    return (Activity.objects.filter(timeline_filter(lead=lead, client=client), kind__in=CONTACT_KINDS)
            .order_by("-occurred_at").values_list("occurred_at", flat=True).first())


def days_since(moment):
    if moment is None:
        return None
    return max((timezone.localdate() - timezone.localtime(moment).date()).days, 0)


def with_last_contact(clients: QuerySet) -> QuerySet:
    """Annotate clients with `last_contact_at` (including their lead's history)."""
    latest = (Activity.objects.filter(kind__in=CONTACT_KINDS)
              .filter(Q(client=OuterRef("pk")) | Q(lead=OuterRef("lead_id")))
              .order_by("-occurred_at").values("occurred_at")[:1])
    return clients.annotate(last_contact_at=Subquery(latest))


def with_next_follow_up(clients: QuerySet) -> QuerySet:
    """Annotate clients with `next_follow_up` (earliest open due date)."""
    soonest = (FollowUp.objects.filter(done_at__isnull=True)
               .filter(Q(client=OuterRef("pk")) | Q(lead=OuterRef("lead_id")))
               .order_by("due_date").values("due_date")[:1])
    return clients.annotate(next_follow_up=Subquery(soonest))


def open_follow_ups() -> QuerySet:
    return (FollowUp.objects.filter(done_at__isnull=True)
            .select_related("lead", "client", "lead__client"))


def follow_up_buckets(upcoming_days: int = 7) -> dict:
    """Open follow-ups split into overdue / today / upcoming, plus recently done."""
    today = timezone.localdate()
    qs = open_follow_ups()
    return {
        "overdue": list(qs.filter(due_date__lt=today)),
        "today": list(qs.filter(due_date=today)),
        "upcoming": list(qs.filter(due_date__gt=today, due_date__lte=today + timedelta(days=upcoming_days))),
        "later": qs.filter(due_date__gt=today + timedelta(days=upcoming_days)).count(),
        "done": list(FollowUp.objects.filter(done_at__gte=timezone.now() - timedelta(days=7))
                     .select_related("lead", "client").order_by("-done_at")[:20]),
    }
