from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, ProtectedError, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.utils import safe_next

from . import services
from .forms import LeadForm, MoveForm, OrderedChoiceForm
from .models import Lead, LeadSource, LostReason, Stage, Temperature

CLOSED_WINDOWS = {"30": 30, "90": 90, "all": None}


def _filters(request):
    """Read the board/list filters from the URL."""
    get = request.GET
    return {
        "q": get.get("q", "").strip(),
        "source": get.get("source", ""),
        "temperature": get.get("temperature", "") if get.get("temperature") in Temperature.values else "",
        "junk": get.get("junk") == "1",
        "closed": get.get("closed", "30") if get.get("closed") in CLOSED_WINDOWS else "30",
    }


def _filtered_leads(f):
    qs = Lead.objects.select_related("source", "lost_reason", "client").filter(is_junk=f["junk"])
    if f["q"]:
        qs = qs.filter(
            Q(name__icontains=f["q"]) | Q(company__icontains=f["q"]) | Q(email__icontains=f["q"])
            | Q(phone__icontains=f["q"]) | Q(instagram__icontains=f["q"]) | Q(notes__icontains=f["q"])
        )
    if f["source"].isdigit():
        qs = qs.filter(source_id=int(f["source"]))
    if f["temperature"]:
        qs = qs.filter(temperature=f["temperature"])
    return qs


def _filter_context(f):
    return {
        "filters": f,
        "sources": LeadSource.objects.all(),
        "temperatures": Temperature.choices,
        "has_filters": bool(f["q"] or f["source"] or f["temperature"]),
        "junk_count": Lead.objects.filter(is_junk=True).count(),
    }


def board(request):
    f = _filters(request)
    leads = _filtered_leads(f).order_by("position", "-created_at")

    # Won and Lost columns only show recent leads, so the board stays usable
    # after months of work. "all" shows everything.
    days = CLOSED_WINDOWS[f["closed"]]
    if days is not None:
        since = timezone.now() - timedelta(days=days)
        leads = leads.filter(Q(stage__in=[Stage.NEW, Stage.DISCOVERY, Stage.PROPOSAL, Stage.FOLLOW_UP])
                             | Q(stage_entered_at__gte=since))

    by_stage = defaultdict(list)
    for lead in leads:
        by_stage[lead.stage].append(lead)

    columns = []
    for value, label in Stage.choices:
        cards = by_stage[value]
        totals = defaultdict(int)
        for lead in cards:
            if lead.estimated_value:
                totals[lead.currency] += lead.estimated_value
        columns.append({"stage": value, "label": label, "leads": cards, "totals": dict(totals)})

    return render(request, "pipeline/board.html", {
        "columns": columns,
        "lost_reasons": LostReason.objects.filter(is_active=True),
        "view": "board",
        **_filter_context(f),
    })


def lead_list(request):
    f = _filters(request)
    stage = request.GET.get("stage", "")
    leads = _filtered_leads(f).order_by("-created_at")
    if stage in Stage.values:
        leads = leads.filter(stage=stage)
    page = Paginator(leads, 50).get_page(request.GET.get("page"))
    return render(request, "pipeline/list.html", {
        "page": page,
        "stage_filter": stage,
        "stages": Stage.choices,
        "view": "list",
        **_filter_context(f),
    })


@require_http_methods(["GET", "POST"])
def lead_create(request):
    initial = {}
    if request.GET.get("stage") in Stage.values:
        initial["stage"] = request.GET["stage"]
    form = LeadForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            lead = services.create_lead(form.save(commit=False), user=request.user)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Lead “{lead.display_title}” added.")
            if "add_another" in request.POST:
                return redirect(f"{request.path}?stage={lead.stage}")
            return redirect(lead)
    return render(request, "pipeline/lead_form.html", {"form": form, "is_new": True})


def lead_detail(request, pk):
    lead = get_object_or_404(Lead.objects.select_related("source", "lost_reason"), pk=pk)
    history = list(lead.stage_changes.select_related("lost_reason", "changed_by"))

    # How far along the pipeline the lead got (a lost lead shows where it dropped out).
    track = [Stage.NEW, Stage.DISCOVERY, Stage.PROPOSAL, Stage.FOLLOW_UP, Stage.WON]
    reached = lead.stage
    if lead.stage == Stage.LOST:
        reached = next((c.from_stage for c in history if c.to_stage == Stage.LOST and c.from_stage), Stage.NEW)
    stage_index = track.index(reached) if reached in track else 0

    from apps.activity import services as activity_services
    from apps.activity.forms import ActivityForm, FollowUpForm
    from apps.clients.models import Client

    return render(request, "pipeline/lead_detail.html", {
        "lead": lead,
        "client": Client.objects.filter(lead=lead).first(),
        "timeline": activity_services.timeline(lead=lead),
        "activity_form": ActivityForm(initial={"contact_name": lead.name}),
        "follow_ups": list(activity_services.open_follow_ups().filter(lead=lead)),
        "follow_up_form": FollowUpForm(),
        "days_since_contact": activity_services.days_since(activity_services.last_contact(lead=lead)),
        "history": history,
        "stage_index": stage_index,
        "stages": Stage.choices,
        "lost_reasons": LostReason.objects.filter(is_active=True),
    })


@require_http_methods(["GET", "POST"])
def lead_edit(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    form = LeadForm(request.POST or None, instance=lead)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Lead updated.")
        return redirect(lead)
    return render(request, "pipeline/lead_form.html", {"form": form, "lead": lead, "is_new": False})


@require_POST
def lead_delete(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    title = lead.display_title
    if services.is_converted(lead):
        messages.error(request, f"“{title}” is now a client, so the lead can’t be deleted. "
                                "Its sales history is shown on the client’s page.")
        return redirect(lead)
    lead.delete()
    messages.success(request, f"“{title}” was deleted.")
    return redirect("pipeline:board")


def _wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


@require_POST
def lead_move(request, pk):
    """Move a lead. The board calls this with fetch(); the lead page posts a form."""
    lead = get_object_or_404(Lead, pk=pk)
    form = MoveForm(request.POST)
    error = None
    if form.is_valid():
        try:
            lead = services.move_lead(
                lead, form.cleaned_data["stage"],
                before_id=form.cleaned_data["before_id"],
                lost_reason=form.cleaned_data["lost_reason"],
                lost_note=form.cleaned_data["lost_note"],
                user=request.user,
            )
        except ValidationError as exc:
            error = " ".join(exc.messages)
    else:
        error = "That move isn’t valid."

    if _wants_json(request):
        if error:
            return JsonResponse({"ok": False, "error": error}, status=400)
        data = {"ok": True, "stage": lead.stage, "stage_label": lead.get_stage_display()}
        if lead.stage == Stage.WON and not services.is_converted(lead):
            data["convert_url"] = reverse("clients:convert", args=[lead.pk])
        return JsonResponse(data)

    if error:
        messages.error(request, error)
    else:
        messages.success(request, f"Moved to {lead.get_stage_display()}.")
    return redirect(lead)


@require_POST
def lead_junk(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    make_junk = request.POST.get("junk") == "1"
    try:
        services.set_junk(lead, make_junk)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(
            request,
            f"“{lead.display_title}” moved to junk." if make_junk else f"“{lead.display_title}” restored.",
        )
    return redirect(safe_next(request, lead.get_absolute_url()))


@require_POST
def lead_bulk(request):
    """Bulk actions from the list view: junk, restore or delete selected leads."""
    ids = [int(i) for i in request.POST.getlist("ids") if i.isdigit()]
    action = request.POST.get("action")
    next_url = safe_next(request, reverse("pipeline:list"))
    if not ids:
        messages.error(request, "Select at least one lead first.")
        return redirect(next_url)

    if action == "junk":
        count = services.bulk_set_junk(ids, True)
        skipped = len(ids) - count
        msg = f"{count} lead{'s' if count != 1 else ''} moved to junk."
        if skipped:
            msg += f" {skipped} won lead{'s were' if skipped != 1 else ' was'} skipped."
        messages.success(request, msg)
    elif action == "restore":
        count = services.bulk_set_junk(ids, False)
        messages.success(request, f"{count} lead{'s' if count != 1 else ''} restored.")
    elif action == "delete":
        qs = Lead.objects.filter(pk__in=ids, client__isnull=True)
        count = qs.count()
        qs.delete()
        messages.success(request, f"Deleted {count} lead{'s' if count != 1 else ''}.")
    else:
        messages.error(request, "Choose an action.")
    return redirect(next_url)


# ---- Settings: lead sources and lost reasons -------------------------------

LIST_SETTINGS = {
    "lead-sources": {
        "model": LeadSource, "tab": "sources", "title": "Lead sources",
        "intro": "Where your leads come from. Shown as a tag on every lead.",
        "item": "source",
    },
    "lost-reasons": {
        "model": LostReason, "tab": "reasons", "title": "Lost reasons",
        "intro": "Picked whenever a lead is moved to Lost, so you can see why deals fall through.",
        "item": "reason",
    },
}


@require_http_methods(["GET", "POST"])
def settings_list(request, kind):
    conf = LIST_SETTINGS.get(kind)
    if conf is None:
        raise Http404
    model = conf["model"]
    add_form = OrderedChoiceForm(model, prefix="add")

    if request.method == "POST":
        action = request.POST.get("action")
        item = None
        if request.POST.get("id", "").isdigit():
            item = model.objects.filter(pk=int(request.POST["id"])).first()

        if action == "add":
            add_form = OrderedChoiceForm(model, request.POST, prefix="add")
            if add_form.is_valid():
                last = model.objects.order_by("-order").first()
                model.objects.create(name=add_form.cleaned_data["name"], order=(last.order + 1) if last else 0)
                messages.success(request, f"Added “{add_form.cleaned_data['name']}”.")
                return redirect(request.path)
        elif item is None:
            messages.error(request, "That item no longer exists.")
            return redirect(request.path)
        elif action == "rename":
            form = OrderedChoiceForm(model, request.POST, instance=item)
            if form.is_valid():
                item.name = form.cleaned_data["name"]
                item.save(update_fields=["name"])
                messages.success(request, "Renamed.")
            else:
                messages.error(request, " ".join(form.errors["name"]))
            return redirect(request.path)
        elif action == "toggle":
            item.is_active = not item.is_active
            item.save(update_fields=["is_active"])
            messages.success(request, f"“{item.name}” is now {'shown' if item.is_active else 'hidden'}.")
            return redirect(request.path)
        elif action in ("up", "down"):
            items = list(model.objects.all())
            i = items.index(item)
            j = i - 1 if action == "up" else i + 1
            if 0 <= j < len(items):
                items[i], items[j] = items[j], items[i]
                for order, obj in enumerate(items):
                    obj.order = order
                model.objects.bulk_update(items, ["order"])
            return redirect(request.path)
        elif action == "delete":
            try:
                item.delete()
                messages.success(request, f"Deleted “{item.name}”.")
            except ProtectedError:
                messages.error(
                    request,
                    f"“{item.name}” is used by existing leads, so it can’t be deleted. Hide it instead.",
                )
            return redirect(request.path)

    items = model.objects.all()
    usage = dict(model.objects.annotate(n=Count("leads")).values_list("pk", "n"))
    return render(request, "pipeline/settings_list.html", {
        "conf": conf, "kind": kind, "items": items, "usage": usage,
        "add_form": add_form, "tab": conf["tab"],
    })
