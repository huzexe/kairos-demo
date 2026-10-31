"""Pages, permissions and the board's move endpoint."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AgencySettings
from apps.pipeline.models import Lead, LeadSource, LostReason

pytestmark = pytest.mark.django_db


# ---- First run & sign-in --------------------------------------------------

def test_first_run_sends_everything_to_setup(client):
    assert client.get("/pipeline/").url == reverse("setup")
    assert client.get("/login/").url == reverse("setup")
    assert client.get("/setup/").status_code == 200


def test_setup_creates_owner_and_agency(client):
    res = client.post("/setup/", {
        "agency_name": "Pixel & Co", "default_currency": "USD", "timezone": "Asia/Karachi",
        "username": "matthew", "email": "", "password1": "Brand-new-pass-9", "password2": "Brand-new-pass-9",
    })
    assert res.status_code == 302
    user = get_user_model().objects.get()
    assert user.username == "matthew" and user.is_superuser
    assert user.password.startswith("pbkdf2_")  # stored hashed, never plain
    agency = AgencySettings.load()
    assert (agency.name, agency.default_currency, agency.timezone) == ("Pixel & Co", "USD", "Asia/Karachi")
    assert client.get("/pipeline/").status_code == 200  # signed in straight away


def test_setup_rejects_weak_password(client):
    res = client.post("/setup/", {
        "agency_name": "A", "default_currency": "USD", "timezone": "UTC",
        "username": "matthew", "password1": "12345678", "password2": "12345678",
    })
    assert res.status_code == 200
    assert not get_user_model().objects.exists()


def test_setup_closed_once_owner_exists(client, owner):
    assert client.get("/setup/").url == reverse("login")
    client.post("/setup/", {"agency_name": "X", "default_currency": "USD", "timezone": "UTC",
                            "username": "intruder", "password1": "Brand-new-pass-9", "password2": "Brand-new-pass-9"})
    assert get_user_model().objects.count() == 1


@pytest.mark.parametrize("url", ["/pipeline/", "/pipeline/list/", "/pipeline/leads/new/", "/settings/",
                                 "/settings/account/", "/settings/lead-sources/"])
def test_pages_need_sign_in(client, owner, url):
    res = client.get(url)
    assert res.status_code == 302 and res.url.startswith("/login/")


def test_login_and_logout(client, owner):
    res = client.post("/login/", {"username": "owner", "password": "a-strong-pass-123"})
    assert res.status_code == 302
    assert client.get("/pipeline/").status_code == 200
    client.post("/logout/")
    assert client.get("/pipeline/").status_code == 302


def test_wrong_password_shows_error(client, owner):
    res = client.post("/login/", {"username": "owner", "password": "nope"})
    assert res.status_code == 200 and b"don\xe2\x80\x99t match" in res.content


# ---- Pipeline pages ----------------------------------------------------------

def test_board_shows_columns_and_totals(client_in, make_lead):
    make_lead("Matthew Murdock", company="Bake House", estimated_value=50000)
    make_lead("Matthew Murdock", estimated_value=1500, currency="USD")
    res = client_in.get("/pipeline/")
    html = res.content.decode()
    for label in ["New Lead", "Discovery Call", "Proposal Sent", "Follow-up", "Won", "Lost"]:
        assert label in html
    assert "Bake House" in html
    assert "PKR 50,000 · USD 1,500" in html


def test_board_hides_junk_and_old_closed(client_in, make_lead):
    make_lead("Visible")
    make_lead("Junky", is_junk=True)
    old = make_lead("OldWin", stage="won")
    Lead.objects.filter(pk=old.pk).update(stage_entered_at=timezone.now() - timedelta(days=60))
    html = client_in.get("/pipeline/").content.decode()
    assert "Visible" in html and "Junky" not in html and "OldWin" not in html
    assert "OldWin" in client_in.get("/pipeline/?closed=90").content.decode()
    junk_html = client_in.get("/pipeline/?junk=1").content.decode()
    assert "Junky" in junk_html and "Visible" not in junk_html


def test_board_filters(client_in, make_lead):
    referral = LeadSource.objects.get(name="Referral")
    make_lead("Hot one", temperature="hot")
    make_lead("Referred", source=referral)
    assert "Referred" not in client_in.get("/pipeline/?temperature=hot").content.decode()
    html = client_in.get(f"/pipeline/?source={referral.pk}").content.decode()
    assert "Referred" in html and "Hot one" not in html
    assert "Hot one" in client_in.get("/pipeline/?q=hot").content.decode()


def test_create_lead(client_in, source):
    res = client_in.post("/pipeline/leads/new/", {
        "name": "Matthew Murdock", "company": "Glow Skincare", "source": source.pk, "temperature": "hot",
        "stage": "discovery", "estimated_value": "75000", "currency": "PKR", "instagram": "@glow.skin",
    })
    lead = Lead.objects.get()
    assert res.url == lead.get_absolute_url()
    assert (lead.stage, lead.instagram, lead.temperature) == ("discovery", "glow.skin", "hot")


def test_create_lead_validation(client_in, source):
    res = client_in.post("/pipeline/leads/new/", {
        "name": "", "source": source.pk, "temperature": "cold", "stage": "new",
        "currency": "PKR", "estimated_value": "-5", "instagram": "bad handle!",
    })
    assert res.status_code == 200
    errors = res.context["form"].errors
    assert {"name", "estimated_value", "instagram"} <= set(errors)
    assert not Lead.objects.exists()


def test_create_lost_lead_needs_reason(client_in, source):
    res = client_in.post("/pipeline/leads/new/", {
        "name": "A", "source": source.pk, "temperature": "cold", "stage": "lost", "currency": "PKR",
    })
    assert res.status_code == 200 and "lost_reason" in res.context["form"].errors


def test_new_lead_defaults_to_agency_currency(client_in):
    agency = AgencySettings.load()
    agency.default_currency = "AED"
    agency.save()
    res = client_in.get("/pipeline/leads/new/")
    assert res.context["form"]["currency"].value() == "AED"


def test_edit_lead_does_not_change_stage(client_in, make_lead, source):
    lead = make_lead("A")
    client_in.post(f"/pipeline/leads/{lead.pk}/edit/", {
        "name": "A2", "source": source.pk, "temperature": "hot", "currency": "USD", "stage": "won",
    })
    lead.refresh_from_db()
    assert (lead.name, lead.stage, lead.currency) == ("A2", "new", "USD")


def test_lead_detail_and_delete(client_in, make_lead):
    lead = make_lead("Gone")
    assert client_in.get(lead.get_absolute_url()).status_code == 200
    assert client_in.get(f"/pipeline/leads/{lead.pk}/delete/").status_code == 405  # GET can't delete
    client_in.post(f"/pipeline/leads/{lead.pk}/delete/")
    assert not Lead.objects.exists()
    assert client_in.get(lead.get_absolute_url()).status_code == 404


# ---- Move endpoint (used by the board) ------------------------------------------

def test_move_json(client_in, make_lead):
    lead = make_lead("A")
    res = client_in.post(f"/pipeline/leads/{lead.pk}/move/", {"stage": "proposal"}, HTTP_ACCEPT="application/json")
    assert res.json() == {"ok": True, "stage": "proposal", "stage_label": "Proposal Sent"}


def test_move_to_lost_without_reason_is_400(client_in, make_lead):
    lead = make_lead("A")
    res = client_in.post(f"/pipeline/leads/{lead.pk}/move/", {"stage": "lost"}, HTTP_ACCEPT="application/json")
    assert res.status_code == 400 and "lost" in res.json()["error"]
    lead.refresh_from_db()
    assert lead.stage == "new"


def test_move_to_lost_with_reason(client_in, make_lead, reason):
    lead = make_lead("A")
    res = client_in.post(f"/pipeline/leads/{lead.pk}/move/",
                         {"stage": "lost", "lost_reason": reason.pk, "lost_note": "budget"},
                         HTTP_ACCEPT="application/json")
    assert res.status_code == 200
    lead.refresh_from_db()
    assert lead.lost_reason == reason


def test_move_bad_stage_is_400(client_in, make_lead):
    lead = make_lead("A")
    res = client_in.post(f"/pipeline/leads/{lead.pk}/move/", {"stage": "nope"}, HTTP_ACCEPT="application/json")
    assert res.status_code == 400


def test_move_needs_csrf(owner, make_lead):
    from django.test import Client
    c = Client(enforce_csrf_checks=True)
    c.force_login(owner)
    lead = make_lead("A")
    assert c.post(f"/pipeline/leads/{lead.pk}/move/", {"stage": "won"}).status_code == 403


def test_move_from_form_redirects(client_in, make_lead):
    lead = make_lead("A")
    res = client_in.post(f"/pipeline/leads/{lead.pk}/move/", {"stage": "won"})
    assert res.url == lead.get_absolute_url()


# ---- Junk & bulk -----------------------------------------------------------------

def test_junk_toggle_and_safe_redirect(client_in, make_lead):
    lead = make_lead("A")
    res = client_in.post(f"/pipeline/leads/{lead.pk}/junk/", {"junk": "1", "next": "https://evil.example"})
    assert res.url == lead.get_absolute_url()  # outside links are ignored
    lead.refresh_from_db()
    assert lead.is_junk
    client_in.post(f"/pipeline/leads/{lead.pk}/junk/", {"junk": "0", "next": "/pipeline/"})
    lead.refresh_from_db()
    assert not lead.is_junk


def test_bulk_actions(client_in, make_lead):
    a, b = make_lead("A"), make_lead("B")
    client_in.post("/pipeline/leads/bulk/", {"ids": [a.pk, b.pk], "action": "junk", "next": "/pipeline/list/"})
    assert Lead.objects.filter(is_junk=True).count() == 2
    client_in.post("/pipeline/leads/bulk/", {"ids": [a.pk], "action": "delete"})
    assert list(Lead.objects.values_list("name", flat=True)) == ["B"]


def test_list_view_pages(client_in, make_lead):
    for i in range(55):
        make_lead(f"L{i}")
    res = client_in.get("/pipeline/list/")
    assert len(res.context["page"].object_list) == 50
    assert len(client_in.get("/pipeline/list/?page=2").context["page"].object_list) == 5


# ---- Settings ----------------------------------------------------------------------

def test_agency_settings_save(client_in):
    res = client_in.post("/settings/", {"name": "New Name", "default_currency": "GBP", "timezone": "Europe/London",
                                        "email": "", "phone": "", "website": "", "address": ""})
    assert res.status_code == 302
    assert AgencySettings.load().name == "New Name"


def test_agency_settings_rejects_bad_timezone(client_in):
    res = client_in.post("/settings/", {"name": "N", "default_currency": "GBP", "timezone": "Mars/Base"})
    assert res.status_code == 200 and "timezone" in res.context["form"].errors


def test_lead_source_add_rename_hide_delete(client_in, make_lead):
    url = "/settings/lead-sources/"
    client_in.post(url, {"action": "add", "add-name": "  TikTok  "})
    tiktok = LeadSource.objects.get(name="TikTok")
    res = client_in.post(url, {"action": "add", "add-name": "tiktok"})
    assert res.status_code == 200  # duplicate rejected
    assert LeadSource.objects.filter(name__iexact="tiktok").count() == 1
    client_in.post(url, {"action": "rename", "id": tiktok.pk, "name": "TikTok Ads"})
    client_in.post(url, {"action": "toggle", "id": tiktok.pk})
    tiktok.refresh_from_db()
    assert tiktok.name == "TikTok Ads" and not tiktok.is_active
    client_in.post(url, {"action": "delete", "id": tiktok.pk})
    assert not LeadSource.objects.filter(pk=tiktok.pk).exists()


def test_source_in_use_cannot_be_deleted(client_in, make_lead, source):
    make_lead("A")
    client_in.post("/settings/lead-sources/", {"action": "delete", "id": source.pk})
    assert LeadSource.objects.filter(pk=source.pk).exists()


def test_hidden_source_not_offered_for_new_leads(client_in, source):
    source.is_active = False
    source.save()
    res = client_in.get("/pipeline/leads/new/")
    assert source not in res.context["form"].fields["source"].queryset


def test_reorder_lost_reasons(client_in):
    first, second = LostReason.objects.all()[:2]
    client_in.post("/settings/lost-reasons/", {"action": "down", "id": first.pk})
    assert list(LostReason.objects.all()[:2]) == [second, first]


def test_unknown_settings_page_404(client_in):
    assert client_in.get("/settings/whatever/").status_code == 404


def test_change_password(client_in, owner):
    res = client_in.post("/settings/account/", {
        "change_password": "1", "password-current_password": "a-strong-pass-123",
        "password-new_password": "Another-pass-456", "password-confirm_password": "Another-pass-456",
    })
    assert res.status_code == 302
    owner.refresh_from_db()
    assert owner.check_password("Another-pass-456")
    assert client_in.get("/pipeline/").status_code == 200  # still signed in


def test_change_password_needs_current(client_in, owner):
    client_in.post("/settings/account/", {
        "change_password": "1", "password-current_password": "wrong",
        "password-new_password": "Another-pass-456", "password-confirm_password": "Another-pass-456",
    })
    owner.refresh_from_db()
    assert owner.check_password("a-strong-pass-123")


def test_missing_page_uses_kairos_404(client_in):
    res = client_in.get("/pipeline/leads/999999/")
    assert res.status_code == 404
    assert "This page doesn’t exist" in res.content.decode()
