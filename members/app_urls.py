from django.urls import path

from . import views

app_name = "member_app"

urlpatterns = [
    path("", views.member_dashboard, name="dashboard"),
    path("profile/edit/", views.member_profile_edit, name="profile_edit"),
]
