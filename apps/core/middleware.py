import zoneinfo

from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.utils import timezone

from .models import AgencySettings

# Paths that must work before the owner account exists.
_SETUP_OPEN_PREFIXES = ("/setup/", "/static/")


class FirstRunSetupMiddleware:
    """Until an owner account exists, send every page to the setup screen."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._has_owner = False  # once True it never goes back

    def __call__(self, request):
        if not self._has_owner:
            if get_user_model().objects.exists():
                self._has_owner = True
            elif not request.path.startswith(_SETUP_OPEN_PREFIXES):
                return redirect("setup")
        return self.get_response(request)


class AgencyTimezoneMiddleware:
    """Show dates and times in the agency's own time zone."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                timezone.activate(zoneinfo.ZoneInfo(AgencySettings.load().timezone))
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                timezone.deactivate()
        response = self.get_response(request)
        timezone.deactivate()
        return response
