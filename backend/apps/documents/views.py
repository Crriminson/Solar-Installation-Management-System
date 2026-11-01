"""
F19 endpoints: ask for a document, then download it.

Documents are generated, never uploaded, so there is no create form.
Generation is a POST because it writes; downloading is a GET that
streams the stored file. Files live outside any public directory and
every download is authorised per request (spec.md section 10).
"""

from django.http import FileResponse
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import BoundedPagination, StaffAccess
from apps.installations.models import InstallationReport
from apps.orders.models import Invoice, Payment
from apps.quotations.models import QuoteRevision

from . import services
from .models import Document
from .serializers import DocumentSerializer

# Who may ask for paperwork. Anyone who can already see the record can
# have the document for it; cost and margin never appear on these.
DOCUMENT_ROLES = (
    Role.SALES, Role.OPERATIONS_MANAGER, Role.FINANCE,
    Role.SUPPORT, Role.WAREHOUSE, Role.DIRECTOR,
)


class DocumentAccess(StaffAccess):
    def has_permission(self, request, view):
        view.read_roles = DOCUMENT_ROLES
        view.write_roles = DOCUMENT_ROLES
        return super().has_permission(request, view)


class DocumentList(ListAPIView):
    """Every document, newest first, filterable by the record it describes."""

    permission_classes = [DocumentAccess]
    serializer_class = DocumentSerializer
    pagination_class = BoundedPagination

    def get_queryset(self):
        documents = Document.objects.select_related("generated_by")
        for field in ("quotation", "invoice", "payment", "installation"):
            value = self.request.query_params.get(field)
            if value:
                documents = documents.filter(**{field: value})
        kind = self.request.query_params.get("kind")
        return documents.filter(kind=kind) if kind else documents


class DocumentGenerate(APIView):
    """
    Build the document for a record, or hand back the one already built.

    Regenerating reproduces the stored snapshot, not current catalogue
    data, so the same source always yields the same file.
    """

    permission_classes = [DocumentAccess]

    BUILDERS = {
        "quotation": (QuoteRevision, services.generate_quotation),
        "invoice": (Invoice, services.generate_invoice),
        "receipt": (Payment, services.generate_receipt),
        "handover": (InstallationReport, services.generate_handover),
    }

    def post(self, request, kind, pk):
        entry = self.BUILDERS.get(kind)
        if entry is None:
            return Response({"detail": f"There is no {kind} document."}, status=400)

        model, build = entry
        record = model.objects.filter(pk=pk).first()
        if record is None:
            return Response({"detail": "That record does not exist."}, status=404)

        document = build(record, request.user)
        return Response(DocumentSerializer(document).data, status=201)


class DocumentDownload(APIView):
    """Streams the stored file. Never regenerates: the customer and the
    office must be looking at the same bytes (spec.md F19)."""

    permission_classes = [DocumentAccess]

    def get(self, request, pk):
        document = Document.objects.filter(pk=pk).first()
        if document is None:
            return Response({"detail": "That document does not exist."}, status=404)

        return FileResponse(
            document.file.open("rb"),
            as_attachment=True,
            filename=f"{document.kind}-{document.reference}.pdf",
            content_type="application/pdf",
        )
