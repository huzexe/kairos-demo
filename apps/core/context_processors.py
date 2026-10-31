from .models import AgencySettings


def agency(request):
    """Make the agency's settings available in every template as `agency`."""
    if not request.user.is_authenticated:
        return {}
    return {"agency": AgencySettings.load()}
