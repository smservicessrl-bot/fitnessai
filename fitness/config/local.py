from .base import *  # noqa: F403,F401


# --------------------
# Local development
# --------------------

# Local dev defaults: allow localhost and enable DEBUG if not explicitly set.
DEBUG = env_bool("DEBUG", default=True)  # noqa: F405
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", default="localhost,127.0.0.1,testserver")  # noqa: F405

# CSRF cookies should be non-secure locally.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

