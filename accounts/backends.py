from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from members.models import MemberProfile
from members.phone import normalize_phone

User = get_user_model()


class EmailPhonePinBackend(BaseBackend):
    """
    Authenticate with email or phone identifier + PIN (stored as User.password hash).
    Staff may still use the admin with username/password via ModelBackend.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or password is None:
            return None
        identifier = str(username).strip()
        if not identifier:
            return None

        user = User.objects.filter(email__iexact=identifier).first()
        if user is None:
            n = normalize_phone(identifier)
            if n:
                mp = MemberProfile.objects.filter(phone_normalized=n).select_related("user").first()
                if mp is not None and mp.user_id is not None:
                    user = mp.user
        if user is None:
            # Staff / superuser: username + password at the same login form as members (PIN).
            user = User.objects.filter(username__iexact=identifier).first()

        if user is None:
            return None

        if user.check_password(password):
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
