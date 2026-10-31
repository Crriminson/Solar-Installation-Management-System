"""
Catalogue serializers (F04).

Purchase cost is removed from responses unless the viewer may see it,
so it never reaches a browser for someone it is hidden from.
"""

from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework import serializers
from apps.core.api import business_date

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
        fields = ["id", "name", "version", "duration_months"]


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
        if value < business_date():
            raise serializers.ValidationError("A new price cannot start in the past.")
        return value

    def validate(self, data):
        product = self.context["product"]
        for field in ("selling_price_excl_tax", "purchase_cost_excl_tax"):
            if data.get(field) is not None and data[field] < 0:
                raise serializers.ValidationError({field: "Enter a non-negative INR amount."})
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
            "revision",
        ]
        read_only_fields = ["revision"]

    def get_current_price(self, product):
        price = product.current_price()
        return ProductPriceSerializer(price, context=self.context).data if price else None

    def validate(self, data):
        for field in ("rated_power_w", "storage_kwh", "nominal_voltage_v"):
            if data.get(field) is not None and data[field] <= 0:
                raise serializers.ValidationError({field: "Enter a positive value."})
        if "gst_rate_percent" in data and not 0 <= data["gst_rate_percent"] <= 100:
            raise serializers.ValidationError({"gst_rate_percent": "Enter a percentage from 0 to 100."})
        return data


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
        elif data.get("quantity", getattr(self.instance, "quantity", None)) is None or data.get("quantity", getattr(self.instance, "quantity", 0)) <= 0:
            raise serializers.ValidationError({"quantity": "A fixed line needs a positive quantity."})
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
            "revision",
        ]
        read_only_fields = ["version_number", "status", "reviewed_at", "created_at", "revision"]

    def validate_battery_depth_of_discharge(self, value):
        if value is not None and not 0 < value <= 1:
            raise serializers.ValidationError("Enter a usable fraction greater than 0 and at most 1.")
        return value


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
        try:
            PackageTemplate(**data).clean()
        except ValidationError as exc:
            raise serializers.ValidationError({"capacity_kw": exc.messages})
        if data.get("capacity_kw") is not None and not 1 <= data["capacity_kw"] <= 5:
            raise serializers.ValidationError({"capacity_kw": "Supported capacity is 1–5 kW."})
        return data


class PackageTemplateDetailSerializer(PackageTemplateSerializer):
    """A template with every version, newest first."""

    versions = PackageVersionSerializer(many=True, read_only=True)

    class Meta(PackageTemplateSerializer.Meta):
        fields = [*PackageTemplateSerializer.Meta.fields, "versions"]
