from datetime import timedelta

import pytest
from django.utils import timezone

from apps.activity.models import Activity, FollowUp
from apps.invoices.models import Invoice
from apps.pipeline import services as pipeline_services

pytestmark = pytest.mark.django_db


def test_dashboard_empty_shows_welcome(client_in):
    res = client_in.get("/")
    assert res.status_code == 200 and "Welcome to Kairos" in res.content.decode()


def test_dashboard_numbers(client_in, make_lead, make_client, reason):
    make_lead("Open hot", temperature="hot", estimated_value=50000)
    make_lead("Open usd", stage="proposal", estimated_value=1000, currency="USD")
    make_lead("Junk", is_junk=True, estimated_value=999999)
    won = make_lead("Winner")
    pipeline_services.move_lead(won, "won")
    lost = make_lead("Loser")
    pipeline_services.move_lead(lost, "lost", lost_reason=reason)

    c = make_client("Quiet Co", monthly_fee=80000)
    c.start_date = timezone.localdate() - timedelta(days=60)
    c.save()
    chatty = make_client("Chatty Co", monthly_fee=20000)
    Activity.objects.create(client=chatty, kind="call", summary="x")
    Invoice.objects.create(number="I-1", client=c, currency="PKR", total=5000,
                           issue_date=timezone.localdate() - timedelta(days=30),
                           due_date=timezone.localdate() - timedelta(days=10))
    FollowUp.objects.create(client=c, due_date=timezone.localdate(), note="Call about renewal")

    ctx = client_in.get("/").context
    assert ctx["pipeline_value"] == "PKR 50,000 · USD 1,000"  # junk and closed leads excluded
    assert ctx["open_count"] == 2 and ctx["hot_count"] == 1
    assert ctx["win_rate"] == 50
    assert ctx["active_count"] == 2 and ctx["monthly_value"] == "PKR 100,000"
    assert ctx["unpaid_value"] == "PKR 5,000" and ctx["overdue_count"] == 1
    assert [c.company for c in ctx["quiet"]] == ["Quiet Co"]
    assert [r["label"] for r in ctx["lost_reasons"]] == ["Too expensive"]
    assert ctx["by_source"][0] == {"label": "Instagram", "count": 4, "pct": 100}
    assert [f.note for f in ctx["due_follow_ups"]] == ["Call about renewal"]


@pytest.mark.parametrize("url", ["/", "/clients/", "/clients/new/", "/clients/packages/", "/invoices/",
                                 "/invoices/new/", "/activity/follow-ups/", "/settings/invoices/"])
def test_new_pages_need_sign_in(client, owner, url):
    res = client.get(url)
    assert res.status_code == 302 and res.url.startswith("/login/")
