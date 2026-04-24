from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from accounts.forms import LoginForm, RegistrationForm
from accounts.rate_limit import clear_login_failures, is_login_blocked, record_login_failure
from members.permissions import member_profile_for_user

ONBOARDING_SESSION_KEY = "require_profile_setup"


def landing(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect(reverse("members:member_list"))
        if member_profile_for_user(request.user):
            return redirect(reverse("member_app:dashboard"))
    return render(request, "accounts/landing.html")


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect(reverse("home"))
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
            request.session[ONBOARDING_SESSION_KEY] = True
            messages.success(request, "Sikeres regisztráció.")
            return redirect(reverse("member_app:profile_edit"))
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect(reverse("home"))
    if request.method == "POST":
        form = LoginForm(request.POST)
        identifier = (request.POST.get("identifier") or "").strip()
        if form.is_valid():
            if is_login_blocked(request, identifier):
                messages.error(
                    request,
                    "Túl sok sikertelen próbálkozás. Próbáld újra később.",
                )
            else:
                user = authenticate(
                    request,
                    username=identifier,
                    password=form.cleaned_data["password"],
                )
                if user is not None:
                    is_first_login = user.last_login is None
                    clear_login_failures(request, identifier)
                    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
                    messages.success(request, "Sikeres bejelentkezés.")
                    if not user.is_staff and is_first_login and member_profile_for_user(user):
                        request.session[ONBOARDING_SESSION_KEY] = True
                        return redirect(reverse("member_app:profile_edit"))
                    next_url = request.GET.get("next") or reverse("home")
                    return redirect(next_url)
                record_login_failure(request, identifier)
                messages.error(request, "Hibás e-mail/telefon vagy PIN.")
        else:
            if identifier and is_login_blocked(request, identifier):
                messages.error(
                    request,
                    "Túl sok sikertelen próbálkozás. Próbáld újra később.",
                )
    else:
        form = LoginForm()
    return render(request, "accounts/login.html", {"form": form})


@require_POST
@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "Kijelentkeztél.")
    return redirect(reverse("home"))
