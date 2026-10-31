from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.activity import services as activity_services
from apps.activity.forms import ActivityForm, FollowUpForm
from apps.core.currencies import format_totals
from apps.pipeline.models import Lead

from . import services
from .forms import ClientForm, ContactForm, ConvertLeadForm, PackageForm, PackageItemFormSet
from .models import Client, ClientStatus, Contact, Package

# ---- Clients ------------------------------------------------------------------


def _package_data():
    """Package details for the form's live 'Package includes' preview."""
    return {p.pk: {"price": str(p.price), "currency": p.currency, "summary": p.summary}
            for p in Package.objects.prefetch_related("items")}


def client_list(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", ClientStatus.ACTIVE)
    if status not in (*ClientStatus.values, "all"):
        status = ClientStatus.ACTIVE

    clients = Client.objects.select_related("package").prefetch_related("contacts")
    if status != "all":
        clients = clients.filter(status=status)
    if q:
        clients = clients.filter(
            Q(company__icontains=q) | Q(industry__icontains=q) | Q(contacts__name__icontains=q)
            | Q(contacts__phone__icontains=q) | Q(contacts__email__icontains=q)
        ).distinct()
    clients = activity_services.with_next_follow_up(activity_services.with_last_contact(clients))

    page = Paginator(clients.order_by("company"), 50).get_page(request.GET.get("page"))
    for client in page.object_list:
        client.days_since_contact = activity_services.days_since(client.last_contact_at)

    active = Client.objects.filter(status=ClientStatus.ACTIVE, monthly_fee__isnull=False)
    monthly = {}
    for c in active.values("currency", "monthly_fee"):
        monthly[c["currency"]] = monthly.get(c["currency"], 0) + c["monthly_fee"]

    return render(request, "clients/list.html", {
        "page": page, "q": q, "status": status, "statuses": ClientStatus.choices,
        "monthly_total": format_totals(monthly),
        "counts": dict(Client.objects.values_list("status").annotate(n=Count("pk"))),
    })


@require_http_methods(["GET", "POST"])
def client_create(request):
    form = ClientForm(request.POST or None)
    contact_form = ContactForm(request.POST or None, prefix="contact", initial={"is_primary": True})
    contact_form.fields["name"].required = False
    if request.method == "POST" and form.is_valid() and contact_form.is_valid():
        with transaction.atomic():
            client = form.save(commit=False)
            client.created_by = request.user
            client.save()
            if contact_form.cleaned_data.get("name"):
                contact = contact_form.save(commit=False)
                contact.client = client
                contact.is_primary = True
                contact.save()
        messages.success(request, f"Client “{client.company}” added.")
        return redirect(client)
    return render(request, "clients/client_form.html", {
        "form": form, "contact_form": contact_form, "is_new": True, "package_data": _package_data(),
    })


@require_http_methods(["GET", "POST"])
def convert_lead(request, lead_pk):
    lead = get_object_or_404(Lead, pk=lead_pk)
    existing = Client.objects.filter(lead=lead).first()
    if existing:
        messages.info(request, f"{lead.display_title} is already a client.")
        return redirect(existing)
    if lead.is_junk:
        messages.error(request, "Restore this lead from junk before turning it into a client.")
        return redirect(lead)

    form = ConvertLeadForm(request.POST or None, initial=ConvertLeadForm.initial_from_lead(lead))
    if request.method == "POST" and form.is_valid():
        try:
            client = services.convert_lead(lead, form.save(commit=False), user=request.user)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"{client.company} is now a client. Welcome aboard!")
            return redirect(client)
    return render(request, "clients/convert.html", {"form": form, "lead": lead, "package_data": _package_data()})


def client_detail(request, pk):
    client = get_object_or_404(Client.objects.select_related("package", "lead"), pk=pk)
    timeline = activity_services.timeline(client=client)
    follow_ups = list(activity_services.open_follow_ups().filter(activity_services.timeline_filter(client=client)))
    last = activity_services.last_contact(client=client)
    invoices = client.invoices.all()[:10]
    unpaid = {}
    for inv in client.invoices.filter(is_paid=False):
        unpaid[inv.currency] = unpaid.get(inv.currency, 0) + inv.total
    return render(request, "clients/detail.html", {
        "client": client,
        "contacts": client.contacts.all(),
        "timeline": timeline,
        "follow_ups": follow_ups,
        "days_since_contact": activity_services.days_since(last),
        "activity_form": ActivityForm(initial={"contact_name": getattr(client.primary_contact, "name", "")}),
        "follow_up_form": FollowUpForm(),
        "invoices": invoices,
        "invoice_count": client.invoices.count(),
        "unpaid_total": format_totals(unpaid),
        "contact_form": ContactForm(prefix="new"),
    })


@require_http_methods(["GET", "POST"])
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Client updated.")
        return redirect(client)
    return render(request, "clients/client_form.html", {
        "form": form, "client": client, "is_new": False, "package_data": _package_data(),
    })


@require_POST
def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk)
    name = client.company
    try:
        client.delete()
    except ProtectedError:
        messages.error(request, f"{name} has invoices, so it can’t be deleted. "
                                "Set the status to “Former client” instead.")
        return redirect(client)
    messages.success(request, f"“{name}” was deleted.")
    return redirect("clients:list")


# ---- Contacts -------------------------------------------------------------------

@require_POST
def contact_add(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ContactForm(request.POST, prefix="new")
    if form.is_valid():
        contact = form.save(commit=False)
        contact.client = client
        contact.save()
        if contact.is_primary or client.contacts.count() == 1:
            services.set_primary_contact(contact)
        messages.success(request, f"Added {contact.name}.")
    else:
        messages.error(request, "Couldn’t add the contact: " + "; ".join(
            f"{form.fields[f].label}: {' '.join(e)}" if f in form.fields else " ".join(e)
            for f, e in form.errors.items()))
    return redirect(f"{client.get_absolute_url()}#contacts")


@require_http_methods(["GET", "POST"])
def contact_edit(request, pk):
    contact = get_object_or_404(Contact.objects.select_related("client"), pk=pk)
    form = ContactForm(request.POST or None, instance=contact)
    if request.method == "POST":
        if "delete" in request.POST:
            name = contact.name
            client = contact.client
            contact.delete()
            remaining = client.contacts.first()
            if remaining and not client.contacts.filter(is_primary=True).exists():
                services.set_primary_contact(remaining)
            messages.success(request, f"Removed {name}.")
            return redirect(f"{client.get_absolute_url()}#contacts")
        if form.is_valid():
            contact = form.save()
            if contact.is_primary:
                services.set_primary_contact(contact)
            messages.success(request, "Contact saved.")
            return redirect(f"{contact.client.get_absolute_url()}#contacts")
    return render(request, "clients/contact_form.html", {"form": form, "contact": contact})


# ---- Packages -------------------------------------------------------------------

def package_list(request):
    packages = Package.objects.prefetch_related("items").annotate(
        n_clients=Count("clients", filter=Q(clients__status=ClientStatus.ACTIVE)))
    return render(request, "clients/packages.html", {"packages": packages})


@require_http_methods(["GET", "POST"])
def package_edit(request, pk=None):
    package = get_object_or_404(Package, pk=pk) if pk else Package()
    form = PackageForm(request.POST or None, instance=package)
    items = PackageItemFormSet(request.POST or None, instance=package, prefix="items")
    if not pk and request.method == "GET":
        items.extra = 1  # a new package starts with two empty rows (1 required + 1 extra)
    if request.method == "POST" and form.is_valid() and items.is_valid():
        with transaction.atomic():
            package = form.save()
            items.instance = package
            items.save()
        messages.success(request, f"Package “{package.name}” saved.")
        return redirect("clients:packages")
    return render(request, "clients/package_form.html", {"form": form, "items": items, "package": package})


@require_POST
def package_delete(request, pk):
    package = get_object_or_404(Package, pk=pk)
    try:
        package.delete()
    except ProtectedError:
        messages.error(request, f"“{package.name}” is used by clients, so it can’t be deleted. "
                                "Untick “Currently offered” to retire it instead.")
        return redirect(package)
    messages.success(request, f"Deleted “{package.name}”.")
    return redirect("clients:packages")
