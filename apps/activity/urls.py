from django.urls import path

from . import views

app_name = "activity"

urlpatterns = [
    path("follow-ups/", views.follow_up_list, name="follow_ups"),
    path("follow-ups/<int:pk>/", views.follow_up_edit, name="follow_up_edit"),
    path("follow-ups/<int:pk>/done/", views.follow_up_done, name="follow_up_done"),
    path("<str:kind>/<int:pk>/log/", views.activity_add, name="activity_add"),
    path("<str:kind>/<int:pk>/follow-up/", views.follow_up_add, name="follow_up_add"),
    path("timeline/<int:pk>/", views.activity_edit, name="activity_edit"),
]
