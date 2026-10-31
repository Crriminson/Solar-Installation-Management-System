"""
Root URL configuration.

Every API route lives under /api/v1/. One line per feature area.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.accounts.urls")),    # staff sign-in
    path("api/v1/", include("apps.customers.urls")),   # F01, F02
    path("api/v1/", include("apps.surveys.urls")),     # F03
    path("api/v1/", include("apps.catalogue.urls")),   # F04
    path("api/v1/", include("apps.quotations.urls")),  # F05, F06
    path("api/v1/", include("apps.orders.urls")),      # F07
    path("api/v1/", include("apps.inventory.urls")),   # F08
    path("api/v1/", include("apps.fulfilment.urls")),  # F09
]
