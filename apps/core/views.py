from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import AccountForm, AgencySettingsForm, InvoiceSettingsForm, PasswordChangeForm, SetupForm
from .models import AgencySettings


@login_not_required
@require_http_methods(["GET", "POST"])
def setup(request):
    """First run only: create the owner account and agency profile."""
    if get_user_model().objects.exists():
        return redirect("login")

    form = SetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            # Two setup forms sent at the same moment must not both create an owner.
            if get_user_model().objects.exists():
                return redirect("login")
            user = form.save(commit=False)
            # The owner has full access, including the admin pages.
            user.is_staff = True
            user.is_superuser = True
            user.save()
            agency = AgencySettings.load()
            agency.name = form.cleaned_data["agency_name"]
            agency.default_currency = form.cleaned_data["default_currency"]
            agency.timezone = form.cleaned_data["timezone"]
            agency.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Welcome to Kairos, {agency.name}.")
        return redirect("home")
    return render(request, "core/setup.html", {"form": form})


@require_http_methods(["GET", "POST"])
def settings_agency(request):
    agency = AgencySettings.load()
    form = AgencySettingsForm(request.POST or None, request.FILES or None, instance=agency)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Agency details saved.")
        return redirect("settings_agency")
    return render(request, "core/settings_agency.html", {"form": form, "tab": "agency"})


@require_http_methods(["GET", "POST"])
def settings_account(request):
    account_form = AccountForm(instance=request.user, prefix="account")
    password_form = PasswordChangeForm(request.user, prefix="password")

    if request.method == "POST":
        if "save_account" in request.POST:
            account_form = AccountForm(request.POST, instance=request.user, prefix="account")
            if account_form.is_valid():
                account_form.save()
                messages.success(request, "Account details saved.")
                return redirect("settings_account")
        elif "change_password" in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST, prefix="password")
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # stay signed in
                messages.success(request, "Password changed.")
                return redirect("settings_account")

    return render(request, "core/settings_account.html", {
        "account_form": account_form,
        "password_form": password_form,
        "tab": "account",
    })


@require_http_methods(["GET", "POST"])
def settings_invoices(request):
    from apps.invoices.services import preview_next_number

    agency = AgencySettings.load()
    form = InvoiceSettingsForm(request.POST or None, instance=agency)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Invoice settings saved.")
        return redirect("settings_invoices")
    return render(request, "core/settings_invoices.html", {
        "form": form, "tab": "invoices", "preview": preview_next_number(),
    })


def media(request, path):
    """Uploaded files (the agency logo), for the signed-in owner only."""
    from django.conf import settings
    from django.views.static import serve
    return serve(request, path, document_root=settings.MEDIA_ROOT)
