from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.currencies import CURRENCY_CHOICES


class Invoice(models.Model):
    """
    An invoice to one client, always in that client's currency.

    The total is stored (not only calculated) so lists and the dashboard can
    add invoices up quickly; services.recalculate() keeps it in sync with the
    lines.
    """

    number = models.CharField(max_length=30, unique=True)
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="invoices")
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    notes = models.TextField(blank=True, help_text="Shown at the bottom of the invoice.")

    is_sent = models.BooleanField("sent", default=False)
    sent_at = models.DateField(null=True, blank=True)
    is_paid = models.BooleanField("paid", default=False)
    paid_at = models.DateField(null=True, blank=True)

    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issue_date", "-pk"]

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse("invoices:detail", args=[self.pk])

    def clean(self):
        if self.issue_date and self.due_date and self.due_date < self.issue_date:
            raise ValidationError({"due_date": "The due date can’t be before the issue date."})

    @property
    def is_overdue(self):
        return not self.is_paid and self.due_date < timezone.localdate()

    @property
    def days_overdue(self):
        return (timezone.localdate() - self.due_date).days if self.is_overdue else 0

    @property
    def status_label(self):
        if self.is_paid:
            return "Paid"
        if self.is_overdue:
            return "Overdue"
        return "Sent" if self.is_sent else "Not sent"

    @property
    def status_key(self):
        return self.status_label.lower().replace(" ", "-")


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("1"), validators=[MinValueValidator(Decimal("0.01"))],
    )
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return self.description

    @property
    def amount(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))
