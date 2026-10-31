"""
Director dashboard endpoints (F15).

    GET /api/v1/dashboard/                     every figure for the filters
    GET /api/v1/dashboard/metrics/<key>/       the records behind one figure
    GET /api/v1/dashboard/export/<key>.csv     that table as CSV
    GET /api/v1/dashboard/export/summary.pdf   the summary as PDF

All take period (today, week, month, custom, with from and to), status
and system_type. Read-only, and for the director: every figure here is
margin or cash, and rules.md section 4 grants the dashboard and its
exports to that role. There is no anonymous financial view.
"""

from django.http import HttpResponse
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import StaffAccess, exact_decimals

from .exports import metric_csv, summary_pdf
from .metrics import METRICS, dashboard, filters_from


class DashboardAccess(StaffAccess):
    def has_permission(self, request, view):
        view.read_roles = (Role.DIRECTOR,)
        view.write_roles = ()
        return super().has_permission(request, view)


def _metric(key):
    metric = METRICS.get(key)
    if metric is None:
        raise NotFound()
    return metric


class DashboardView(APIView):
    permission_classes = [DashboardAccess]

    def get(self, request):
        return Response(exact_decimals(dashboard(filters_from(request.query_params))))


class MetricRowsView(APIView):
    """A number the director cannot trace is not trusted (spec.md F15)."""

    permission_classes = [DashboardAccess]

    def get(self, request, key):
        metric = _metric(key)
        filters = filters_from(request.query_params)
        return Response(exact_decimals({
            "key": metric.key, "label": metric.label, "caption": metric.caption,
            "kind": metric.kind, "period": filters.description,
            "rows": metric.rows(filters),
        }))


class MetricCsvView(APIView):
    permission_classes = [DashboardAccess]

    def get(self, request, key):
        metric = _metric(key)
        body = metric_csv(metric, filters_from(request.query_params))
        response = HttpResponse(body, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{metric.key}.csv"'
        return response


class SummaryPdfView(APIView):
    permission_classes = [DashboardAccess]

    def get(self, request):
        response = HttpResponse(summary_pdf(filters_from(request.query_params)),
                                content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="director-summary.pdf"'
        return response
