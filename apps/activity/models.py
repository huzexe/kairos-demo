"""
The communication timeline (calls, meetings, messages, notes) and follow-ups.

Both belong to either a lead or a client — never both, never neither.
When a lead becomes a client, its earlier history shows on the client's
timeline too.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

# Kinds of activity that count as actually being in touch.
CONTACT_KINDS = ("call", "meeting", "message")


class ActivityKind(models.TextChoices):
    CALL = "call", "Call"
    MEETING = "meeting", "Meeting"
    MESSAGE = "message", "Message"
    NOTE = "note", "Note"


class Channel(models.TextChoices):
    PHONE = "phone", "Phone"
    WHATSAPP = "whatsapp", "WhatsApp"
    INSTAGRAM = "instagram", "Instagram DM"
    EMAIL = "email", "Email"
    VIDEO = "video", "Video call"
    IN_PERSON = "in_person", "In person"
    OTHER = "other", "Other"


class LeadOrClient(models.Model):
    """Shared rules; each subclass defines its own `lead` and `client` links."""

    class Meta:
        abstract = True

    def clean(self):
        if bool(self.lead_id) == bool(self.client_id):
            raise ValidationError("Link this to a lead or a client.")

    @property
    def subject(self):
        return self.client if self.client_id else self.lead


class Activity(LeadOrClient):
    lead = models.ForeignKey("pipeline.Lead", on_delete=models.CASCADE, null=True, blank=True, related_name="activities")
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, null=True, blank=True, related_name="activities")
    kind = models.CharField(max_length=10, choices=ActivityKind.choices, default=ActivityKind.CALL)
    channel = models.CharField(max_length=10, choices=Channel.choices, blank=True)
    contact_name = models.CharField(
        "spoke with", max_length=120, blank=True, help_text="Who you talked to on their side.",
    )
    occurred_at = models.DateTimeField("when", default=timezone.now, db_index=True)
    summary = models.TextField("what was discussed", max_length=4000)
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-pk"]
        verbose_name_plural = "activities"
        constraints = [
            models.CheckConstraint(
                condition=(Q(lead__isnull=False, client__isnull=True) | Q(lead__isnull=True, client__isnull=False)),
                name="activity_lead_xor_client",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.subject}"

    @property
    def is_contact(self):
        return self.kind in CONTACT_KINDS


class FollowUp(LeadOrClient):
    lead = models.ForeignKey("pipeline.Lead", on_delete=models.CASCADE, null=True, blank=True, related_name="follow_ups")
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, null=True, blank=True, related_name="follow_ups")
    due_date = models.DateField(db_index=True)
    note = models.CharField("what to do", max_length=300)
    done_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(lead__isnull=False, client__isnull=True) | Q(lead__isnull=True, client__isnull=False)),
                name="followup_lead_xor_client",
            ),
        ]

    def __str__(self):
        return f"{self.due_date}: {self.note}"

    @property
    def is_done(self):
        return self.done_at is not None

    @property
    def is_overdue(self):
        return not self.is_done and self.due_date < timezone.localdate()

    @property
    def is_today(self):
        return not self.is_done and self.due_date == timezone.localdate()
