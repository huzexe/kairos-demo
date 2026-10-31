from django.contrib import admin

from .models import Invoice, InvoiceLine


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["number", "client", "issue_date", "due_date", "total", "currency", "is_sent", "is_paid"]
    list_filter = ["is_sent", "is_paid", "currency"]
    search_fields = ["number", "client__company"]
    readonly_fields = ["total"]
    inlines = [InvoiceLineInline]
