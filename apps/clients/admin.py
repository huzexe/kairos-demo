from django.contrib import admin

from .models import Client, Contact, Package, PackageItem


class PackageItemInline(admin.TabularInline):
    model = PackageItem
    extra = 0


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ["name", "price", "currency", "is_active"]
    inlines = [PackageItemInline]


class ContactInline(admin.TabularInline):
    model = Contact
    extra = 0


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["company", "status", "package", "monthly_fee", "currency", "start_date"]
    list_filter = ["status", "currency", "package"]
    search_fields = ["company", "contacts__name"]
    inlines = [ContactInline]
