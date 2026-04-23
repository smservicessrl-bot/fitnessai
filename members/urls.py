from django.urls import path

from . import views

app_name = "members"

urlpatterns = [
    path("", views.member_list, name="member_list"),
    path("new/", views.member_create, name="member_create"),
    path("<int:pk>/edit/", views.member_edit, name="member_edit"),
]

