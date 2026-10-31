from django.contrib import admin

from .models import AgencySettings


@admin.register(AgencySettings)
class AgencySettingsAdmin(admin.ModelAdmin):
    list_display = ["name", "default_currency", "timezone"]

    def has_add_permission(self, request):
        return not AgencySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
