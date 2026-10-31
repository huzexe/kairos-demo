from django.urls import path

from . import views

app_name = "pipeline"

urlpatterns = [
    path("", views.board, name="board"),
    path("list/", views.lead_list, name="list"),
    path("leads/new/", views.lead_create, name="lead_create"),
    path("leads/bulk/", views.lead_bulk, name="lead_bulk"),
    path("leads/<int:pk>/", views.lead_detail, name="lead_detail"),
    path("leads/<int:pk>/edit/", views.lead_edit, name="lead_edit"),
    path("leads/<int:pk>/delete/", views.lead_delete, name="lead_delete"),
    path("leads/<int:pk>/move/", views.lead_move, name="lead_move"),
    path("leads/<int:pk>/junk/", views.lead_junk, name="lead_junk"),
]
