from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from apps.clients.models import Client, ClientStatus

from .models import Invoice, InvoiceLine

DATE_WIDGET = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["client", "issue_date", "due_date", "notes"]
        widgets = {
            "issue_date": DATE_WIDGET,
            "due_date": DATE_WIDGET,
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. Thank you for your business."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # The client (and so the currency) is fixed once an invoice exists.
            del self.fields["client"]
        else:
            self.fields["client"].queryset = Client.objects.filter(status=ClientStatus.ACTIVE)
            self.fields["client"].empty_label = "Choose a client"
            self.fields["client"].label_from_instance = lambda c: f"{c.company} ({c.currency})"


class InvoiceLineForm(forms.ModelForm):
    class Meta:
        model = InvoiceLine
        fields = ["description", "quantity", "unit_price"]
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "e.g. Growth package — November 2026"}),
            "quantity": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal", "placeholder": "Qty"}),
            "unit_price": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal",
                                                   "placeholder": "Price"}),
        }
        labels = {"unit_price": "Price"}


class BaseLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        kept = [f for f in self.forms
                if f.cleaned_data and not f.cleaned_data.get("DELETE") and f.cleaned_data.get("description")]
        if not kept:
            raise forms.ValidationError("Add at least one line to the invoice.")


InvoiceLineFormSet = inlineformset_factory(
    Invoice, InvoiceLine, form=InvoiceLineForm, formset=BaseLineFormSet,
    extra=0, can_delete=True, max_num=50,
)


class MarkPaidForm(forms.Form):
    paid_on = forms.DateField(widget=DATE_WIDGET, label="Paid on")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paid_on"].initial = timezone.localdate()
