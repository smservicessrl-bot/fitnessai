"""
URL configuration for fitness project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from accounts import views as account_views

admin.site.site_header = "FitnessAI adminisztráció"
admin.site.site_title = "FitnessAI"
admin.site.index_title = "Kezdőlap"


urlpatterns = [
    path("", account_views.landing, name="home"),
    path("accounts/", include("accounts.urls")),
    path("app/", include("members.app_urls")),
    path("app/workouts/", include(("workouts.urls_app", "app_workouts"), namespace="app_workouts")),
    path("admin/", admin.site.urls),
    path("members/", include("members.urls")),
    path("members/<int:member_id>/workouts/", include("workouts.urls")),
]
