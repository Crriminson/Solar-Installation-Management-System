"""
Catalogue API (F04).

    GET, POST  /api/v1/catalogue/products/
    GET, PATCH /api/v1/catalogue/products/<id>/
    POST       /api/v1/catalogue/products/<id>/prices/
    GET        /api/v1/catalogue/warranty-policies/
    GET, POST  /api/v1/catalogue/packages/
    GET        /api/v1/catalogue/packages/<id>/
    POST       /api/v1/catalogue/packages/<id>/versions/
    PATCH      /api/v1/catalogue/versions/<id>/
    POST       /api/v1/catalogue/versions/<id>/lines/
    PATCH, DELETE /api/v1/catalogue/lines/<id>/
    POST       /api/v1/catalogue/versions/<id>/activate/

Reading is open to staff. Writing needs an operations manager, and going
live needs an administrator. The models refuse edits to a reviewed
version, so the same rule applies however a change is triggered.
"""

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import F
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError as ApiValidationError

from .models import PackageLine, PackageTemplate, PackageVersion, Product, WarrantyPolicy
from .permissions import CatalogueWriteAccess, can_review_packages
from apps.core.api import ActiveStaff, check_revision
from .serializers import (
    PackageLineSerializer,
    PackageTemplateDetailSerializer,
    PackageTemplateSerializer,
    PackageVersionSerializer,
    ProductPriceSerializer,
    ProductSerializer,
    WarrantyPolicySerializer,
)


def refused(exception):
    """A model's refusal as a 400 naming every problem it found."""
    return Response(
        {"detail": exception.messages[0], "problems": exception.messages},
        status=status.HTTP_400_BAD_REQUEST,
    )


# ============================================================
# Products
# ============================================================

def products_with_prices():
    """Joined up front, so a page does not run a query per product."""
    return Product.objects.select_related("warranty_policy").prefetch_related("prices")


class ProductListCreateView(generics.ListCreateAPIView):
    """
    Products. Takes ?search=, ?category=, ?repair=true and ?active=true.

    ?picker=true returns every match unpaged, to fill a product picker.
    """

    serializer_class = ProductSerializer
    permission_classes = [CatalogueWriteAccess]

    def paginate_queryset(self, queryset):
        if self.request.query_params.get("picker") == "true":
            return None
        return super().paginate_queryset(queryset)

    def get_queryset(self):
        queryset = products_with_prices()
        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(sku__icontains=search) | Q(name__icontains=search)
            )

        if params.get("category"):
            queryset = queryset.filter(category=params["category"])

        if params.get("repair") == "true":
            queryset = queryset.filter(is_repair_part=True)

        if params.get("active") == "true":
            queryset = queryset.filter(is_active=True)

        return queryset


class ProductDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [CatalogueWriteAccess]
    queryset = products_with_prices()
    http_method_names = ["get", "patch", "head", "options"]

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        product = get_object_or_404(Product.objects.select_for_update(), pk=kwargs["pk"])
        check_revision(product, request.data)
        serializer = self.get_serializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(revision=product.revision + 1)
        return Response(serializer.data)


class ProductPriceCreateView(generics.CreateAPIView):
    """Adds a price. Existing prices are never edited."""

    serializer_class = ProductPriceSerializer
    permission_classes = [CatalogueWriteAccess]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["product"] = get_object_or_404(Product, pk=self.kwargs["pk"])
        return context

    @transaction.atomic
    def perform_create(self, serializer):
        product = Product.objects.select_for_update().get(pk=self.kwargs["pk"])
        if product.prices.filter(effective_from=serializer.validated_data["effective_from"]).exists():
            raise ApiValidationError({"effective_from": ["This product already has a price from that date."]})
        serializer.save(
            product=product, created_by=self.request.user
        )


class WarrantyPolicyListView(generics.ListAPIView):
    """Short, fixed list for a picker, so it is not paginated."""

    serializer_class = WarrantyPolicySerializer
    permission_classes = [ActiveStaff]
    queryset = WarrantyPolicy.objects.all()
    pagination_class = None


# ============================================================
# Package templates
# ============================================================

class PackageListCreateView(generics.ListCreateAPIView):
    serializer_class = PackageTemplateSerializer
    permission_classes = [CatalogueWriteAccess]
    queryset = PackageTemplate.objects.prefetch_related("versions")


class PackageDetailView(generics.RetrieveAPIView):
    serializer_class = PackageTemplateDetailSerializer
    permission_classes = [ActiveStaff]

    def get_queryset(self):
        lines = PackageLine.objects.select_related("product")
        versions = PackageVersion.objects.select_related(
            "reviewed_by"
        ).prefetch_related(Prefetch("lines", queryset=lines))

        return PackageTemplate.objects.prefetch_related(
            Prefetch("versions", queryset=versions)
        )


class VersionCreateView(APIView):
    """Opens a draft, copied from the newest version."""

    permission_classes = [CatalogueWriteAccess]

    def post(self, request, pk):
        template = get_object_or_404(PackageTemplate, pk=pk)

        try:
            version = template.start_new_version(request.user)
        except ValidationError as exc:
            return refused(exc)

        return Response(
            PackageVersionSerializer(version).data, status=status.HTTP_201_CREATED
        )


class VersionDetailView(generics.UpdateAPIView):
    """Changes a draft's figures. The model refuses a reviewed version."""

    serializer_class = PackageVersionSerializer
    permission_classes = [CatalogueWriteAccess]
    queryset = PackageVersion.objects.all()
    http_method_names = ["patch", "options"]

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        try:
            version = lock_version(kwargs["pk"], request.data)
            serializer = self.get_serializer(version, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save(revision=version.revision + 1)
            return Response(serializer.data)
        except ValidationError as exc:
            return refused(exc)


class LineCreateView(generics.CreateAPIView):
    serializer_class = PackageLineSerializer
    permission_classes = [CatalogueWriteAccess]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        try:
            version = lock_version(kwargs["pk"], request.data)
            response = super().create(request, *args, **kwargs)
            PackageVersion.objects.filter(pk=version.pk).update(revision=F("revision") + 1)
            return response
        except ValidationError as exc:
            return refused(exc)

    def perform_create(self, serializer):
        version = get_object_or_404(PackageVersion, pk=self.kwargs["pk"])
        if version.lines.filter(product=serializer.validated_data["product"]).exists():
            raise ApiValidationError({"product": ["This product is already on the package version."]})
        serializer.save(version=version)


class LineDetailView(generics.UpdateAPIView, generics.DestroyAPIView):
    serializer_class = PackageLineSerializer
    permission_classes = [CatalogueWriteAccess]
    queryset = PackageLine.objects.select_related("product")
    http_method_names = ["patch", "delete", "options"]

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        try:
            line = self.get_object()
            version = lock_version(line.version_id, request.data)
            response = super().update(request, *args, **kwargs)
            PackageVersion.objects.filter(pk=version.pk).update(revision=F("revision") + 1)
            return response
        except ValidationError as exc:
            return refused(exc)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        try:
            line = self.get_object()
            version = lock_version(line.version_id, request.data)
            response = super().destroy(request, *args, **kwargs)
            PackageVersion.objects.filter(pk=version.pk).update(revision=F("revision") + 1)
            return response
        except ValidationError as exc:
            return refused(exc)


class VersionActivateView(APIView):
    """
    Records the review and takes the version live.

    Only an administrator, because this is what lets a template reach a
    customer. Refused with every problem listed, so they can all be
    fixed in one go.
    """

    permission_classes = [ActiveStaff]

    @transaction.atomic
    def post(self, request, pk):
        if not can_review_packages(request.user):
            return Response(
                {"detail": "Only an administrator may review a package."},
                status=status.HTTP_403_FORBIDDEN,
            )

        version = lock_version(pk, request.data)

        try:
            version.activate(request.user)
            PackageVersion.objects.filter(pk=pk).update(revision=F("revision") + 1)
            version.refresh_from_db()
        except ValidationError as exc:
            return refused(exc)

        return Response(PackageVersionSerializer(version).data)


def lock_version(pk, data):
    """Use activation's template-first lock order for edits and line writes too."""
    version = get_object_or_404(PackageVersion, pk=pk)
    PackageTemplate.objects.select_for_update().get(pk=version.template_id)
    version = PackageVersion.objects.select_for_update().get(pk=pk)
    check_revision(version, data)
    return version
