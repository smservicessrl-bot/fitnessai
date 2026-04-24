import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse


# Directory containing `manage.py` (project root)
BASE_DIR = Path(__file__).resolve().parents[2]


def env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None or str(val).strip() == "":
        return default
    return int(val)


def env_list(name: str, default: str = "") -> list[str]:
    """
    Comma-separated list for env vars, e.g.:
      ALLOWED_HOSTS=example.com,api.example.com
    """
    raw = os.environ.get(name, default) or ""
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def parse_database_url(database_url: str) -> dict:
    """
    Minimal `DATABASE_URL` parser (expects postgres://... or postgresql://...).
    Keeps dependencies minimal (no dj-database-url).
    """
    parsed = urlparse(database_url)

    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError(f"Unsupported DATABASE_URL scheme: {parsed.scheme}")

    dbname = (parsed.path or "").lstrip("/")
    query = parse_qs(parsed.query)
    options = {}

    # Railway often includes sslmode=require; keep it if present.
    if "sslmode" in query and query["sslmode"]:
        options["sslmode"] = query["sslmode"][0]

    db: dict = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": dbname,
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or 5432),
    }
    if options:
        db["OPTIONS"] = options
    return db


# --------------------
# Core settings (shared)
# --------------------

# SECURITY WARNING: keep the secret key used in production secret!
# Local default exists for convenience; Railway must provide SECRET_KEY.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")

# Local vs production DEBUG comes from env; local.py/production.py override defaults.
DEBUG = env_bool("DEBUG", default=False)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", default="localhost,127.0.0.1,testserver")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # htmx integration
    "django_htmx",
    # MVP apps (created by you)
    "users",
    "accounts",
    "members",
    "exercises",
    "workouts",
    "ai_engine",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files in production without requiring a separate server.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # htmx adds request.htmx details for views/middleware.
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "fitness.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "fitness.wsgi.application"
ASGI_APPLICATION = "fitness.asgi.application"


# --------------------
# Database (local sqlite, Railway/Postgres via DATABASE_URL)
# --------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL:
    DATABASES = {"default": parse_database_url(DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# --------------------
# Auth / validation
# --------------------

AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailPhonePinBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# LocMem cache for login rate limiting (PIN brute-force mitigation).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "fitnessai-cache",
    }
}


# --------------------
# Internationalization
# --------------------

LANGUAGE_CODE = "hu"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --------------------
# Static files (WhiteNoise)
# --------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Local dev: avoid manifest-based storage so you don't need to run `collectstatic`
# just to render pages with `{% static %}`.
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# --------------------
# App defaults
# --------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------
# Optional app env vars
# --------------------

# `ai_engine` can read this from env; don't commit API keys.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# SKIP_LLM=1 — skip OpenAI refinement; deterministic plan only (fastest).
# OPENAI_MAX_OUTPUT_TOKENS_DEFAULT — cap completion size (default 4096 in generator).

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"

