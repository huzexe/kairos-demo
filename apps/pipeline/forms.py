from django import forms
from django.db.models import Q

from apps.core.models import AgencySettings

from .models import Lead, LeadSource, LostReason, Stage


def _active_or_current(model, current_id):
    """Active items, plus the one already chosen (even if it was hidden since)."""
    return model.objects.filter(Q(is_active=True) | Q(pk=current_id)).order_by("order", "name")


class LeadForm(forms.ModelForm):
    """Create or edit a lead. Stage changes after creation go through MoveForm."""

    class Meta:
        model = Lead
        fields = [
            "name", "company", "phone", "email", "instagram",
            "source", "temperature", "stage",
            "estimated_value", "currency",
            "lost_reason", "lost_note", "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 4}),
            "temperature": forms.RadioSelect,
            "estimated_value": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}),
            "phone": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"}),
        }
        labels = {"lost_note": "Lost note", "temperature": "Hot or cold"}
        help_texts = {
            "instagram": "Username only, without @.",
            "estimated_value": "What this client would likely pay per month.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        self.fields["source"].queryset = _active_or_current(LeadSource, instance.source_id)
        self.fields["source"].empty_label = "Choose a source"
        self.fields["lost_reason"].queryset = _active_or_current(LostReason, instance.lost_reason_id)
        self.fields["lost_reason"].empty_label = "Choose a reason"
        if instance.pk:
            # Moving between stages is done from the lead page or the board,
            # so the change gets recorded in the stage history.
            del self.fields["stage"]
            if instance.stage != Stage.LOST:
                del self.fields["lost_reason"]
                del self.fields["lost_note"]
        else:
            self.fields["currency"].initial = AgencySettings.load().default_currency

    def clean_instagram(self):
        return self.cleaned_data["instagram"].strip().lstrip("@")

    def clean(self):
        cleaned = super().clean()
        stage = cleaned.get("stage", self.instance.stage)
        if stage == Stage.LOST and not cleaned.get("lost_reason") and "lost_reason" in self.fields:
            self.add_error("lost_reason", "Pick why this lead was lost.")
        return cleaned


class MoveForm(forms.Form):
    """Move a lead to another stage (used by the board and the lead page)."""

    stage = forms.ChoiceField(choices=Stage.choices)
    before_id = forms.IntegerField(required=False)
    lost_reason = forms.ModelChoiceField(queryset=LostReason.objects.all(), required=False)
    lost_note = forms.CharField(max_length=300, required=False)


class OrderedChoiceForm(forms.Form):
    name = forms.CharField(max_length=60)

    def __init__(self, model, *args, instance=None, **kwargs):
        self.model = model
        self.instance = instance
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        qs = self.model.objects.filter(name__iexact=name)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"“{name}” is already in the list.")
        return name
