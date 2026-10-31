"""
Checks on uploaded files, per spec.md section 10.

A file's name and its declared content type are both chosen by whoever
sent it, so the type is read from the file's own opening bytes instead.
"""

from django.conf import settings
from rest_framework import serializers

BYTES_PER_MB = 1024 * 1024

# The bytes each allowed format starts with.
FILE_SIGNATURES = {
    "application/pdf": b"%PDF-",
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}

TYPE_NAMES = {
    "application/pdf": "PDF",
    "image/jpeg": "JPEG",
    "image/png": "PNG",
}


def validate_upload(uploaded_file, allowed_types=None):
    """Raises a validation error unless the file is an allowed size and type."""
    allowed_types = allowed_types or settings.ALLOWED_UPLOAD_TYPES

    if uploaded_file.size > settings.MAX_UPLOAD_SIZE_BYTES:
        limit_mb = settings.MAX_UPLOAD_SIZE_BYTES // BYTES_PER_MB
        raise serializers.ValidationError(f"Files must be {limit_mb} MB or smaller.")

    header = uploaded_file.read(max(map(len, FILE_SIGNATURES.values())))
    uploaded_file.seek(0)

    if not any(header.startswith(FILE_SIGNATURES[kind]) for kind in allowed_types):
        names = ", ".join(TYPE_NAMES[kind] for kind in allowed_types)
        raise serializers.ValidationError(f"Upload a file of type: {names}.")

    return uploaded_file
