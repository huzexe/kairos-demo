"""Pipeline rules: ordering, stage history, lost reasons and junk."""

import pytest
from django.core.exceptions import ValidationError

from apps.pipeline import services
from apps.pipeline.models import Lead, LostReason, Stage, StageChange


def column(stage):
    return list(Lead.objects.filter(stage=stage).order_by("position").values_list("name", flat=True))


def test_default_sources_and_reasons_exist(db):
    from apps.pipeline.models import LeadSource
    assert list(LeadSource.objects.values_list("name", flat=True)) == [
        "Instagram", "Referral", "Paid Ads", "Cold Outreach", "Hot Outreach"]
    assert LostReason.objects.count() == 6


def test_new_lead_goes_to_top_and_records_history(make_lead):
    make_lead("A")
    b = make_lead("B")
    assert column("new") == ["B", "A"]
    change = StageChange.objects.get(lead=b)
    assert change.from_stage == "" and change.to_stage == "new"


def test_move_between_columns_places_before_neighbour(make_lead):
    a = make_lead("A")
    make_lead("B")
    x = make_lead("X", stage="discovery")
    make_lead("Y", stage="discovery")   # discovery is [Y, X]
    services.move_lead(a, "discovery", before_id=x.pk)
    assert column("discovery") == ["Y", "A", "X"]
    assert column("new") == ["B"]
    # positions are always 0..n-1 with no gaps
    assert list(Lead.objects.filter(stage="discovery").order_by("position").values_list("position", flat=True)) == [0, 1, 2]


def test_move_to_end_when_no_neighbour(make_lead):
    a = make_lead("A")
    make_lead("X", stage="proposal")
    services.move_lead(a, "proposal")
    assert column("proposal") == ["X", "A"]


def test_reorder_within_column_does_not_record_stage_change(make_lead):
    a = make_lead("A")
    b = make_lead("B")  # [B, A]
    services.move_lead(a, "new", before_id=b.pk)
    assert column("new") == ["A", "B"]
    assert StageChange.objects.filter(lead=a).count() == 1  # only "created"


def test_stage_change_resets_stage_clock_and_is_recorded(make_lead, owner):
    a = make_lead("A")
    Lead.objects.filter(pk=a.pk).update(stage_entered_at="2020-01-01T00:00:00Z")
    a.refresh_from_db()
    assert a.days_in_stage > 100
    a = services.move_lead(a, "discovery", user=owner)
    assert a.days_in_stage == 0
    last = StageChange.objects.filter(lead=a).first()
    assert (last.from_stage, last.to_stage, last.changed_by) == ("new", "discovery", owner)


def test_lost_requires_reason(make_lead):
    a = make_lead("A")
    with pytest.raises(ValidationError):
        services.move_lead(a, "lost")
    a.refresh_from_db()
    assert a.stage == "new"


def test_lost_saves_reason_and_note(make_lead, reason):
    a = services.move_lead(make_lead("A"), "lost", lost_reason=reason, lost_note="  Wanted half price  ")
    assert a.lost_reason == reason and a.lost_note == "Wanted half price"
    assert StageChange.objects.filter(lead=a).first().lost_reason == reason


def test_leaving_lost_clears_reason(make_lead, reason):
    a = services.move_lead(make_lead("A"), "lost", lost_reason=reason, lost_note="x")
    a = services.move_lead(a, "follow_up")
    assert a.lost_reason is None and a.lost_note == ""


def test_hidden_lost_reason_cannot_be_used(make_lead, reason):
    reason.is_active = False
    reason.save()
    with pytest.raises(ValidationError):
        services.move_lead(make_lead("A"), "lost", lost_reason=reason)


def test_unknown_stage_rejected(make_lead):
    with pytest.raises(ValidationError):
        services.move_lead(make_lead("A"), "maybe")


def test_create_lost_lead_requires_reason(source):
    with pytest.raises(ValidationError):
        services.create_lead(Lead(name="A", source=source, stage="lost"))


def test_won_lead_cannot_be_junk(make_lead):
    a = make_lead("A", stage="won")
    with pytest.raises(ValidationError):
        services.set_junk(a, True)


def test_winning_a_junk_lead_unjunks_it(make_lead):
    a = make_lead("A")
    services.set_junk(a, True)
    a = services.move_lead(a, "won")
    assert not a.is_junk


def test_bulk_junk_skips_won_leads(make_lead):
    a, b, w = make_lead("A"), make_lead("B"), make_lead("W", stage="won")
    assert services.bulk_set_junk([a.pk, b.pk, w.pk], True) == 2
    assert set(Lead.objects.filter(is_junk=True).values_list("name", flat=True)) == {"A", "B"}
    assert services.bulk_set_junk([a.pk], False) == 1


def test_all_stages_reachable_from_any_stage(make_lead, reason):
    """Agencies jump around (e.g. straight from New to Proposal) — allowed."""
    a = make_lead("A")
    for stage in [Stage.PROPOSAL, Stage.NEW, Stage.WON, Stage.FOLLOW_UP, Stage.DISCOVERY]:
        a = services.move_lead(a, stage)
        assert a.stage == stage
