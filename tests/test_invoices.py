"""Invoice numbering, totals, statuses, locking and PDF."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import AgencySettings
from apps.invoices import services
from apps.invoices.models import Invoice, InvoiceLine

pytestmark = pytest.mark.django_db


def lines_data(*lines, initial=0):
    data = {"lines-TOTAL_FORMS": str(len(lines)), "lines-INITIAL_FORMS": str(initial),
            "lines-MIN_NUM_FORMS": "0", "lines-MAX_NUM_FORMS": "50"}
    for i, line in enumerate(lines):
        for key, value in line.items():
            data[f"lines-{i}-{key}"] = value
    return data


def create(client_in, client, *lines, **extra):
    today = timezone.localdate()
    data = {"client": client.pk, "issue_date": today.isoformat(),
            "due_date": (today + timedelta(days=7)).isoformat(), "notes": ""}
    data.update(extra)
    data.update(lines_data(*lines))
    return client_in.post("/invoices/new/", data)


def test_create_invoice_numbers_and_totals(client_in, make_client):
    c = make_client(currency="USD")
    res = create(client_in, c,
                 {"description": "Growth package", "quantity": "1", "unit_price": "1200"},
                 {"description": "Ads management", "quantity": "1.5", "unit_price": "200.10"})
    inv = Invoice.objects.get()
    assert res.url == inv.get_absolute_url()
    assert inv.number == "INV-0001" and inv.currency == "USD"
    assert inv.total == Decimal("1500.15")
    assert list(inv.lines.values_list("description", flat=True)) == ["Growth package", "Ads management"]
    assert AgencySettings.load().next_invoice_number == 2


def test_numbers_skip_ones_already_used(client_in, make_client):
    agency = AgencySettings.load()
    agency.invoice_prefix, agency.next_invoice_number = "PS-", 7
    agency.save()
    c = make_client()
    Invoice.objects.create(number="PS-0007", client=c, currency="PKR", due_date=timezone.localdate())
    create(client_in, c, {"description": "x", "quantity": "1", "unit_price": "1"})
    assert Invoice.objects.filter(number="PS-0008").exists()


def test_invoice_needs_a_line(client_in, make_client):
    res = create(client_in, make_client(), {"description": "", "quantity": "", "unit_price": ""})
    assert res.status_code == 200 and not Invoice.objects.exists()
    assert AgencySettings.load().next_invoice_number == 1  # no number used up


def test_due_before_issue_rejected(client_in, make_client):
    today = timezone.localdate()
    res = create(client_in, make_client(), {"description": "x", "quantity": "1", "unit_price": "1"},
                 due_date=(today - timedelta(days=1)).isoformat())
    assert res.status_code == 200 and not Invoice.objects.exists()


def test_negative_price_rejected(client_in, make_client):
    res = create(client_in, make_client(), {"description": "x", "quantity": "1", "unit_price": "-5"})
    assert res.status_code == 200 and not Invoice.objects.exists()


def test_former_client_cannot_be_invoiced(client_in, make_client):
    res = create(client_in, make_client(status="former"), {"description": "x", "quantity": "1", "unit_price": "1"})
    assert res.status_code == 200 and not Invoice.objects.exists()


def test_new_invoice_prefills_package_line(client_in, make_client, package):
    c = make_client(package=package, monthly_fee=75000)
    res = client_in.get(f"/invoices/new/?client={c.pk}")
    first = res.context["lines"].forms[0]
    assert first.initial["description"].startswith("Growth package — ")
    assert first.initial["unit_price"] == 75000


def edit_post(client_in, inv, *lines, **extra):
    data = {"issue_date": inv.issue_date.isoformat(), "due_date": inv.due_date.isoformat(), "notes": ""}
    data.update(extra)
    data.update(lines_data(*lines, initial=inv.lines.count()))
    return client_in.post(f"/invoices/{inv.pk}/edit/", data)


def test_edit_lines_and_recalculate(client_in, make_client):
    c = make_client()
    create(client_in, c, {"description": "A", "quantity": "1", "unit_price": "100"},
           {"description": "B", "quantity": "1", "unit_price": "50"})
    inv = Invoice.objects.get()
    a, b = inv.lines.all()
    edit_post(client_in, inv,
              {"id": a.pk, "description": "A", "quantity": "2", "unit_price": "100"},
              {"id": b.pk, "description": "B", "quantity": "1", "unit_price": "50", "DELETE": "on"})
    inv.refresh_from_db()
    assert inv.total == Decimal("200.00") and inv.lines.count() == 1


def test_cannot_delete_every_line(client_in, make_client):
    c = make_client()
    create(client_in, c, {"description": "A", "quantity": "1", "unit_price": "100"})
    inv = Invoice.objects.get()
    line = inv.lines.get()
    res = edit_post(client_in, inv, {"id": line.pk, "description": "A", "quantity": "1", "unit_price": "100", "DELETE": "on"})
    assert res.status_code == 200 and inv.lines.count() == 1


def make_invoice(client, total=100, days_ago=0, due_in=7):
    issue = timezone.localdate() - timedelta(days=days_ago)
    inv = Invoice.objects.create(number=f"T-{Invoice.objects.count() + 1}", client=client, currency=client.currency,
                                 issue_date=issue, due_date=issue + timedelta(days=due_in))
    InvoiceLine.objects.create(invoice=inv, description="x", unit_price=total)
    return services.recalculate(inv)


def test_statuses(make_client):
    c = make_client()
    inv = make_invoice(c)
    assert inv.status_label == "Not sent"
    services.set_sent(inv, True)
    assert inv.status_label == "Sent" and inv.sent_at == timezone.localdate()
    late = make_invoice(c, days_ago=20, due_in=7)
    assert late.is_overdue and late.status_label == "Overdue" and late.days_overdue == 13
    services.set_paid(late, True)
    assert late.status_label == "Paid" and late.is_sent and not late.is_overdue


def test_paid_date_rules(make_client):
    inv = make_invoice(make_client(), days_ago=3)
    with pytest.raises(ValidationError):
        services.set_paid(inv, True, timezone.localdate() - timedelta(days=10))  # before issue
    with pytest.raises(ValidationError):
        services.set_paid(inv, True, timezone.localdate() + timedelta(days=1))   # future


def test_paid_invoice_is_locked(client_in, make_client):
    inv = make_invoice(make_client())
    services.set_paid(inv, True)
    assert client_in.get(f"/invoices/{inv.pk}/edit/").url == inv.get_absolute_url()
    client_in.post(f"/invoices/{inv.pk}/delete/")
    assert Invoice.objects.filter(pk=inv.pk).exists()
    client_in.post(f"/invoices/{inv.pk}/status/", {"action": "not-sent"})
    inv.refresh_from_db()
    assert inv.is_sent


def test_status_endpoint(client_in, make_client):
    inv = make_invoice(make_client())
    client_in.post(f"/invoices/{inv.pk}/status/", {"action": "sent"})
    client_in.post(f"/invoices/{inv.pk}/status/", {"action": "paid", "paid_on": timezone.localdate().isoformat()})
    inv.refresh_from_db()
    assert inv.is_sent and inv.is_paid
    client_in.post(f"/invoices/{inv.pk}/status/", {"action": "unpaid"})
    inv.refresh_from_db()
    assert not inv.is_paid and inv.paid_at is None


def test_delete_unpaid(client_in, make_client):
    c = make_client()
    inv = make_invoice(c)
    res = client_in.post(f"/invoices/{inv.pk}/delete/")
    assert res.url == c.get_absolute_url() and not Invoice.objects.exists()


def test_pdf(client_in, make_client):
    from apps.clients.models import Contact
    c = make_client("Glow <Skincare> & Co", address="12 Main Blvd\nLahore")
    Contact.objects.create(client=c, name="Ayesha", email="a@glow.pk", is_primary=True)
    agency = AgencySettings.load()
    agency.payment_details = "Bank: Meezan\nIBAN: PK00"
    agency.save()
    inv = make_invoice(c, total=Decimal("85000.50"))
    res = client_in.get(f"/invoices/{inv.pk}/pdf/")
    assert res["Content-Type"] == "application/pdf" and res.content.startswith(b"%PDF")
    assert res["Content-Disposition"].startswith("inline")
    assert client_in.get(f"/invoices/{inv.pk}/pdf/?download=1")["Content-Disposition"].startswith("attachment")


def test_list_filters_and_totals(client_in, make_client):
    pkr, usd = make_client("P"), make_client("U", currency="USD")
    make_invoice(pkr, total=1000)
    make_invoice(usd, total=50, days_ago=30)  # overdue
    paid = make_invoice(pkr, total=7)
    services.set_paid(paid, True)
    res = client_in.get("/invoices/")
    assert res.context["unpaid_total"] == "PKR 1,000 · USD 50"
    assert res.context["overdue_total"] == "USD 50"
    assert len(client_in.get("/invoices/?status=overdue").context["page"].object_list) == 1
    assert len(client_in.get("/invoices/?status=paid").context["page"].object_list) == 1


def test_invoice_settings(client_in):
    res = client_in.post("/settings/invoices/", {"invoice_prefix": "PS/", "next_invoice_number": "40",
                                                  "invoice_due_days": "14", "payment_details": "IBAN"})
    assert res.status_code == 302
    assert services.preview_next_number() == "PS/0040"
    res = client_in.post("/settings/invoices/", {"invoice_prefix": "bad prefix!", "next_invoice_number": "0",
                                                  "invoice_due_days": "14"})
    assert res.status_code == 200 and {"invoice_prefix", "next_invoice_number"} <= set(res.context["form"].errors)
