import zoneinfo

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import UserCreationForm

from .models import AgencySettings

TIMEZONE_CHOICES = [(tz, tz.replace("_", " ")) for tz in sorted(zoneinfo.available_timezones())
                    if "/" in tz and not tz.startswith(("Etc/", "SystemV/", "US/"))] + [("UTC", "UTC")]


class SetupForm(UserCreationForm):
    """First-run form: creates the owner account and the agency profile together."""

    agency_name = forms.CharField(max_length=120, label="Agency name")
    default_currency = forms.ChoiceField(
        choices=AgencySettings._meta.get_field("default_currency").choices,
        initial=AgencySettings._meta.get_field("default_currency").default,
        label="Main currency",
        help_text="You can still pick a different currency for each client.",
    )
    timezone = forms.ChoiceField(choices=TIMEZONE_CHOICES, initial="UTC", label="Time zone")

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")

    field_order = ["agency_name", "default_currency", "timezone",
                   "username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = False
        # The built-in help text is long; the validators still run.
        self.fields["password1"].help_text = "At least 8 characters, not only numbers."
        self.fields["username"].help_text = ""
        self.fields["password2"].help_text = ""
        self.fields["password2"].label = "Confirm password"
        self.fields["email"].label = "Email"


class AgencySettingsForm(forms.ModelForm):
    timezone = forms.ChoiceField(choices=TIMEZONE_CHOICES, label="Time zone")

    class Meta:
        model = AgencySettings
        fields = ["name", "email", "phone", "website", "address", "default_currency", "timezone"]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}


class AccountForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email"]
        labels = {"first_name": "First name", "last_name": "Last name"}
        help_texts = {"username": "Used to sign in."}


class PasswordChangeForm(forms.Form):
    """Change password, asking for the current one first."""

    current_password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="At least 8 characters, not only numbers.",
    )
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        value = self.cleaned_data["current_password"]
        if not self.user.check_password(value):
            raise forms.ValidationError("That isn’t your current password.")
        return value

    def clean(self):
        cleaned = super().clean()
        new, confirm = cleaned.get("new_password"), cleaned.get("confirm_password")
        if new and confirm and new != confirm:
            self.add_error("confirm_password", "The two passwords don’t match.")
        if new:
            try:
                password_validation.validate_password(new, self.user)
            except forms.ValidationError as exc:
                self.add_error("new_password", exc)
        return cleaned

    def save(self):
        self.user.set_password(self.cleaned_data["new_password"])
        self.user.save(update_fields=["password"])
        return self.user
