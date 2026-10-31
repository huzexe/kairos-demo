from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, fallback: str) -> str:
    """
    The `next` URL from a form, but only if it points back into Kairos.

    Checking `startswith("/")` isn't enough: browsers treat "/\\evil.com"
    like "//evil.com", which leaves the site.
    """
    url = request.POST.get("next") or request.GET.get("next") or ""
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return url
    return fallback
