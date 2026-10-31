from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import Activity, ActivityKind, FollowUp

DATE_WIDGET = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class ActivityForm(forms.ModelForm):
    """Log a call, meeting, message or note — and optionally plan the next follow-up."""

    follow_up_date = forms.DateField(
        required=False, widget=DATE_WIDGET, label="Next follow-up",
        help_text="Optional. Adds it to your follow-ups.",
    )
    follow_up_note = forms.CharField(
        required=False, max_length=300, label="Follow-up note",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Send the revised proposal"}),
    )

    class Meta:
        model = Activity
        fields = ["kind", "channel", "contact_name", "occurred_at", "summary"]
        widgets = {
            "kind": forms.RadioSelect,
            "occurred_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "summary": forms.Textarea(attrs={"rows": 3, "placeholder": "Key points, decisions, what they asked for…"}),
        }
        labels = {"kind": "Type"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["channel"].choices = [("", "Channel")] + list(self.fields["channel"].choices)[1:]
        if not self.instance.pk:
            self.initial.setdefault("occurred_at", timezone.localtime().replace(second=0, microsecond=0))
        else:
            # Follow-ups are planned when logging; editing only touches the activity.
            del self.fields["follow_up_date"]
            del self.fields["follow_up_note"]

    def clean_occurred_at(self):
        value = self.cleaned_data["occurred_at"]
        if value > timezone.now() + timedelta(minutes=5):
            raise forms.ValidationError("This can’t be in the future. Plan future contact as a follow-up.")
        return value

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get("follow_up_date")
        if date:
            if date < timezone.localdate():
                self.add_error("follow_up_date", "Pick today or a later date.")
            if not cleaned.get("follow_up_note", "").strip():
                kind = cleaned.get("kind")
                cleaned["follow_up_note"] = "Follow up" if kind == ActivityKind.NOTE else \
                    f"Follow up after {dict(ActivityKind.choices).get(kind, 'contact').lower()}"
        return cleaned


class FollowUpForm(forms.ModelForm):
    class Meta:
        model = FollowUp
        fields = ["due_date", "note"]
        widgets = {
            "due_date": DATE_WIDGET,
            "note": forms.TextInput(attrs={"placeholder": "e.g. Check if they reviewed the proposal"}),
        }
        labels = {"due_date": "When"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial.setdefault("due_date", timezone.localdate() + timedelta(days=2))

    def clean_due_date(self):
        value = self.cleaned_data["due_date"]
        if not self.instance.pk and value < timezone.localdate():
            raise forms.ValidationError("Pick today or a later date.")
        return value
