from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.currencies import CURRENCY_CHOICES, DEFAULT_CURRENCY
from apps.pipeline.models import validate_instagram


class DeliverableKind(models.TextChoices):
    POST = "post", "Posts"
    REEL = "reel", "Reels"
    STORY = "story", "Stories"
    CAROUSEL = "carousel", "Carousels"
    VIDEO = "video", "Videos"
    OTHER = "other", "Other"


class Package(models.Model):
    """A monthly content package the agency sells, e.g. "Growth: 16 posts + 6 reels"."""

    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=300, blank=True)
    price = models.DecimalField("monthly price", max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default=DEFAULT_CURRENCY)
    is_active = models.BooleanField(
        "offered", default=True, help_text="Packages no longer offered stay on existing clients.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "price", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("clients:package_edit", args=[self.pk])

    @property
    def summary(self):
        """'12 Posts · 4 Reels'"""
        return " · ".join(item.label_text for item in self.items.all())


class PackageItem(models.Model):
    """One line of what a package includes each month."""

    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="items")
    kind = models.CharField(max_length=10, choices=DeliverableKind.choices, default=DeliverableKind.POST)
    custom_label = models.CharField(
        max_length=60, blank=True, help_text="Only for “Other”, e.g. “Blog articles”.",
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return self.label_text

    @property
    def label_text(self):
        name = self.custom_label if self.kind == DeliverableKind.OTHER and self.custom_label \
            else self.get_kind_display()
        return f"{self.quantity} {name}"


class ClientStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    FORMER = "former", "Former client"


class Client(models.Model):
    company = models.CharField("client / brand name", max_length=160)
    lead = models.OneToOneField(
        "pipeline.Lead", on_delete=models.SET_NULL, null=True, blank=True, related_name="client",
        help_text="The lead this client was won from.",
    )
    status = models.CharField(max_length=10, choices=ClientStatus.choices, default=ClientStatus.ACTIVE, db_index=True)
    currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default=DEFAULT_CURRENCY,
        help_text="Every invoice for this client uses this currency.",
    )
    package = models.ForeignKey(Package, on_delete=models.PROTECT, null=True, blank=True, related_name="clients")
    monthly_fee = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text="What this client pays per month. Filled from the package, but can differ.",
    )
    start_date = models.DateField(default=timezone.localdate)
    industry = models.CharField(max_length=80, blank=True, help_text="e.g. Restaurant, Skincare, Real estate")
    website = models.CharField(max_length=200, blank=True)
    instagram = models.CharField("Instagram", max_length=30, blank=True, validators=[validate_instagram])
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company"]

    def __str__(self):
        return self.company

    def get_absolute_url(self):
        return reverse("clients:detail", args=[self.pk])

    @property
    def primary_contact(self):
        contacts = list(self.contacts.all())
        return next((c for c in contacts if c.is_primary), contacts[0] if contacts else None)


class Contact(models.Model):
    """A person at the client's company."""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=80, blank=True, help_text="e.g. Owner, Marketing manager")
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    is_primary = models.BooleanField("main contact", default=False)

    class Meta:
        ordering = ["-is_primary", "name"]

    def __str__(self):
        return f"{self.name} ({self.role})" if self.role else self.name
