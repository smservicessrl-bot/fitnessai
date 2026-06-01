import re
import uuid

from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from members.models import MemberProfile
from members.phone import normalize_phone

User = get_user_model()

_PIN_RE = re.compile(r"^\d{4}$")


class RegistrationForm(forms.Form):
    full_name = forms.CharField(
        label=_("Full name"),
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control form-control-lg", "autocomplete": "name"}),
    )
    email = forms.EmailField(
        label=_("Email"),
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control form-control-lg", "autocomplete": "email"}),
    )
    phone = forms.CharField(
        label=_("Phone (optional)"),
        required=False,
        max_length=32,
        widget=forms.TextInput(
            attrs={"class": "form-control form-control-lg", "autocomplete": "tel", "inputmode": "tel"}
        ),
    )
    pin = forms.CharField(
        label=_("PIN (4 digits)"),
        min_length=4,
        max_length=4,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg text-center",
                "autocomplete": "new-password",
                "inputmode": "numeric",
                "pattern": r"\d{4}",
                "maxlength": "4",
            }
        ),
    )
    pin_confirm = forms.CharField(
        label=_("Confirm PIN"),
        min_length=4,
        max_length=4,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg text-center",
                "autocomplete": "new-password",
                "inputmode": "numeric",
                "pattern": r"\d{4}",
                "maxlength": "4",
            }
        ),
    )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        return email or ""

    def clean_phone(self):
        return (self.cleaned_data.get("phone") or "").strip()

    def clean(self):
        cleaned = super().clean()
        email = (cleaned.get("email") or "").strip()
        phone_raw = (cleaned.get("phone") or "").strip()
        phone_n = normalize_phone(phone_raw)
        pin = cleaned.get("pin")
        pin_confirm = cleaned.get("pin_confirm")
        if pin and pin_confirm and pin != pin_confirm:
            self.add_error("pin_confirm", _("The PINs do not match."))
        if pin and not _PIN_RE.match(pin):
            self.add_error("pin", _("PIN must be exactly 4 digits."))
        if email and User.objects.filter(email__iexact=email).exists():
            self.add_error("email", _("This email address is already registered."))
        if phone_n and MemberProfile.objects.filter(phone_normalized=phone_n).exists():
            self.add_error("phone", _("This phone number is already registered."))
        return cleaned

    def clean_pin(self):
        pin = self.cleaned_data.get("pin") or ""
        if pin and not _PIN_RE.match(pin):
            raise forms.ValidationError(_("PIN must be exactly 4 digits."))
        return pin

    def clean_pin_confirm(self):
        return self.cleaned_data.get("pin_confirm") or ""

    @transaction.atomic
    def save(self):
        email = (self.cleaned_data["email"] or "").strip()
        phone_raw = (self.cleaned_data["phone"] or "").strip()
        phone_n = normalize_phone(phone_raw)
        pin = self.cleaned_data["pin"]

        username = f"m_{uuid.uuid4().hex}"
        # Phone-only accounts need a unique placeholder email (User.email is used for lookups).
        user_email = email if email else f"{username}@member.local"
        user = User(username=username, email=user_email, is_staff=False, is_superuser=False)
        user.set_password(pin)
        user.save()

        MemberProfile.objects.create(
            user=user,
            full_name=self.cleaned_data["full_name"].strip(),
            phone=phone_raw,
            phone_normalized=phone_n,
        )
        return user


class LoginForm(forms.Form):
    identifier = forms.CharField(
        label=_("Email, phone or username"),
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "autocomplete": "username",
                "autocapitalize": "none",
            }
        ),
    )
    password = forms.CharField(
        label=_("PIN or password"),
        max_length=128,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg",
                "autocomplete": "current-password",
            }
        ),
    )
