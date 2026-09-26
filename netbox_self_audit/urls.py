from django.urls import path

from . import views

app_name = "netbox_self_audit"

urlpatterns = [
    path("", views.audit_view, name="audit"),
    path("rules/", views.rules_view, name="rules"),
    path("settings/", views.settings_view, name="settings"),
    path("email/", views.email_view, name="email"),
    path("health/", views.health_view, name="health"),
]
