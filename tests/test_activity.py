"""Timeline entries, days since last contact and follow-ups."""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.activity import services
from apps.activity.models import Activity, FollowUp

pytestmark = pytest.mark.django_db


def test_activity_must_link_to_exactly_one(make_lead, make_client):
    lead, client = make_lead("A"), make_client()
    with pytest.raises(ValidationError):
        Activity(summary="x").full_clean()
    with pytest.raises(ValidationError):
        Activity(lead=lead, client=client, summary="x").full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():  # the database enforces it too
        Activity.objects.create(lead=lead, client=client, summary="x")


def test_log_activity_with_follow_up(client_in, make_lead):
    lead = make_lead("A")
    when = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
    due = (timezone.localdate() + timedelta(days=3)).isoformat()
    res = client_in.post(f"/activity/lead/{lead.pk}/log/", {
        "kind": "call", "channel": "whatsapp", "contact_name": "Matthew Murdock", "occurred_at": when,
        "summary": "Talked about the Growth package", "follow_up_date": due, "follow_up_note": "",
    })
    assert res.url == f"{lead.get_absolute_url()}#timeline"
    a = Activity.objects.get()
    assert (a.lead, a.kind, a.channel) == (lead, "call", "whatsapp")
    f = FollowUp.objects.get()
    assert f.lead == lead and f.note == "Follow up after call"


def test_future_activity_rejected(client_in, make_lead):
    lead = make_lead("A")
    later = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    client_in.post(f"/activity/lead/{lead.pk}/log/", {"kind": "call", "occurred_at": later, "summary": "x"})
    assert not Activity.objects.exists()


def test_empty_summary_rejected(client_in, make_client):
    c = make_client()
    client_in.post(f"/activity/client/{c.pk}/log/", {"kind": "note", "occurred_at": "2026-01-01T10:00", "summary": ""})
    assert not Activity.objects.exists()


def test_unknown_subject_kind_404(client_in):
    assert client_in.post("/activity/nope/1/log/", {}).status_code == 404


def test_edit_and_delete_activity(client_in, make_lead):
    lead = make_lead("A")
    a = Activity.objects.create(lead=lead, kind="call", summary="old")
    client_in.post(f"/activity/timeline/{a.pk}/", {"kind": "meeting", "occurred_at": "2026-01-02T09:30", "summary": "new"})
    a.refresh_from_db()
    assert (a.kind, a.summary) == ("meeting", "new")
    client_in.post(f"/activity/timeline/{a.pk}/", {"delete": "1"})
    assert not Activity.objects.exists()


def test_last_contact_ignores_notes(make_lead):
    lead = make_lead("A")
    now = timezone.now()
    Activity.objects.create(lead=lead, kind="call", summary="c", occurred_at=now - timedelta(days=5))
    Activity.objects.create(lead=lead, kind="note", summary="n", occurred_at=now)
    assert services.days_since(services.last_contact(lead=lead)) == 5


def test_client_list_last_contact_annotation(make_lead, make_client):
    from apps.clients.models import Client
    lead = make_lead("L")
    client = make_client(lead=lead)
    other = make_client("Other")
    Activity.objects.create(lead=lead, kind="message", summary="m", occurred_at=timezone.now() - timedelta(days=9))
    rows = {c.pk: c.last_contact_at for c in services.with_last_contact(Client.objects.all())}
    assert services.days_since(rows[client.pk]) == 9
    assert rows[other.pk] is None  # other clients' lead-less history isn't mixed in


def test_follow_up_buckets(make_lead):
    lead = make_lead("A")
    today = timezone.localdate()
    FollowUp.objects.create(lead=lead, due_date=today - timedelta(days=2), note="late")
    FollowUp.objects.create(lead=lead, due_date=today, note="now")
    FollowUp.objects.create(lead=lead, due_date=today + timedelta(days=3), note="soon")
    FollowUp.objects.create(lead=lead, due_date=today + timedelta(days=30), note="later")
    FollowUp.objects.create(lead=lead, due_date=today, note="finished", done_at=timezone.now())
    b = services.follow_up_buckets()
    assert [f.note for f in b["overdue"]] == ["late"]
    assert [f.note for f in b["today"]] == ["now"]
    assert [f.note for f in b["upcoming"]] == ["soon"]
    assert b["later"] == 1 and [f.note for f in b["done"]] == ["finished"]


def test_follow_up_add_done_undo(client_in, make_client):
    c = make_client()
    due = timezone.localdate().isoformat()
    client_in.post(f"/activity/client/{c.pk}/follow-up/", {"due_date": due, "note": "Send report"})
    f = FollowUp.objects.get()
    client_in.post(f"/activity/follow-ups/{f.pk}/done/", {"done": "1"})
    f.refresh_from_db()
    assert f.is_done
    client_in.post(f"/activity/follow-ups/{f.pk}/done/", {"done": "0"})
    f.refresh_from_db()
    assert not f.is_done


def test_follow_up_in_past_rejected(client_in, make_client):
    c = make_client()
    client_in.post(f"/activity/client/{c.pk}/follow-up/",
                   {"due_date": (timezone.localdate() - timedelta(days=1)).isoformat(), "note": "x"})
    assert not FollowUp.objects.exists()


def test_follow_up_page_and_sidebar_badge(client_in, make_lead):
    lead = make_lead("Glowy")
    FollowUp.objects.create(lead=lead, due_date=timezone.localdate() - timedelta(days=1), note="Chase proposal")
    res = client_in.get("/activity/follow-ups/")
    html = res.content.decode()
    assert "Chase proposal" in html and "Overdue" in html
    assert res.context["follow_ups_due"] == 1


def test_follow_up_done_redirect_is_safe(client_in, make_lead):
    f = FollowUp.objects.create(lead=make_lead("A"), due_date=timezone.localdate(), note="x")
    res = client_in.post(f"/activity/follow-ups/{f.pk}/done/", {"done": "1", "next": "//evil.example"})
    assert not res.url.startswith("//")
