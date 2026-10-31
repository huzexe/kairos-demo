"""
Pipeline rules: creating leads, moving them between stages, junk handling.

Views call these functions instead of changing leads directly, so the rules
(lost leads need a reason, every stage change is recorded, card order stays
consistent) hold no matter where a change comes from.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Lead, LostReason, Stage, StageChange


def _renumber(stage: str, ordered_ids: list[int]) -> None:
    """Give the leads in one column positions 0, 1, 2… in the given order."""
    leads = {lead.pk: lead for lead in Lead.objects.filter(pk__in=ordered_ids)}
    changed = []
    for index, pk in enumerate(ordered_ids):
        lead = leads[pk]
        if lead.position != index:
            lead.position = index
            changed.append(lead)
    Lead.objects.bulk_update(changed, ["position"])


def _column_ids(stage: str, exclude_pk: int | None = None) -> list[int]:
    qs = Lead.objects.filter(stage=stage).order_by("position", "-created_at")
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return list(qs.values_list("pk", flat=True))


@transaction.atomic
def create_lead(lead: Lead, user=None) -> Lead:
    """Save a new lead at the top of its column and record where it started."""
    if lead.stage == Stage.LOST and not lead.lost_reason_id:
        raise ValidationError({"lost_reason": "Pick why this lead was lost."})
    lead.created_by = user
    lead.position = 0
    lead.stage_entered_at = timezone.now()
    lead.full_clean()
    lead.save()
    _renumber(lead.stage, [lead.pk] + _column_ids(lead.stage, exclude_pk=lead.pk))
    StageChange.objects.create(
        lead=lead, from_stage="", to_stage=lead.stage,
        lost_reason=lead.lost_reason, changed_by=user,
    )
    return lead


@transaction.atomic
def move_lead(
    lead: Lead,
    stage: str,
    *,
    before_id: int | None = None,
    lost_reason: LostReason | None = None,
    lost_note: str = "",
    user=None,
) -> Lead:
    """
    Move a lead to `stage`, placing it just above the lead `before_id`
    (or at the bottom of the column when `before_id` is None).

    Placing by neighbour instead of by index keeps the order right even when
    the board is filtered and only some cards are visible.
    """
    if stage not in Stage.values:
        raise ValidationError("Unknown stage.")
    lead = Lead.objects.select_for_update().get(pk=lead.pk)
    old_stage = lead.stage

    if stage == Stage.LOST:
        if lost_reason is None and not (old_stage == Stage.LOST and lead.lost_reason_id):
            raise ValidationError("Pick why this lead was lost.")
        if lost_reason is not None:
            if not lost_reason.is_active and lost_reason.pk != lead.lost_reason_id:
                raise ValidationError("That lost reason is no longer in use.")
            lead.lost_reason = lost_reason
            lead.lost_note = lost_note.strip()[:300]
    else:
        lead.lost_reason = None
        lead.lost_note = ""

    if stage == Stage.WON and lead.is_junk:
        lead.is_junk = False  # winning a lead proves it wasn't junk

    ids = _column_ids(stage, exclude_pk=lead.pk)
    if before_id is not None and before_id in ids:
        ids.insert(ids.index(before_id), lead.pk)
    else:
        ids.append(lead.pk)

    if stage != old_stage:
        lead.stage = stage
        lead.stage_entered_at = timezone.now()
    lead.save()
    _renumber(stage, ids)
    if stage != old_stage:
        _renumber(old_stage, _column_ids(old_stage))
        StageChange.objects.create(
            lead=lead, from_stage=old_stage, to_stage=stage,
            lost_reason=lead.lost_reason if stage == Stage.LOST else None,
            changed_by=user,
        )
    lead.refresh_from_db()
    return lead


def set_junk(lead: Lead, is_junk: bool) -> Lead:
    if is_junk and lead.stage == Stage.WON:
        raise ValidationError("A won lead can’t be marked as junk.")
    lead.is_junk = is_junk
    lead.save(update_fields=["is_junk", "updated_at"])
    return lead


def bulk_set_junk(lead_ids, is_junk: bool) -> int:
    """Mark many leads as junk (or not). Won leads are always skipped."""
    qs = Lead.objects.filter(pk__in=lead_ids)
    if is_junk:
        qs = qs.exclude(stage=Stage.WON)
    return qs.update(is_junk=is_junk, updated_at=timezone.now())
