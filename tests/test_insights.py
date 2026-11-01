"""The numbers behind the charts: what's drawn must match what's in the books."""
from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.activity.models import Activity
from apps.dashboard import insights
from apps.invoices import services as billing
from apps.invoices.models import Invoice, InvoiceLine
from apps.pipeline import services as pipeline_services

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate


def invoice(client, number, amount, issued=0, due=0):
    inv = Invoice.objects.create(client=client, number=number, currency=client.currency,
                                 issue_date=TODAY() + timedelta(days=issued), due_date=TODAY() + timedelta(days=due))
    InvoiceLine.objects.create(invoice=inv, description="Retainer", quantity=1, unit_price=amount)
    billing.recalculate(inv)
    inv.refresh_from_db()
    return inv


def panel(code):
    return next(p for p in insights.money_panels() if p["code"] == code)


def test_ticks_are_round_and_rise_above_the_tallest_mark():
    assert insights.nice_ticks(0) == [0]
    assert insights.nice_ticks(915000) == [0, 250000, 500000, 750000, 1000000]
    assert insights.nice_ticks(100)[-1] > 100  # an exact tick still leaves headroom
    assert insights.nice_ticks(7, whole=True) == [0, 2, 4, 6, 8]
    assert all(t == int(t) for t in insights.nice_ticks(2, whole=True))


def test_compact_axis_labels():
    assert [insights.compact(n) for n in (0, 950, 250000, 1000000, 1500000)] == ["0", "950", "250K", "1M", "1.5M"]


def test_month_start_crosses_years():
    assert insights.month_start(date(2026, 1, 20), 1) == date(2025, 12, 1)
    assert insights.month_start(date(2026, 11, 1), 11) == date(2025, 12, 1)


def test_money_never_adds_across_currencies(make_client):
    pkr, usd = make_client("Rupee Co", monthly_fee=50000), make_client("Dollar Co", monthly_fee=1000, currency="USD")
    invoice(pkr, "P-1", 50000)
    invoice(usd, "U-1", 1000)
    assert panel("PKR")["recurring"] == "PKR 50,000" and panel("USD")["recurring"] == "USD 1,000"
    assert panel("PKR")["months"][-1]["billed"] == 50000 and panel("USD")["months"][-1]["billed"] == 1000
    assert insights.money_panels()[0]["code"] == "PKR"  # the agency's main currency leads


def test_billed_and_collected_by_month(make_client):
    c = make_client(monthly_fee=1000)
    invoice(c, "A-1", 1000)
    billing.set_paid(invoice(c, "A-2", 400), True)
    months = panel("PKR")["months"]
    assert len(months) == 12 and months[-1]["current"]
    assert months[-1]["billed"] == 1400 and months[-1]["collected"] == 400
    assert months[-1]["collected_pct"] < months[-1]["billed_pct"] <= 100


def test_ageing_buckets_unpaid_invoices(make_client):
    c = make_client(start_date=TODAY() - timedelta(days=200))
    invoice(c, "A-1", 100, issued=-5, due=5)
    invoice(c, "A-2", 200, issued=-30, due=-10)
    invoice(c, "A-3", 300, issued=-70, due=-45)
    invoice(c, "A-4", 400, issued=-90, due=-80)
    billing.set_paid(invoice(c, "A-5", 900, issued=-90, due=-80), True)
    p = panel("PKR")
    assert {a["key"]: a["amount"] for a in p["ages"]} == {"not_due": 100, "late_30": 200, "late_60": 300, "late_more": 400}
    assert p["owed"] == "PKR 1,000" and p["open_count"] == 4 and p["late_count"] == 3
    assert sum(a["pct"] for a in p["ages"]) == pytest.approx(100)


def test_ring_slices_cover_the_whole_and_skip_empty_parts():
    ring = insights.ring([{"key": "a", "count": 1}, {"key": "b", "count": 0}, {"key": "c", "count": 3}])
    assert ring["total"] == 4 and [s["key"] for s in ring["slices"]] == ["a", "c"]
    assert sum(s["dash"] for s in ring["slices"]) == pytest.approx(100 - 2 * 1.6)
    assert insights.ring([{"key": "a", "count": 0}])["slices"] == []
    assert insights.ring([{"key": "a", "count": 2}])["slices"][0]["dash"] == 100  # no gap in a full circle


def test_funnel_counts_every_stage_a_lead_passed(make_lead, reason):
    make_lead("Fresh")
    pipeline_services.move_lead(make_lead("Far along"), "won")
    pipeline_services.move_lead(make_lead("Got to proposal", stage="proposal"), "lost", lost_reason=reason)
    make_lead("Junk", is_junk=True)
    rows = {r["key"]: r for r in insights.funnel()["rows"]}
    assert rows["new"]["count"] == 3 and rows["proposal"]["count"] == 2 and rows["won"]["count"] == 1
    assert rows["new"]["share"] is None and rows["follow_up"]["share"] == 50 and rows["won"]["share"] == 100


def test_funnel_with_no_leads():
    data = insights.funnel()
    assert data["total"] == 0 and data["note"] == "" and all(r["pct"] == 0 for r in data["rows"])


def test_weekly_leads_have_whole_ticks_above_the_peak(make_lead):
    for n in range(3):
        make_lead(f"Lead {n}")
    data = insights.weekly_leads()
    assert len(data["rows"]) == 12 and data["rows"][-1]["count"] == 3 and data["rows"][-1]["current"]
    assert all(r["pct"] <= 100 for r in data["rows"]) and data["total"] == 3


def test_calendar_counts_contact_but_not_notes(make_client):
    c, other = make_client("Mine"), make_client("Other")
    Activity.objects.create(client=c, kind="call", summary="x")
    Activity.objects.create(client=c, kind="note", summary="x")
    Activity.objects.create(client=other, kind="message", summary="x")
    assert insights.activity_calendar()["total"] == 2
    data = insights.activity_calendar(client=c)
    assert data["total"] == 1 and len(data["columns"]) == 12 and all(len(w["cells"]) == 7 for w in data["columns"])
    cells = [cell for week in data["columns"] for cell in week["cells"]]
    assert sum(1 for cell in cells if cell["today"]) == 1
    assert all(cell["count"] is None for cell in cells[cells.index(next(x for x in cells if x["today"])) + 1:])


def test_income_shares_name_the_concentration(make_client):
    for name, fee in (("A", 500), ("B", 300), ("C", 100), ("D", 100)):
        make_client(name, monthly_fee=fee)
    p = insights.income_shares()[0]
    assert [r["label"] for r in p["rows"]][:2] == ["A", "B"] and p["rows"][0]["pct"] == 100
    assert "90%" in p["note"] and p["total"] == "PKR 1,000"


@pytest.mark.parametrize("url", ["/", "/invoices/", "/pipeline/", "/pipeline/list/", "/clients/"])
def test_chart_pages_load_empty_and_full(client_in, make_client, make_lead, url):
    assert client_in.get(url).status_code == 200
    c = make_client(monthly_fee=1000)
    make_client("Dollar Co", monthly_fee=10, currency="USD")
    make_lead("Someone")
    invoice(c, "A-1", 1000, due=-3)
    Activity.objects.create(client=c, kind="call", summary="x")
    assert client_in.get(url).status_code == 200


def test_client_page_shows_their_contact_calendar(client_in, make_client):
    c = make_client("Glow")
    Activity.objects.create(client=c, kind="call", summary="x")
    page = client_in.get(c.get_absolute_url())
    assert page.context["calendar"]["total"] == 1 and "Contact with Glow" in page.content.decode()


def test_dashboard_greets_and_switches_currency(client_in, make_client):
    make_client("Dollar Co", monthly_fee=10, currency="USD")
    html = client_in.get("/").content.decode()
    assert "Good " in html and 'data-currency="USD"' in html and 'data-currency-panel="USD"' in html


# ---- The agency logo ---------------------------------------------------------------------------

def png_bytes():
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (11, 110, 80)).save(buf, "PNG")
    return buf.getvalue()


def agency_post(client_in, **extra):
    from apps.core.models import AgencySettings
    agency = AgencySettings.load()
    return client_in.post("/settings/", {"name": agency.name or "Agency", "default_currency": "PKR", "timezone": "UTC", **extra})


@pytest.fixture
def media_dir(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def test_logo_upload_preview_rail_and_remove(client_in, media_dir):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.models import AgencySettings
    agency_post(client_in, logo=SimpleUploadedFile("logo.png", png_bytes(), content_type="image/png"))
    agency = AgencySettings.load()
    assert agency.logo
    page = client_in.get("/settings/").content.decode()
    assert "Replace logo" in page and "Remove logo" in page
    assert page.count(f'src="{agency.logo.url}"') == 2  # the preview and the rail
    agency_post(client_in, **{"logo-clear": "on"})
    assert not AgencySettings.load().logo


@pytest.mark.parametrize("name,content", [("logo.png", b"not an image"), ("logo.svg", b"<svg></svg>")])
def test_only_real_images_become_the_logo(client_in, media_dir, name, content):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.models import AgencySettings
    res = agency_post(client_in, logo=SimpleUploadedFile(name, content))
    assert res.status_code == 200 and not AgencySettings.load().logo


def test_logo_is_on_the_invoice_pdf_with_the_footer(client_in, media_dir, make_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.invoices.pdf import render_invoice
    agency_post(client_in, logo=SimpleUploadedFile("logo.png", png_bytes(), content_type="image/png"))
    pdf = render_invoice(invoice(make_client(), "A-1", 100))
    assert pdf.startswith(b"%PDF") and b"/Subtype /Image" in pdf


def test_invoice_pdf_works_without_a_logo_or_with_a_lost_file(client_in, media_dir, make_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.models import AgencySettings
    from apps.invoices.pdf import render_invoice
    inv = invoice(make_client(), "A-1", 100)
    assert b"/Subtype /Image" not in render_invoice(inv)
    agency_post(client_in, logo=SimpleUploadedFile("logo.png", png_bytes(), content_type="image/png"))
    (media_dir / AgencySettings.load().logo.name).unlink()
    assert render_invoice(inv).startswith(b"%PDF")


def test_logo_file_needs_sign_in(client_in, media_dir):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.test import Client

    from apps.core.models import AgencySettings
    agency_post(client_in, logo=SimpleUploadedFile("logo.png", png_bytes(), content_type="image/png"))
    url = AgencySettings.load().logo.url
    assert client_in.get(url).status_code == 200
    assert Client().get(url).status_code == 302
