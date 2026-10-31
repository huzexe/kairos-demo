from django.urls import path

from . import views

app_name = "invoices"

urlpatterns = [
    path("", views.invoice_list, name="list"),
    path("new/", views.invoice_create, name="create"),
    path("<int:pk>/", views.invoice_detail, name="detail"),
    path("<int:pk>/edit/", views.invoice_edit, name="edit"),
    path("<int:pk>/pdf/", views.invoice_pdf, name="pdf"),
    path("<int:pk>/status/", views.invoice_status, name="status"),
    path("<int:pk>/delete/", views.invoice_delete, name="delete"),
]
