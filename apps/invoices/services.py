"""Invoice rules: numbering, totals, sent/paid status."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import AgencySettings

from .models import Invoice


def format_number(prefix: str, number: int) -> str:
    return f"{prefix}{number:04d}"


def preview_next_number() -> str:
    agency = AgencySettings.load()
    return format_number(agency.invoice_prefix, agency.next_invoice_number)


def default_due_date(issue_date=None):
    issue_date = issue_date or timezone.localdate()
    return issue_date + timedelta(days=AgencySettings.load().invoice_due_days)


def _take_next_number() -> str:
    """Reserve the next free invoice number. Call inside a transaction."""
    agency = AgencySettings.objects.select_for_update().get(pk=AgencySettings.load().pk)
    number = agency.next_invoice_number
    # The owner can change the counter in Settings; skip numbers already used.
    while Invoice.objects.filter(number=format_number(agency.invoice_prefix, number)).exists():
        number += 1
    agency.next_invoice_number = number + 1
    agency.save(update_fields=["next_invoice_number", "updated_at"])
    return format_number(agency.invoice_prefix, number)


def recalculate(invoice: Invoice) -> Invoice:
    total = sum((line.amount for line in invoice.lines.all()), Decimal("0"))
    if invoice.total != total:
        invoice.total = total
        invoice.save(update_fields=["total", "updated_at"])
    return invoice


@transaction.atomic
def save_invoice(invoice: Invoice, line_formset, user=None) -> Invoice:
    """Save a new or edited invoice together with its lines."""
    if invoice.pk and Invoice.objects.filter(pk=invoice.pk, is_paid=True).exists():
        raise ValidationError("Paid invoices can’t be changed. Mark it as unpaid first.")
    if not invoice.pk:
        invoice.number = _take_next_number()
        invoice.currency = invoice.client.currency
        invoice.created_by = user
    invoice.full_clean()
    invoice.save()
    line_formset.instance = invoice
    lines = line_formset.save(commit=False)
    for obj in line_formset.deleted_objects:
        obj.delete()
    for line in lines:
        line.invoice = invoice
        line.save()
    # Keep the lines in the order they appear on screen.
    kept = [f.instance for f in line_formset.forms
            if f.instance.pk and f not in line_formset.deleted_forms]
    for position, line in enumerate(kept):
        if line.position != position:
            line.position = position
            line.save(update_fields=["position"])
    if not kept:
        raise ValidationError("An invoice needs at least one line.")
    return recalculate(invoice)


def set_sent(invoice: Invoice, sent: bool) -> Invoice:
    invoice.is_sent = sent
    invoice.sent_at = timezone.localdate() if sent else None
    invoice.save(update_fields=["is_sent", "sent_at", "updated_at"])
    return invoice


def set_paid(invoice: Invoice, paid: bool, paid_on=None) -> Invoice:
    if paid:
        paid_on = paid_on or timezone.localdate()
        if paid_on < invoice.issue_date:
            raise ValidationError("The payment date can’t be before the invoice was issued.")
        if paid_on > timezone.localdate():
            raise ValidationError("The payment date can’t be in the future.")
        invoice.is_paid, invoice.paid_at = True, paid_on
        # A paid invoice was obviously sent.
        if not invoice.is_sent:
            invoice.is_sent, invoice.sent_at = True, invoice.sent_at or paid_on
    else:
        invoice.is_paid, invoice.paid_at = False, None
    invoice.save(update_fields=["is_paid", "paid_at", "is_sent", "sent_at", "updated_at"])
    return invoice
