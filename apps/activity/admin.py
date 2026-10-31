from django.contrib import admin

from .models import Activity, FollowUp


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ["occurred_at", "kind", "channel", "lead", "client", "contact_name"]
    list_filter = ["kind", "channel"]
    search_fields = ["summary", "contact_name"]


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ["due_date", "note", "lead", "client", "done_at"]
    list_filter = ["done_at"]
