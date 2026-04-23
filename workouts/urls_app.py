from django.urls import path

from . import views

app_name = "app_workouts"

urlpatterns = [
    path("session/new/", views.app_workout_session_input, name="workout_session_input"),
    path("history/", views.app_workout_history, name="workout_history"),
    path("plans/<int:plan_id>/", views.app_workout_plan_detail, name="workout_plan_detail"),
    path("plans/<int:plan_id>/ask/", views.app_workout_plan_ask, name="workout_plan_ask"),
    path("plans/<int:plan_id>/print/", views.app_workout_plan_print, name="workout_plan_print"),
    path("plans/<int:plan_id>/download/pdf/", views.app_workout_plan_download_pdf, name="workout_plan_download_pdf"),
    path("plans/<int:plan_id>/qr.png/", views.app_workout_plan_qr_png, name="workout_plan_qr_png"),
    path("plans/<int:plan_id>/download/csv/", views.app_workout_plan_download_csv, name="workout_plan_download_csv"),
]
