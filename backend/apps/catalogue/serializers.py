"""
Catalogue serializers (F04).

Purchase cost is removed from responses unless the viewer may see it,
so it never reaches a browser for someone it is hidden from.
"""

from django.utils import timezone
from rest_framework import serializers

from .models import (
    PackageLine,
    PackageTemplate,
    PackageVersion,
    Product,
    ProductPrice,
    QuantityBasis,
    WarrantyPolicy,
)
from .permissions import can_view_costs


def _viewer_sees_costs(serializer):
    return can_view_costs(serializer.context["request"].user)


class WarrantyPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = WarrantyPolicy
        fields = ["id", "name", "duration_months"]


class ProductPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPrice
        fields = [
            "id", "selling_price_excl_tax", "purchase_cost_excl_tax",
            "effective_from", "created_at",
        ]
        read_only_fields = ["created_at"]
        # The check runs in validate(), with the product from the URL.
        validators = []

    def to_representation(self, price):
        data = super().to_representation(price)
        if not _viewer_sees_costs(self):
            data.pop("purchase_cost_excl_tax")
        return data

    def validate_effective_from(self, value):
        """Prices only change going forward, so past quotes stay explainable."""
        if value < timezone.localdate():
            raise serializers.ValidationError("A new price cannot start in the past.")
        return value

    def validate(self, data):
        product = self.context["product"]
        if product.prices.filter(effective_from=data["effective_from"]).exists():
            raise serializers.ValidationError(
                {"effective_from": "This product already has a price from that date."}
            )
        return data


class ProductSerializer(serializers.ModelSerializer):
    warranty_policy_name = serializers.CharField(
        source="warranty_policy.name", default="", read_only=True
    )
    current_price = serializers.SerializerMethodField()
    prices = ProductPriceSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "description", "category", "tracking_method",
            "unit", "stocking_quantity", "gst_rate_percent", "warranty_policy",
            "warranty_policy_name", "rated_power_w", "storage_kwh",
            "nominal_voltage_v", "is_repair_part", "is_active",
            "current_price", "prices",
        ]

    def get_current_price(self, product):
        price = product.current_price()
        return ProductPriceSerializer(price, context=self.context).data if price else None


class PackageLineSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit = serializers.CharField(source="product.unit", read_only=True)

    class Meta:
        model = PackageLine
        fields = ["id", "product", "sku", "product_name", "unit", "basis", "quantity", "notes"]

    def validate(self, data):
        """A calculated line never stores a typed quantity."""
        basis = data.get("basis", getattr(self.instance, "basis", QuantityBasis.FIXED))
        if basis != QuantityBasis.FIXED:
            data["quantity"] = None
        return data


class PackageVersionSerializer(serializers.ModelSerializer):
    lines = PackageLineSerializer(many=True, read_only=True)
    is_editable = serializers.BooleanField(read_only=True)
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.get_full_name", default="", read_only=True
    )

    class Meta:
        model = PackageVersion
        fields = [
            "id", "version_number", "status", "is_editable", "cable_waste_factor",
            "cable_termination_buffer_m", "battery_depth_of_discharge", "notes",
            "reviewed_by_name", "reviewed_at", "created_at", "lines",
        ]
        read_only_fields = ["version_number", "status", "reviewed_at", "created_at"]


class PackageTemplateSerializer(serializers.ModelSerializer):
    """A template in a list, with what quotations would use today."""

    active_version_number = serializers.SerializerMethodField()
    has_draft = serializers.SerializerMethodField()

    class Meta:
        model = PackageTemplate
        fields = [
            "id", "kind", "capacity_kw", "name",
            "active_version_number", "has_draft",
        ]

    def get_active_version_number(self, template):
        active = template.active_version
        return active.version_number if active else None

    def get_has_draft(self, template) -> bool:
        return any(version.is_editable for version in template.versions.all())

    def validate(self, data):
        PackageTemplate(**data).clean()
        return data


class PackageTemplateDetailSerializer(PackageTemplateSerializer):
    """A template with every version, newest first."""

    versions = PackageVersionSerializer(many=True, read_only=True)

    class Meta(PackageTemplateSerializer.Meta):
        fields = [*PackageTemplateSerializer.Meta.fields, "versions"]
