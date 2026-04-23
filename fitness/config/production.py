from .base import *  # noqa: F403,F401


# --------------------
# Production (Railway)
# --------------------

# Production must run with DEBUG off.
DEBUG = env_bool("DEBUG", default=False)  # noqa: F405

# Ensure hosts are provided via env in production.
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", default="")  # noqa: F405

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Railway runs behind a proxy; ensure Django knows the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Browser security headers (basic defaults)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", default=31536000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)  # noqa: F405
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", default=True)  # noqa: F405
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Optional: if you host the app on a different origin for CSRF.
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", default="")  # noqa: F405

# WhiteNoise tweaks for production
WHITENOISE_USE_FINDERS = False

# Production: use manifest-based storage (requires `collectstatic` during deploy).
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

