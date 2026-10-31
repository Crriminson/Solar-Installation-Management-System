"""URL routes for F04."""

from django.urls import path

from .views import (
    LineCreateView,
    LineDetailView,
    PackageDetailView,
    PackageListCreateView,
    ProductDetailView,
    ProductListCreateView,
    ProductPriceCreateView,
    VersionActivateView,
    VersionCreateView,
    VersionDetailView,
    WarrantyPolicyListView,
)

urlpatterns = [
    path("catalogue/products/", ProductListCreateView.as_view(), name="product-list"),
    path("catalogue/products/<int:pk>/", ProductDetailView.as_view(), name="product-detail"),
    path("catalogue/products/<int:pk>/prices/", ProductPriceCreateView.as_view(), name="product-prices"),
    path("catalogue/warranty-policies/", WarrantyPolicyListView.as_view(), name="warranty-policies"),
    path("catalogue/packages/", PackageListCreateView.as_view(), name="package-list"),
    path("catalogue/packages/<int:pk>/", PackageDetailView.as_view(), name="package-detail"),
    path("catalogue/packages/<int:pk>/versions/", VersionCreateView.as_view(), name="version-create"),
    path("catalogue/versions/<int:pk>/", VersionDetailView.as_view(), name="version-detail"),
    path("catalogue/versions/<int:pk>/lines/", LineCreateView.as_view(), name="line-create"),
    path("catalogue/versions/<int:pk>/activate/", VersionActivateView.as_view(), name="version-activate"),
    path("catalogue/lines/<int:pk>/", LineDetailView.as_view(), name="line-detail"),
]
