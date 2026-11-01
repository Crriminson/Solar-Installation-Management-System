"""
Django settings.

Read the first two sections. Everything below them is standard Django
configuration that rarely changes.

Secrets come from a .env file that is never committed. .env.example
lists every key with a safe placeholder.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# ============================================================
# 1. Business settings — the values you are likely to change
# ============================================================

# Day, week and month boundaries use this. Timestamps are stored in UTC
# and converted to this zone for display. See spec.md section 6.
BUSINESS_TIMEZONE = "Asia/Kolkata"

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024                     # 10 MB per file
ALLOWED_UPLOAD_TYPES = ["application/pdf", "image/jpeg", "image/png"]
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png"]
MAX_IMAGE_DIMENSION_PX = 8000                                # longest side
MAX_PHOTOS_PER_RECORD = 20

DEFAULT_PAGE_SIZE = 10                                       # rows per page (scope log 7)
MAX_PAGE_SIZE = 100                                          # hard ceiling

# How often one anonymous client may submit the public enquiry form.
# Raise it in .env for demos: every local submission shares one IP.
PUBLIC_ENQUIRY_RATE = os.getenv("PUBLIC_ENQUIRY_RATE", "20/hour")

# How often one client may try to sign in.
LOGIN_RATE = os.getenv("LOGIN_RATE", "10/minute")

# Proxies in front of Django. Rate limits only trust this many entries
# in X-Forwarded-For; without it a client can forge the header and get a
# fresh limit on every request. Zero means use the connection's address.
TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))


# ============================================================
# Telegram (F16)
#
# The token is a credential: it is read here and must never be logged,
# echoed in an error, or written to an audit entry. With no token the
# worker uses a fake transport, so the app runs and the tests pass on a
# machine that has never spoken to Telegram.
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")

# Where a customer's phone reaches this app, for links sent to them.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# How long a staff-issued linking token is good for, and how long a
# signing or confirmation link lives before it stops working.
TELEGRAM_LINK_TOKEN_MINUTES = int(os.getenv("TELEGRAM_LINK_TOKEN_MINUTES", "30"))
CUSTOMER_LINK_HOURS = int(os.getenv("CUSTOMER_LINK_HOURS", "72"))

# Outbox delivery: how many times to retry a message, and the base of
# the backoff between attempts.
OUTBOX_MAX_ATTEMPTS = int(os.getenv("OUTBOX_MAX_ATTEMPTS", "6"))
OUTBOX_BACKOFF_SECONDS = int(os.getenv("OUTBOX_BACKOFF_SECONDS", "20"))


# ============================================================
# Staff assistant (F21)
#
# Answers run on a local Ollama server, so staff questions stay on this
# machine. With it stopped the app runs normally and the assistant says
# it is offline. Never point these at a "-cloud" model.
# ============================================================

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
ASSISTANT_CHAT_MODEL = os.getenv("ASSISTANT_CHAT_MODEL", "qwen2.5:3b")
ASSISTANT_EMBED_MODEL = os.getenv("ASSISTANT_EMBED_MODEL", "nomic-embed-text")

# Questions per staff member. Every one occupies the one model.
ASSISTANT_RATE = os.getenv("ASSISTANT_RATE", "20/minute")


# ============================================================
# 2. Environment — differs per machine, comes from .env
# ============================================================

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "solar_db"),
        "USER": os.getenv("POSTGRES_USER", "solar_app"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}


# ============================================================
# 3. Our apps — add a line here for each new feature area
# ============================================================

OUR_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.customers",
    "apps.surveys",
    "apps.catalogue",
    "apps.quotations",
    "apps.subsidies",
    "apps.orders",
    "apps.inventory",
    "apps.fulfilment",
    "apps.scheduling",
    "apps.installations",
    "apps.warranties",
    "apps.documents",
    "apps.messaging",
    "apps.support",
    "apps.costing",
    "apps.dashboard",
    "apps.assistant",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
] + OUR_APPS

# Staff are the only users. Set before the first migration; Django
# cannot swap the user model cleanly afterwards.
AUTH_USER_MODEL = "accounts.User"


# ============================================================
# 4. API behaviour
# ============================================================

REST_FRAMEWORK = {
    # Browser sessions, not tokens - same-origin app, no mobile client.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Everything requires login unless a view opts out, such as the
    # public enquiry form.
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.core.api.ActiveStaff",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.api.BoundedPagination",
    "PAGE_SIZE": DEFAULT_PAGE_SIZE,
    "DEFAULT_THROTTLE_RATES": {
        "public_enquiry": PUBLIC_ENQUIRY_RATE,
        "login": LOGIN_RATE,
        "assistant": ASSISTANT_RATE,
    },
    "NUM_PROXIES": TRUSTED_PROXY_COUNT,
}


# ============================================================
# 5. Files
# ============================================================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Private. Uploads are served through authorized views, never directly,
# because they hold customer documents. See spec.md section 10.
MEDIA_ROOT = BASE_DIR / "private_media"


# ============================================================
# 6. Security
# ============================================================

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Secure cookies need HTTPS, which we only have in deployment.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG


# ============================================================
# 7. Django defaults — standard setup, rarely changed
# ============================================================

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"        # Stored in UTC; displayed in BUSINESS_TIMEZONE.
USE_I18N = True
USE_TZ = True

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{validator}"}
    for validator in [
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    ]
]
