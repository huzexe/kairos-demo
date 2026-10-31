from django import forms
from django.db.models import Q
from django.forms import inlineformset_factory

from apps.core.models import AgencySettings

from .models import Client, Contact, DeliverableKind, Package, PackageItem

MONEY_WIDGET = forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"})


class PackageForm(forms.ModelForm):
    class Meta:
        model = Package
        fields = ["name", "description", "price", "currency", "is_active"]
        widgets = {"price": MONEY_WIDGET}
        labels = {"is_active": "Currently offered"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["currency"].initial = AgencySettings.load().default_currency


class PackageItemForm(forms.ModelForm):
    class Meta:
        model = PackageItem
        fields = ["quantity", "kind", "custom_label"]
        widgets = {"quantity": forms.NumberInput(attrs={"min": "1", "inputmode": "numeric"})}
        labels = {"custom_label": "Name (for Other)", "kind": "Type"}

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("kind") == DeliverableKind.OTHER and not cleaned.get("custom_label", "").strip():
            self.add_error("custom_label", "Name this deliverable, e.g. “Blog articles”.")
        if cleaned.get("kind") != DeliverableKind.OTHER:
            cleaned["custom_label"] = ""
        return cleaned


PackageItemFormSet = inlineformset_factory(
    Package, PackageItem, form=PackageItemForm, extra=0, can_delete=True,
    min_num=1, validate_min=True, max_num=20,
)


def _package_choices(current_id=None):
    return Package.objects.filter(Q(is_active=True) | Q(pk=current_id)).prefetch_related("items")


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["company", "industry", "status", "currency", "package", "monthly_fee", "start_date",
                  "website", "instagram", "address", "notes"]
        widgets = {
            "monthly_fee": MONEY_WIDGET,
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {"instagram": "Username only, without @."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["package"].queryset = _package_choices(self.instance.package_id)
        self.fields["package"].empty_label = "No package yet"
        if not self.instance.pk:
            self.fields["currency"].initial = AgencySettings.load().default_currency
            self.fields.pop("status", None)

    def clean_instagram(self):
        return self.cleaned_data["instagram"].strip().lstrip("@")

    def clean(self):
        cleaned = super().clean()
        package = cleaned.get("package")
        # Fill the fee from the package when it's left empty and currencies match.
        if package and cleaned.get("monthly_fee") is None and package.currency == cleaned.get("currency"):
            cleaned["monthly_fee"] = package.price
        return cleaned


class ConvertLeadForm(ClientForm):
    """The client form, pre-filled from a won lead."""

    class Meta(ClientForm.Meta):
        fields = ["company", "industry", "currency", "package", "monthly_fee", "start_date"]

    @classmethod
    def initial_from_lead(cls, lead):
        return {
            "company": lead.company or lead.name,
            "currency": lead.currency,
            "monthly_fee": lead.estimated_value,
        }


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["name", "role", "phone", "email", "is_primary"]
        widgets = {"phone": forms.TextInput(attrs={"inputmode": "tel"})}
