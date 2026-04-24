from django.urls import path

from . import views

app_name = "members"

urlpatterns = [
    path("", views.member_list, name="member_list"),
    path("uploaded-plans/<int:pk>/delete/", views.uploaded_workout_plan_delete, name="uploaded_workout_plan_delete"),
    path("new/", views.member_create, name="member_create"),
    path("equipments/", views.equipment_list, name="equipment_list"),
    path("equipments/<int:pk>/delete/", views.equipment_delete, name="equipment_delete"),
    path("exercises/new/", views.exercise_create, name="exercise_create"),
    path("<int:pk>/edit/", views.member_edit, name="member_edit"),
]

