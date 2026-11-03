from django.template import Context, Template

from apps.core.templatetags.kairos import ageing_bar, source_icon
from apps.dashboard import insights
from apps.dashboard.templatetags import kairos_charts as charts

MONTHS = [{"label": "Oct", "full": "October", "billed": 100, "collected": 50, "billed_pct": 100, "collected_pct": 50,
           "tip": "Oct", "current": False},
          {"label": "Nov", "full": "November", "billed": 80, "collected": 80, "billed_pct": 80, "collected_pct": 80,
           "tip": "Nov", "current": True}]


def draw(source, **context):
    return Template("{% load kairos_charts %}" + source).render(Context(context))


def test_bar_chart_marks_current_and_lists_data_for_screen_readers():
    rows = [{"label": "1 Nov", "count": 3, "pct": 100, "tip": "x", "current": True}]
    html = draw('{% bar_chart rows "New leads" %}', rows=rows)
    assert "is-current" in html and '<div class="sr-only"><table>' in html and 'aria-label="New leads"' in html


def test_every_chart_has_an_empty_state():
    html = draw('{% bar_chart rows "Leads" action="Log your first lead" url="/pipeline/new/" %}',
                rows=[{"label": "a", "count": 0, "pct": 0, "tip": "", "current": False}])
    assert "chart-empty" in html and "Log your first lead" in html
    assert "chart-empty" in draw('{% hbar_ranked rows "Sources" %}', rows=[])
    assert "chart-empty" in draw('{% stacked_hbar rows "Ages" %}', rows=[])
    assert "chart-empty" in draw('{% treemap rows "Income" %}', rows=[])
    calendar = {"columns": [], "note": "", "total": 0}
    assert "chart-empty" in draw('{% heat_grid c "Contact" %}', c=calendar)
    assert "chart-empty" in draw('{% funnel f "Funnel" %}', f={"rows": [], "note": "", "worst_key": ""})


def test_paired_bars_show_one_currency_only():
    panel = {"code": "PKR", "months": MONTHS, "ticks": [], "has_money": True}
    html = draw('{% paired_bar_chart p "Billed" %}', p=panel)
    assert "PKR" in html and "USD" not in html


def test_funnel_marks_the_worst_stage_in_acid_only_when_asked():
    data = {"rows": [{"key": "new", "label": "New", "count": 10, "share": None},
                     {"key": "won", "label": "Won", "count": 2, "share": 20}],
            "note": "", "worst_key": "won"}
    assert "is-worst" in draw('{% funnel f "F" %}', f=data) and "is-accent" not in draw('{% funnel f "F" %}', f=data)
    assert "is-accent" in draw('{% funnel f "F" accent=True %}', f=data)


def test_treemap_tiles_fill_the_space_with_area_following_value():
    tiles = [{"label": n, "value": v} for n, v in (("A", 50.0), ("B", 30.0), ("C", 15.0), ("D", 5.0))]
    laid = charts._layout(tiles, 0, 0, 100, 100)
    assert abs(sum(t["w"] * t["h"] for t in laid) - 10000) < 5
    for tile in laid:
        assert abs(tile["w"] * tile["h"] / 100 - tile["value"]) < 0.5


def test_treemap_with_no_tiles():
    assert charts._layout([], 0, 0, 100, 100) == []


def test_area_line_ignores_no_data_and_draws_the_field():
    html = draw('{% area_line rows "collected" "Collected" %}', rows=MONTHS)
    assert "area-line" in html and "C" in html and "Collected" in html
    zero = [{**MONTHS[0], "collected": 0}]
    assert "chart-empty" in draw('{% area_line rows "collected" "Collected" %}', rows=zero)


def test_ring_handles_no_value():
    assert "—" in draw('{% ring v "Win rate" %}', v=None)
    assert "42%" in draw('{% ring v "Win rate" %}', v=42)


def test_meter_warns_above_the_line():
    assert "is-warn" in draw('{% meter 62 "Top three" %}')
    assert "is-warn" not in draw('{% meter 40 "Top three" %}')


def test_segments_one_per_promised_item():
    html = draw('{% segments 3 16 "Posts" %}')
    assert html.count("<i") == 16 and html.count("is-done") == 3


def test_sparkline():
    assert "<path" in draw('{% sparkline v "Trend" %}', v=[1, 3, 2])
    assert "<path" not in draw('{% sparkline v "Trend" %}', v=[0, 0])


def test_source_icon_falls_back_for_custom_sources():
    assert source_icon("Instagram") == "instagram" and source_icon("Trade show") == "source"


def test_ageing_bar_turns_warn_then_danger():
    assert ageing_bar(1)["tone"] == "" and ageing_bar(8)["tone"] == "is-warn" and ageing_bar(15)["tone"] == "is-danger"
    assert ageing_bar(60)["fill"] == 100


def test_income_shares_top_three(db, make_client):
    for name, fee in (("A", 50), ("B", 30), ("C", 15), ("D", 5)):
        make_client(name, monthly_fee=fee)
    panel = insights.income_shares()[0]
    assert panel["top3"] == 95 and len(panel["tiles"]) == 4


def test_funnel_names_the_worst_stage(db, make_lead):
    for _ in range(4):
        make_lead("x")
    assert insights.funnel()["worst_key"] == "discovery"


def test_money_delta_signs():
    assert insights._money_delta(150, 100, "PKR") == "+ PKR 50"
    assert insights._money_delta(100, 150, "PKR") == "− PKR 50"


def test_board_shows_next_follow_up(client_in, make_lead):
    from django.utils import timezone

    from apps.activity.models import FollowUp

    lead = make_lead("Has a date")
    FollowUp.objects.create(lead=lead, due_date=timezone.localdate(), note="Call")
    assert "next-fu" in client_in.get("/pipeline/").content.decode()


def test_shell_shows_status_line_and_section(client_in):
    html = client_in.get("/pipeline/").content.decode()
    assert "Data stored locally" in html and "band-pipeline" in html and "/02" in html


def test_dashboard_shows_locked_full_version_panels(client_in):
    html = client_in.get("/").content.decode()
    assert "Available in the full version" in html and "Client health" in html


def test_every_page_has_a_skip_link(client_in):
    html = client_in.get("/pipeline/").content.decode()
    assert 'class="skip-link" href="#main"' in html and 'id="main"' in html


def test_board_cards_offer_move_to_other_stages_only(client_in, make_lead):
    make_lead("Movable")
    html = client_in.get("/pipeline/").content.decode()
    assert "data-move-form" in html and 'value="discovery"' in html
    assert 'name="stage" value="new"' not in html  # the lead is already there


def test_junk_view_has_no_move_menu(client_in, make_lead):
    make_lead("Binned", is_junk=True)
    assert "data-move-form" not in client_in.get("/pipeline/?junk=1").content.decode()


def test_move_to_saves_the_stage(client_in, make_lead):
    lead = make_lead("Movable")
    res = client_in.post(f"/pipeline/leads/{lead.pk}/move/", {"stage": "proposal"}, headers={"Accept": "application/json"})
    lead.refresh_from_db()
    assert res.json()["ok"] and lead.stage == "proposal"


def test_smooth_path_passes_through_every_point_without_overshooting():
    path = charts._smooth_path([(0, 10), (10, 2), (20, 6)])
    assert path == "M0,10 C5.0,10 5.0,2 10,2 C15.0,2 15.0,6 20,6"


def test_insights_page_and_ranges(client_in, make_lead):
    from datetime import date

    make_lead("From Insta")
    html = client_in.get("/insights/").content.decode()
    assert "Funnel by source" in html and "Time to first contact" in html
    today = date(2026, 11, 3)
    assert insights.insight_range({"range": "month"}, today)[1] == date(2026, 11, 1)
    assert insights.insight_range({"range": "custom", "from": "2026-01-01", "to": "2026-02-01"}, today)[0] == "custom"
    assert insights.insight_range({"range": "custom", "from": "rubbish"}, today)[0] == "12"
    assert client_in.get("/insights/?range=custom&from=rubbish&to=x").status_code == 200


def test_win_loss_and_durations(db, make_lead, reason):
    from django.utils import timezone

    from apps.pipeline import services

    won = make_lead("Winner")
    services.move_lead(won, "discovery")
    services.move_lead(won, "won")
    lost = make_lead("Loser")
    services.move_lead(lost, "lost", lost_reason=reason)
    today = timezone.localdate()
    row = insights.win_loss_by_source(today, today)[0]
    assert row["won"] == 1 and row["lost"] == 1 and row["rate"] == 50
    assert insights.lost_reason_rows(today, today)[0]["label"] == reason.name
    assert {r["label"] for r in insights.stage_durations(today, today)} >= {"New Lead"}
    assert insights.first_contact(today, today)["never"] == 2


def test_first_contact_average(db, make_lead):
    from django.utils import timezone

    from apps.activity.models import Activity

    lead = make_lead("Called")
    Activity.objects.create(lead=lead, kind="call", summary="x", occurred_at=lead.created_at + timezone.timedelta(days=2))
    today = timezone.localdate()
    data = insights.first_contact(today, today)
    assert data["contacted"] == 1 and data["average"] == 2.0


def test_global_timeline_filters(client_in, make_lead, make_client):
    from apps.activity.models import Activity

    Activity.objects.create(lead=make_lead("A"), kind="call", channel="phone", summary="Phoned them")
    Activity.objects.create(client=make_client("B"), kind="note", summary="Just a note")
    html = client_in.get("/activity/timeline/").content.decode()
    assert "Phoned them" in html and "Just a note" in html
    assert "Just a note" not in client_in.get("/activity/timeline/?kind=call").content.decode()
    assert "Phoned them" not in client_in.get("/activity/timeline/?kind=note").content.decode()
    assert client_in.get("/activity/timeline/?from=rubbish").status_code == 200


def test_lead_page_offers_next_stage_and_time_per_stage(client_in, make_lead):
    html = client_in.get(make_lead("Next").get_absolute_url()).content.decode()
    assert "Move to Discovery Call" in html and "day" in html


def test_appearance_settings_and_locked_panels(client_in):
    html = client_in.get("/settings/appearance/").content.decode()
    assert 'data-theme-set="dark"' in html and "Available in the full version" in html
    assert "gmail" not in html


def test_every_page_uses_the_new_styles_only(client_in, make_lead, make_client):
    for url in ("/", "/pipeline/", "/pipeline/list/", "/clients/", "/clients/packages/", "/invoices/", "/insights/",
                "/activity/follow-ups/", "/activity/timeline/", "/settings/"):
        res = client_in.get(url)
        assert res.status_code == 200, url
        html = res.content.decode()
        assert "legacy.css" not in html and "kairos.css" not in html and "#i-" not in html, url


def test_error_pages_only_link_stylesheets_that_exist():
    import re
    from pathlib import Path

    from django.conf import settings as dj

    for name in ("500.html",):
        html = (Path(dj.BASE_DIR) / "templates" / name).read_text()
        for href in re.findall(r'href="/static/([^"]+\.css)"', html):
            assert (Path(dj.BASE_DIR) / "static" / href).exists(), href
