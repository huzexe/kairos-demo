"""Turning won leads into clients, client pages, contacts and packages."""

import pytest
from django.core.exceptions import ValidationError

from apps.activity.models import Activity
from apps.clients import services
from apps.clients.models import Client, Contact, Package
from apps.pipeline import services as pipeline_services
from apps.pipeline.models import Lead, StageChange

pytestmark = pytest.mark.django_db


def test_convert_lead_creates_client_and_contact(make_lead, package, owner):
    lead = make_lead("Matthew Murdock", company="Glow Skincare", stage="proposal",
                     phone="0300", email="a@glow.pk", instagram="glow.skin", estimated_value=80000)
    client = services.convert_lead(lead, Client(company="Glow Skincare", currency="PKR", package=package,
                                                monthly_fee=80000), user=owner)
    lead.refresh_from_db()
    assert lead.stage == "won"  # moved to Won automatically
    assert StageChange.objects.filter(lead=lead, to_stage="won").exists()
    assert client.lead == lead and client.instagram == "glow.skin"
    contact = client.contacts.get()
    assert (contact.name, contact.phone, contact.email, contact.is_primary) == ("Matthew Murdock", "0300", "a@glow.pk", True)


def test_cannot_convert_twice(make_lead):
    lead = make_lead("A", stage="won")
    services.convert_lead(lead, Client(company="A", currency="PKR"))
    with pytest.raises(ValidationError):
        services.convert_lead(lead, Client(company="A again", currency="PKR"))


def test_converted_lead_stays_won_and_cannot_be_deleted(client_in, make_lead):
    lead = make_lead("A", stage="won")
    services.convert_lead(lead, Client(company="A", currency="PKR"))
    with pytest.raises(ValidationError):
        pipeline_services.move_lead(lead, "follow_up")
    client_in.post(f"/pipeline/leads/{lead.pk}/delete/")
    assert Lead.objects.filter(pk=lead.pk).exists()
    client_in.post("/pipeline/leads/bulk/", {"ids": [lead.pk], "action": "delete"})
    assert Lead.objects.filter(pk=lead.pk).exists()


def test_convert_page_prefills_and_creates(client_in, make_lead, package):
    lead = make_lead("Matthew Murdock", company="Urban Bites", stage="won", estimated_value=120000)
    res = client_in.get(f"/clients/from-lead/{lead.pk}/")
    form = res.context["form"]
    assert form["company"].value() == "Urban Bites" and str(form["monthly_fee"].value()) == "120000.00"
    res = client_in.post(f"/clients/from-lead/{lead.pk}/", {
        "company": "Urban Bites", "currency": "PKR", "package": package.pk, "monthly_fee": "",
        "start_date": "2026-11-01",
    })
    client = Client.objects.get()
    assert res.url == client.get_absolute_url()
    assert client.monthly_fee == 80000  # empty fee filled from the package
    # Visiting again goes straight to the client
    assert client_in.get(f"/clients/from-lead/{lead.pk}/").url == client.get_absolute_url()


def test_junk_lead_cannot_be_converted(client_in, make_lead):
    lead = make_lead("J", is_junk=True)
    client_in.post(f"/clients/from-lead/{lead.pk}/", {"company": "J", "currency": "PKR", "start_date": "2026-11-01"})
    assert not Client.objects.exists()


def test_client_timeline_includes_lead_history(client_in, make_lead, owner):
    lead = make_lead("A", stage="won")
    Activity.objects.create(lead=lead, kind="call", summary="Discovery call about reels", logged_by=owner)
    client = services.convert_lead(lead, Client(company="A Co", currency="PKR"))
    Activity.objects.create(client=client, kind="meeting", summary="Kickoff meeting")
    html = client_in.get(client.get_absolute_url()).content.decode()
    assert "Discovery call about reels" in html and "Kickoff meeting" in html and "While a lead" in html


def test_create_client_directly_with_contact(client_in):
    res = client_in.post("/clients/new/", {
        "company": "Velvet Bridal", "currency": "USD", "start_date": "2026-10-01",
        "contact-name": "Matthew Murdock", "contact-phone": "0311",
    })
    client = Client.objects.get()
    assert res.url == client.get_absolute_url()
    assert client.currency == "USD" and client.contacts.get().is_primary


def test_create_client_without_contact(client_in):
    client_in.post("/clients/new/", {"company": "No Contact Co", "currency": "PKR", "start_date": "2026-10-01"})
    assert Client.objects.get().contacts.count() == 0


def test_client_form_validation(client_in):
    res = client_in.post("/clients/new/", {"company": "", "currency": "XXX", "monthly_fee": "-1",
                                           "start_date": "nope", "instagram": "bad name!"})
    assert res.status_code == 200
    assert {"company", "currency", "monthly_fee", "start_date", "instagram"} <= set(res.context["form"].errors)


def test_client_list_and_filters(client_in, make_client):
    make_client("Active One")
    make_client("Old One", status="former")
    html = client_in.get("/clients/").content.decode()
    assert "Active One" in html and "Old One" not in html
    assert "Old One" in client_in.get("/clients/?status=former").content.decode()
    assert "Active One" not in client_in.get("/clients/?q=old&status=all").content.decode()


def test_only_one_main_contact(client_in, make_client):
    c = make_client()
    first = Contact.objects.create(client=c, name="First", is_primary=True)
    client_in.post(f"/clients/{c.pk}/contacts/add/", {"new-name": "Second", "new-is_primary": "on"})
    first.refresh_from_db()
    assert not first.is_primary and c.contacts.get(name="Second").is_primary


def test_deleting_main_contact_promotes_another(client_in, make_client):
    c = make_client()
    main = Contact.objects.create(client=c, name="Main", is_primary=True)
    Contact.objects.create(client=c, name="Other")
    client_in.post(f"/clients/contacts/{main.pk}/", {"delete": "1"})
    assert c.contacts.get().is_primary


def test_client_with_invoice_cannot_be_deleted(client_in, make_client):
    from apps.invoices.models import Invoice
    c = make_client()
    Invoice.objects.create(number="X-1", client=c, currency="PKR", due_date="2026-12-01")
    client_in.post(f"/clients/{c.pk}/delete/")
    assert Client.objects.filter(pk=c.pk).exists()


def test_package_create_with_items(client_in):
    res = client_in.post("/clients/packages/new/", {
        "name": "Starter", "price": "45000", "currency": "PKR", "is_active": "on",
        "items-TOTAL_FORMS": "3", "items-INITIAL_FORMS": "0", "items-MIN_NUM_FORMS": "1", "items-MAX_NUM_FORMS": "20",
        "items-0-quantity": "12", "items-0-kind": "post",
        "items-1-quantity": "2", "items-1-kind": "other", "items-1-custom_label": "Blog articles",
        "items-2-quantity": "", "items-2-kind": "post",  # blank extra row is ignored
    })
    assert res.status_code == 302
    p = Package.objects.get(name="Starter")
    assert p.summary == "12 Posts · 2 Blog articles"


def test_package_other_needs_a_name(client_in):
    res = client_in.post("/clients/packages/new/", {
        "name": "X", "price": "1", "currency": "PKR",
        "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "0", "items-MIN_NUM_FORMS": "1", "items-MAX_NUM_FORMS": "20",
        "items-0-quantity": "2", "items-0-kind": "other", "items-0-custom_label": "",
    })
    assert res.status_code == 200 and not Package.objects.exists()


def test_package_needs_at_least_one_item(client_in):
    res = client_in.post("/clients/packages/new/", {
        "name": "Empty", "price": "1", "currency": "PKR",
        "items-TOTAL_FORMS": "0", "items-INITIAL_FORMS": "0", "items-MIN_NUM_FORMS": "1", "items-MAX_NUM_FORMS": "20",
    })
    assert res.status_code == 200 and not Package.objects.exists()


def test_package_in_use_cannot_be_deleted(client_in, make_client, package):
    make_client(package=package)
    client_in.post(f"/clients/packages/{package.pk}/delete/")
    assert Package.objects.filter(pk=package.pk).exists()


def test_retired_package_not_offered_to_new_clients(client_in, package):
    package.is_active = False
    package.save()
    res = client_in.get("/clients/new/")
    assert package not in res.context["form"].fields["package"].queryset
