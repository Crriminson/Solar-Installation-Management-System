"""Fast password hashing for isolated Django tests; PostgreSQL and production auth paths are unchanged."""

from .settings import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
