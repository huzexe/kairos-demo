from django.contrib import admin

from .models import Lead, LeadSource, LostReason, StageChange


@admin.register(LeadSource, LostReason)
class OrderedChoiceAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "order"]
    list_editable = ["is_active", "order"]


class StageChangeInline(admin.TabularInline):
    model = StageChange
    extra = 0
    readonly_fields = ["from_stage", "to_stage", "lost_reason", "changed_by", "changed_at"]


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ["__str__", "stage", "temperature", "source", "estimated_value", "currency", "is_junk"]
    list_filter = ["stage", "temperature", "source", "is_junk"]
    search_fields = ["name", "company", "email", "phone", "instagram"]
    inlines = [StageChangeInline]
