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
    path("api/v1/", include("apps.scheduling.urls")),  # F10
    path("api/v1/", include("apps.installations.urls")), # F11
    path("api/v1/", include("apps.warranties.urls")),  # F12
    path("api/v1/", include("apps.documents.urls")),  # F19
    path("api/v1/", include("apps.messaging.urls")),  # F16
    path("api/v1/", include("apps.support.urls")),     # F13
    path("api/v1/", include("apps.costing.urls")),     # F14
    path("api/v1/", include("apps.dashboard.urls")),   # F15
]
