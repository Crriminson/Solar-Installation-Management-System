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

DEFAULT_PAGE_SIZE = 25                                       # rows per page
MAX_PAGE_SIZE = 100                                          # hard ceiling

# How often one anonymous client may submit the public enquiry form.
# Raise it in .env for demos: every local submission shares one IP.
PUBLIC_ENQUIRY_RATE = os.getenv("PUBLIC_ENQUIRY_RATE", "20/hour")


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
    "apps.accounts",
    "apps.customers",
    "apps.surveys",
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
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": DEFAULT_PAGE_SIZE,
    "DEFAULT_THROTTLE_RATES": {"public_enquiry": PUBLIC_ENQUIRY_RATE},
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
