from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.clients.models import Client, ClientStatus
from apps.core.currencies import format_totals

from . import services
from .forms import InvoiceForm, InvoiceLineFormSet, MarkPaidForm
from .models import Invoice
from .pdf import render_invoice

STATUS_FILTERS = {
    "all": ("All", Q()),
    "unpaid": ("Unpaid", Q(is_paid=False)),
    "overdue": ("Overdue", Q(is_paid=False)),  # narrowed by due date below
    "not-sent": ("Not sent", Q(is_sent=False, is_paid=False)),
    "paid": ("Paid", Q(is_paid=True)),
}


def _totals(qs):
    totals = {}
    for currency, total in qs.values_list("currency", "total"):
        totals[currency] = totals.get(currency, 0) + total
    return format_totals(totals)


def invoice_list(request):
    status = request.GET.get("status", "all")
    if status not in STATUS_FILTERS:
        status = "all"
    q = request.GET.get("q", "").strip()
    today = timezone.localdate()

    invoices = Invoice.objects.select_related("client").filter(STATUS_FILTERS[status][1])
    if status == "overdue":
        invoices = invoices.filter(due_date__lt=today)
    if q:
        invoices = invoices.filter(Q(number__icontains=q) | Q(client__company__icontains=q))
    page = Paginator(invoices, 50).get_page(request.GET.get("page"))

    unpaid = Invoice.objects.filter(is_paid=False)
    return render(request, "invoices/list.html", {
        "page": page, "status": status, "q": q,
        "filters": [(key, label) for key, (label, _) in STATUS_FILTERS.items()],
        "unpaid_total": _totals(unpaid),
        "overdue_total": _totals(unpaid.filter(due_date__lt=today)),
        "overdue_count": unpaid.filter(due_date__lt=today).count(),
        "paid_this_month": _totals(Invoice.objects.filter(
            is_paid=True, paid_at__year=today.year, paid_at__month=today.month)),
    })


def _package_line(client):
    """A first invoice line for the client's package, e.g. 'Growth package — November 2026'."""
    if not client or not client.package_id:
        return None
    month = timezone.localdate().strftime("%B %Y")
    summary = client.package.summary
    description = f"{client.package.name} package — {month}" + (f" ({summary})" if summary else "")
    return {"description": description[:200], "quantity": 1,
            "unit_price": client.monthly_fee if client.monthly_fee is not None else client.package.price}


@require_http_methods(["GET", "POST"])
def invoice_create(request):
    client = None
    if request.GET.get("client", "").isdigit():
        client = Client.objects.filter(pk=int(request.GET["client"]), status=ClientStatus.ACTIVE).first()

    initial = {"due_date": services.default_due_date()}
    if client:
        initial["client"] = client
    form = InvoiceForm(request.POST or None, initial=initial)
    lines = InvoiceLineFormSet(request.POST or None, instance=Invoice(), prefix="lines")
    if request.method == "GET":
        first = _package_line(client)
        lines = InvoiceLineFormSet(instance=Invoice(), prefix="lines", initial=[first] if first else None)
        lines.extra = 1

    if request.method == "POST" and form.is_valid() and lines.is_valid():
        try:
            invoice = services.save_invoice(form.save(commit=False), lines, user=request.user)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Invoice {invoice.number} created.")
            return redirect(invoice)

    clients = Client.objects.filter(status=ClientStatus.ACTIVE).select_related("package")
    return render(request, "invoices/invoice_form.html", {
        "form": form, "lines": lines, "is_new": True,
        "next_number": services.preview_next_number(),
        "client_data": {c.pk: {"currency": c.currency, "line": _package_line(c)} for c in clients},
    })


@require_http_methods(["GET", "POST"])
def invoice_edit(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("client"), pk=pk)
    if invoice.is_paid:
        messages.error(request, "Paid invoices can’t be changed. Mark it as unpaid first.")
        return redirect(invoice)
    form = InvoiceForm(request.POST or None, instance=invoice)
    lines = InvoiceLineFormSet(request.POST or None, instance=invoice, prefix="lines")
    if request.method == "POST" and form.is_valid() and lines.is_valid():
        try:
            services.save_invoice(form.save(commit=False), lines, user=request.user)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Invoice saved.")
            return redirect(invoice)
    return render(request, "invoices/invoice_form.html", {
        "form": form, "lines": lines, "invoice": invoice, "is_new": False,
    })


def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("client", "created_by"), pk=pk)
    return render(request, "invoices/detail.html", {
        "invoice": invoice, "lines": invoice.lines.all(), "paid_form": MarkPaidForm(),
    })


def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("client"), pk=pk)
    response = HttpResponse(render_invoice(invoice), content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") == "1" else "inline"
    safe_client = "".join(ch for ch in invoice.client.company if ch.isalnum() or ch in " -_").strip() or "client"
    response["Content-Disposition"] = f'{disposition}; filename="{invoice.number} {safe_client}.pdf"'
    return response


@require_POST
def invoice_status(request, pk):
    """Mark sent / not sent, paid / unpaid."""
    invoice = get_object_or_404(Invoice, pk=pk)
    action = request.POST.get("action")
    try:
        if action == "sent":
            services.set_sent(invoice, True)
            messages.success(request, f"{invoice.number} marked as sent.")
        elif action == "not-sent":
            if invoice.is_paid:
                raise ValidationError("A paid invoice counts as sent. Mark it as unpaid first.")
            services.set_sent(invoice, False)
            messages.success(request, f"{invoice.number} marked as not sent.")
        elif action == "paid":
            form = MarkPaidForm(request.POST)
            if not form.is_valid():
                raise ValidationError("Enter the date the payment arrived.")
            services.set_paid(invoice, True, form.cleaned_data["paid_on"])
            messages.success(request, f"{invoice.number} marked as paid.")
        elif action == "unpaid":
            services.set_paid(invoice, False)
            messages.success(request, f"{invoice.number} marked as unpaid.")
        else:
            raise ValidationError("Unknown action.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(invoice)


@require_POST
def invoice_delete(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if invoice.is_paid:
        messages.error(request, "Paid invoices can’t be deleted. Mark it as unpaid first.")
        return redirect(invoice)
    number, client = invoice.number, invoice.client
    invoice.delete()
    messages.success(request, f"Invoice {number} deleted.")
    return redirect(client)
