import zoneinfo

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
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

    # Invoices
    invoice_prefix = models.CharField(
        max_length=12, default="INV-", blank=True,
        validators=[RegexValidator(r"^[A-Za-z0-9\-_/]*$", "Use letters, numbers, - _ or / only.")],
        help_text="Put before every invoice number, e.g. INV- gives INV-0001.",
    )
    next_invoice_number = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)],
        help_text="The number the next invoice will get.",
    )
    invoice_due_days = models.PositiveIntegerField(
        "days to pay", default=7, validators=[MaxValueValidator(365)],
        help_text="New invoices are due this many days after they’re issued.",
    )
    payment_details = models.TextField(
        blank=True, help_text="Printed on invoices, e.g. bank name, account title, IBAN.",
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
