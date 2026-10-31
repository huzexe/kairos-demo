"""Bugs found in the review after phase 2. Each test failed before its fix."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.activity.models import Activity, FollowUp
from apps.clients.models import Client

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("evil", ["/\\evil.example", "//evil.example", "https://evil.example", "/\\/evil.example"])
def test_no_open_redirects(client_in, make_lead, evil):
    """'/\\evil.example' starts with '/' but browsers treat it like '//evil.example'."""
    lead = make_lead("A")
    res = client_in.post(f"/pipeline/leads/{lead.pk}/junk/", {"junk": "1", "next": evil})
    assert res.url == lead.get_absolute_url()
    res = client_in.post("/pipeline/leads/bulk/", {"ids": [lead.pk], "action": "restore", "next": evil})
    assert res.url == "/pipeline/list/"
    f = FollowUp.objects.create(lead=lead, due_date=timezone.localdate(), note="x")
    res = client_in.post(f"/activity/follow-ups/{f.pk}/done/", {"done": "1", "next": evil})
    assert res.url.startswith(lead.get_absolute_url())


def test_junk_leads_follow_ups_are_not_due(client_in, make_lead):
    """Junking a lead hides it everywhere — its follow-ups shouldn't keep nagging."""
    lead = make_lead("Spam")
    FollowUp.objects.create(lead=lead, due_date=timezone.localdate(), note="Call back")
    lead.is_junk = True
    lead.save()
    res = client_in.get("/activity/follow-ups/")
    assert res.context["follow_ups_due"] == 0
    assert "Call back" not in res.content.decode()
    assert client_in.get("/").context["due_follow_ups"] == []


def test_package_price_in_other_currency_not_used_for_invoice(client_in, make_client, package):
    """A PKR package must not put a PKR price on a USD client's invoice."""
    c = make_client(currency="USD", package=package)  # package is PKR 80,000, no fee set
    first = client_in.get(f"/invoices/new/?client={c.pk}").context["lines"].forms[0]
    assert first.initial.get("unit_price") is None
    assert first.initial["description"].startswith("Growth package")


@pytest.mark.parametrize("company, prefix", [("Glow/Skin", "PS/"), ("مہک بیوٹی", "INV-"), ('Q"uote', "INV-")])
def test_pdf_filename_is_safe(client_in, make_client, company, prefix):
    from apps.core.models import AgencySettings
    from apps.invoices.models import Invoice
    agency = AgencySettings.load()
    agency.invoice_prefix = prefix
    agency.save()
    c = make_client(company)
    inv = Invoice.objects.create(number=f"{prefix}0001", client=c, currency="PKR", due_date=timezone.localdate())
    disposition = client_in.get(f"/invoices/{inv.pk}/pdf/")["Content-Disposition"]
    filename = disposition.split("filename=", 1)[1]
    assert disposition.isascii() and "/" not in filename and filename.count('"') == 2


def test_setup_cannot_create_second_owner(client, owner):
    res = client.post("/setup/", {"agency_name": "X", "default_currency": "USD", "timezone": "UTC",
                                  "username": "second", "password1": "Brand-new-pass-9",
                                  "password2": "Brand-new-pass-9"})
    assert res.status_code == 302 and get_user_model().objects.count() == 1


def test_editing_lead_history_on_client_page_returns_to_client(client_in, make_lead):
    from apps.clients import services
    lead = make_lead("A", stage="won")
    a = Activity.objects.create(lead=lead, kind="call", summary="sales call")
    client = services.convert_lead(lead, Client(company="A Co", currency="PKR"))
    res = client_in.post(f"/activity/timeline/{a.pk}/", {"kind": "call", "occurred_at": "2026-01-01T10:00",
                                                         "summary": "edited"})
    assert res.url.startswith(client.get_absolute_url())


def test_overdue_follow_up_from_converted_lead_shows_on_client(client_in, make_lead):
    from apps.clients import services
    lead = make_lead("A", stage="won")
    FollowUp.objects.create(lead=lead, due_date=timezone.localdate() - timedelta(days=1), note="Send contract")
    client = services.convert_lead(lead, Client(company="A Co", currency="PKR"))
    assert "Send contract" in client_in.get(client.get_absolute_url()).content.decode()


def test_pdf_handles_non_latin_names(client_in, make_client):
    """Helvetica printed boxes for Urdu, Turkish (ğ ş), Polish (ł) etc. Fonts are now embedded."""
    from apps.clients.models import Contact
    from apps.invoices.models import Invoice, InvoiceLine
    c = make_client("مہک بیوٹی سیلون", address="Şişli, İstanbul · Łódź · Hà Nội")
    Contact.objects.create(client=c, name="Ayşe Łukasz", is_primary=True)
    inv = Invoice.objects.create(number="INV-0009", client=c, currency="PKR", due_date=timezone.localdate())
    InvoiceLine.objects.create(invoice=inv, description="ماہانہ پیکیج — Growth", unit_price=100)
    pdf = client_in.get(f"/invoices/{inv.pk}/pdf/").content
    assert pdf.startswith(b"%PDF")
    assert b"NotoNaskhArabic" in pdf and b"NotoSans" in pdf
