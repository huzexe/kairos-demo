from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods, require_POST

from apps.clients.models import Client
from apps.core.utils import safe_next
from apps.pipeline.models import Lead

from . import services
from .forms import ActivityForm, FollowUpForm
from .models import Activity, ActivityKind, Channel, FollowUp


def _subject(kind, pk):
    """The lead or client an activity / follow-up is being added to."""
    if kind == "lead":
        return {"lead": get_object_or_404(Lead, pk=pk)}
    if kind == "client":
        return {"client": get_object_or_404(Client, pk=pk)}
    raise Http404


def _back(obj, anchor="timeline"):
    """
    URL of the page the item shows on. Items from a lead that became a
    client show on the client's page, so go back there.
    """
    subject = obj.client if obj.client_id else obj.lead
    if not obj.client_id:
        client = Client.objects.filter(lead_id=obj.lead_id).first()
        if client:
            subject = client
    return f"{subject.get_absolute_url()}#{anchor}"


def _safe_next(request, fallback):
    return safe_next(request, fallback)


def _errors_text(form):
    return "; ".join(f"{form.fields[f].label if f in form.fields else ''}: {' '.join(e)}".lstrip(": ")
                     for f, e in form.errors.items())


@require_POST
def activity_add(request, kind, pk):
    link = _subject(kind, pk)
    activity = Activity(**link, logged_by=request.user)
    form = ActivityForm(request.POST, instance=activity)
    if form.is_valid():
        with transaction.atomic():
            activity = form.save()
            if form.cleaned_data.get("follow_up_date"):
                FollowUp.objects.create(
                    **link, due_date=form.cleaned_data["follow_up_date"],
                    note=form.cleaned_data["follow_up_note"], created_by=request.user,
                )
        messages.success(request, f"{activity.get_kind_display()} logged.")
    else:
        messages.error(request, "Couldn’t log that: " + _errors_text(form))
    return redirect(_back(activity))


@require_http_methods(["GET", "POST"])
def activity_edit(request, pk):
    activity = get_object_or_404(Activity.objects.select_related("lead", "client"), pk=pk)
    form = ActivityForm(request.POST or None, instance=activity)
    if request.method == "POST":
        if "delete" in request.POST:
            back = _back(activity)
            activity.delete()
            messages.success(request, "Removed from the timeline.")
            return redirect(back)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved.")
            return redirect(_back(activity))
    return render(request, "activity/activity_form.html", {"form": form, "activity": activity})


@require_POST
def follow_up_add(request, kind, pk):
    link = _subject(kind, pk)
    follow_up = FollowUp(**link, created_by=request.user)
    form = FollowUpForm(request.POST, instance=follow_up)
    if form.is_valid():
        follow_up = form.save()
        messages.success(request, f"Follow-up planned for {follow_up.due_date.day} {follow_up.due_date:%b}.")
    else:
        messages.error(request, "Couldn’t plan that: " + _errors_text(form))
    return redirect(_back(follow_up, "follow-ups"))


@require_POST
def follow_up_done(request, pk):
    follow_up = get_object_or_404(FollowUp, pk=pk)
    done = request.POST.get("done", "1") == "1"
    follow_up.done_at = timezone.now() if done else None
    follow_up.save(update_fields=["done_at"])
    messages.success(request, "Marked as done." if done else "Moved back to open follow-ups.")
    return redirect(_safe_next(request, _back(follow_up, "follow-ups")))


@require_http_methods(["GET", "POST"])
def follow_up_edit(request, pk):
    follow_up = get_object_or_404(FollowUp.objects.select_related("lead", "client"), pk=pk)
    form = FollowUpForm(request.POST or None, instance=follow_up)
    if request.method == "POST":
        if "delete" in request.POST:
            back = _safe_next(request, _back(follow_up, "follow-ups"))
            follow_up.delete()
            messages.success(request, "Follow-up deleted.")
            return redirect(back)
        if form.is_valid():
            form.save()
            messages.success(request, "Follow-up saved.")
            return redirect(_safe_next(request, _back(follow_up, "follow-ups")))
    return render(request, "activity/follow_up_form.html", {
        "form": form, "follow_up": follow_up, "next": request.GET.get("next", ""),
    })


def follow_up_list(request):
    return render(request, "activity/follow_ups.html", {"buckets": services.follow_up_buckets()})


def _date_param(request, name):
    """A date from the URL, or None when it's missing or nonsense."""
    try:
        return parse_date(request.GET.get(name, ""))
    except ValueError:
        return None


def timeline_list(request):
    """Everything logged, across all leads and clients, newest first."""
    entries = Activity.objects.select_related("lead", "client", "logged_by")
    channel = request.GET.get("channel", "")
    if channel in Channel.values:
        entries = entries.filter(channel=channel)
    kind = request.GET.get("kind", "")
    if kind in ActivityKind.values:
        entries = entries.filter(kind=kind)
    since, until = _date_param(request, "from"), _date_param(request, "to")
    if since:
        entries = entries.filter(occurred_at__date__gte=since)
    if until:
        entries = entries.filter(occurred_at__date__lte=until)
    return render(request, "activity/timeline.html", {
        "page": Paginator(entries, 50).get_page(request.GET.get("page")),
        "channels": Channel.choices, "kinds": ActivityKind.choices,
        "channel": channel, "kind": kind, "since": since, "until": until,
    })
