from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.core import views as core_views
from apps.dashboard import views as dashboard_views
from apps.pipeline import views as pipeline_views

urlpatterns = [
    path("", dashboard_views.dashboard, name="home"),
    path("setup/", core_views.setup, name="setup"),
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("settings/", core_views.settings_agency, name="settings_agency"),
    path("settings/account/", core_views.settings_account, name="settings_account"),
    path("settings/invoices/", core_views.settings_invoices, name="settings_invoices"),
    path("settings/<slug:kind>/", pipeline_views.settings_list, name="settings_list"),
    path("pipeline/", include("apps.pipeline.urls")),
    path("clients/", include("apps.clients.urls")),
    path("activity/", include("apps.activity.urls")),
    path("invoices/", include("apps.invoices.urls")),
    path("admin/", admin.site.urls),
    # Uploaded files (the agency logo). Kairos runs only on this computer, so Django
    # serves them itself — and like every page, only to the signed-in owner.
    path("media/<path:path>", core_views.media, name="media"),
]
