from django.urls import path

from . import views

app_name = "workouts"

urlpatterns = [
    path("session/new/", views.workout_session_input, name="workout_session_input"),
    path("history/", views.workout_history, name="workout_history"),
    path("plans/<int:plan_id>/", views.workout_plan_detail, name="workout_plan_detail"),
    path("plans/<int:plan_id>/ask/", views.workout_plan_ask, name="workout_plan_ask"),
    path("plans/<int:plan_id>/print/", views.workout_plan_print, name="workout_plan_print"),
    path("plans/<int:plan_id>/download/pdf/", views.workout_plan_download_pdf, name="workout_plan_download_pdf"),
    path("plans/<int:plan_id>/download/word/", views.workout_plan_download_word, name="workout_plan_download_word"),
    path("plans/<int:plan_id>/qr.png/", views.workout_plan_qr_png, name="workout_plan_qr_png"),
    path("plans/<int:plan_id>/download/csv/", views.workout_plan_download_csv, name="workout_plan_download_csv"),
]

