from django.urls import path

from . import views

app_name = "clients"

urlpatterns = [
    path("", views.client_list, name="list"),
    path("new/", views.client_create, name="create"),
    path("from-lead/<int:lead_pk>/", views.convert_lead, name="convert"),
    path("<int:pk>/", views.client_detail, name="detail"),
    path("<int:pk>/edit/", views.client_edit, name="edit"),
    path("<int:pk>/delete/", views.client_delete, name="delete"),
    path("<int:pk>/contacts/add/", views.contact_add, name="contact_add"),
    path("contacts/<int:pk>/", views.contact_edit, name="contact_edit"),
    path("packages/", views.package_list, name="packages"),
    path("packages/new/", views.package_edit, name="package_create"),
    path("packages/<int:pk>/", views.package_edit, name="package_edit"),
    path("packages/<int:pk>/delete/", views.package_delete, name="package_delete"),
]
