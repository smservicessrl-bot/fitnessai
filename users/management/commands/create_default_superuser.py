from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the default deployment superuser."

    def handle(self, *args, **options):
        username = "Admin"
        password = "QweAsd789"
        email = "admin@fitnessai.local"

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        changed = False
        if not user.is_staff:
            user.is_staff = True
            changed = True
        if not user.is_superuser:
            user.is_superuser = True
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if not user.email:
            user.email = email
            changed = True

        if created or not user.check_password(password):
            user.set_password(password)
            changed = True

        if changed:
            user.save()

        if created:
            self.stdout.write(self.style.SUCCESS("Default superuser created: Admin"))
        elif changed:
            self.stdout.write(self.style.SUCCESS("Default superuser updated: Admin"))
        else:
            self.stdout.write(self.style.WARNING("Default superuser already up to date: Admin"))
