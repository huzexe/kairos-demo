import pytest
from django.contrib.auth import get_user_model

from apps.core.models import AgencySettings
from apps.pipeline.models import Lead, LeadSource, LostReason


@pytest.fixture(autouse=True)
def _tmp_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def owner(db):
    user = get_user_model().objects.create_superuser("owner", "owner@example.com", "a-strong-pass-123")
    agency = AgencySettings.load()
    agency.name = "Test Agency"
    agency.save()
    return user


@pytest.fixture
def client_in(client, owner):
    """A test browser signed in as the owner."""
    client.force_login(owner)
    return client


@pytest.fixture
def source(db):
    return LeadSource.objects.get(name="Instagram")


@pytest.fixture
def reason(db):
    return LostReason.objects.get(name="Too expensive")


@pytest.fixture
def make_lead(db, source):
    from apps.pipeline import services

    def make(name="Lead", stage="new", currency="PKR", **kw):
        kw.setdefault("source", source)
        lead = Lead(name=name, stage=stage, currency=currency, **kw)
        return services.create_lead(lead)
    return make
