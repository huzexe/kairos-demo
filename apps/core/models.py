import zoneinfo

from django.core.exceptions import ValidationError
from django.db import models

from .currencies import CURRENCY_CHOICES, DEFAULT_CURRENCY


def validate_timezone(value):
    if value not in zoneinfo.available_timezones():
        raise ValidationError(f"“{value}” is not a known time zone.")


class AgencySettings(models.Model):
    """The agency's own details. There is exactly one row (pk=1)."""

    name = models.CharField("agency name", max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    website = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    default_currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default=DEFAULT_CURRENCY,
        help_text="Used for new leads and clients. Each client can still have its own.",
    )
    timezone = models.CharField(
        "time zone", max_length=64, default="UTC", validators=[validate_timezone],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "agency settings"
        verbose_name_plural = "agency settings"

    def __str__(self):
        return self.name or "Agency"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "AgencySettings":
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"name": "My Agency"})
        return obj
