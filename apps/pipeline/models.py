import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.currencies import CURRENCY_CHOICES, DEFAULT_CURRENCY


class OrderedChoice(models.Model):
    """A short, owner-editable list item (lead sources, lost reasons)."""

    name = models.CharField(max_length=60, unique=True)
    is_active = models.BooleanField(
        "in use", default=True, help_text="Hidden items stay on old leads but can’t be picked for new ones.",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class LeadSource(OrderedChoice):
    class Meta(OrderedChoice.Meta):
        verbose_name = "lead source"


class LostReason(OrderedChoice):
    class Meta(OrderedChoice.Meta):
        verbose_name = "lost reason"


class Stage(models.TextChoices):
    NEW = "new", "New Lead"
    DISCOVERY = "discovery", "Discovery Call"
    PROPOSAL = "proposal", "Proposal Sent"
    FOLLOW_UP = "follow_up", "Follow-up"
    WON = "won", "Won"
    LOST = "lost", "Lost"


OPEN_STAGES = [Stage.NEW, Stage.DISCOVERY, Stage.PROPOSAL, Stage.FOLLOW_UP]


class Temperature(models.TextChoices):
    HOT = "hot", "Hot"
    COLD = "cold", "Cold"


_INSTAGRAM_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def validate_instagram(value):
    if not _INSTAGRAM_RE.match(value):
        raise ValidationError("Use the Instagram username only, e.g. brandname (letters, numbers, . and _).")


class Lead(models.Model):
    name = models.CharField("contact name", max_length=120)
    company = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    instagram = models.CharField(
        "Instagram", max_length=30, blank=True, validators=[validate_instagram],
    )

    source = models.ForeignKey(LeadSource, on_delete=models.PROTECT, related_name="leads")
    temperature = models.CharField(max_length=4, choices=Temperature.choices, default=Temperature.COLD)
    stage = models.CharField(max_length=12, choices=Stage.choices, default=Stage.NEW, db_index=True)
    position = models.PositiveIntegerField(default=0, help_text="Order of the card inside its column.")
    stage_entered_at = models.DateTimeField(default=timezone.now)

    estimated_value = models.DecimalField(
        "estimated monthly value", max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default=DEFAULT_CURRENCY)

    is_junk = models.BooleanField("junk", default=False, db_index=True)
    lost_reason = models.ForeignKey(
        LostReason, on_delete=models.PROTECT, null=True, blank=True, related_name="leads",
    )
    lost_note = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["stage", "position", "-created_at"]
        indexes = [models.Index(fields=["stage", "position"])]

    def __str__(self):
        return f"{self.name} ({self.company})" if self.company else self.name

    def get_absolute_url(self):
        return reverse("pipeline:lead_detail", args=[self.pk])

    @property
    def display_title(self):
        """Company first when there is one — agencies think in brands."""
        return self.company or self.name

    @property
    def days_in_stage(self) -> int:
        return max((timezone.now() - self.stage_entered_at).days, 0)

    @property
    def is_open(self) -> bool:
        return self.stage in OPEN_STAGES

    def clean(self):
        if self.instagram:
            self.instagram = self.instagram.strip().lstrip("@")
        if self.stage == Stage.LOST and not self.lost_reason_id:
            raise ValidationError({"lost_reason": "Pick why this lead was lost."})
        if self.stage != Stage.LOST and (self.lost_reason_id or self.lost_note):
            self.lost_reason = None
            self.lost_note = ""
        if self.is_junk and self.stage == Stage.WON:
            raise ValidationError({"is_junk": "A won lead can’t be marked as junk."})


class StageChange(models.Model):
    """Every time a lead moves to another stage."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="stage_changes")
    from_stage = models.CharField(max_length=12, choices=Stage.choices, blank=True)
    to_stage = models.CharField(max_length=12, choices=Stage.choices)
    lost_reason = models.ForeignKey(LostReason, on_delete=models.SET_NULL, null=True, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-changed_at", "-pk"]

    def __str__(self):
        return f"{self.lead}: {self.get_from_stage_display() or 'created'} → {self.get_to_stage_display()}"
