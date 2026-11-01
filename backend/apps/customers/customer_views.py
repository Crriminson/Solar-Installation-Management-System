"""
The customer as a whole (F01).

Spec.md F01: a customer may have several sites, and a site may have
several projects. Everything else in the product reaches a customer
sideways - through an enquiry, an order, a serial. This is the one
place that answers "who is this person and what have we done for
them", which is the question support and sales actually ask.

Read only. A customer record is made by an enquiry and changed through
the enquiry that owns it, so there is nothing to create or edit here.
"""

from django.db.models import Count, OuterRef, Subquery
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import BoundedPagination, StaffAccess

from .models import Customer, Enquiry, Site
from .serializers import CustomerListSerializer

# Everyone who deals with a customer by name. Technicians are not here:
# they reach the customer detail their own job needs, and no more
# (rules.md section 4).
CUSTOMER_ROLES = (
    Role.SALES, Role.OPERATIONS_MANAGER, Role.SUPPORT,
    Role.FINANCE, Role.DIRECTOR,
)

# How many of each kind of record the detail view carries. A customer
# of twenty years has more history than one screen should load.
RECENT = 20


class CustomerAccess(StaffAccess):
    def has_permission(self, request, view):
        view.read_roles = CUSTOMER_ROLES
        view.write_roles = ()
        return super().has_permission(request, view)


class CustomerListView(ListAPIView):
    """
    Customers, searchable by name or phone.

    The counts come from the database rather than from walking each
    customer's records, so the page is one query however long the list
    gets.
    """

    permission_classes = [CustomerAccess]
    serializer_class = CustomerListSerializer
    pagination_class = BoundedPagination

    def get_queryset(self):
        first_site = Site.objects.filter(customer=OuterRef("pk")).order_by("id")

        customers = Customer.objects.annotate(
            site_count=Count("sites", distinct=True),
            enquiry_count=Count("sites__enquiries", distinct=True),
            # Order points at the customer directly, so there is no need
            # to walk the enquiry and quotation behind it.
            order_count=Count("order", distinct=True),
            city=Subquery(first_site.values("city")[:1]),
        ).order_by("-id")

        search = self.request.query_params.get("search", "").strip()
        if search:
            digits = "".join(character for character in search if character.isdigit())
            customers = (
                customers.filter(phone__contains=digits) if digits
                else customers.filter(full_name__icontains=search)
            )
        return customers


class CustomerDetailView(APIView):
    """
    One customer, and what has happened for them.

    Everything here already exists elsewhere; this gathers it so nobody
    has to visit five screens to answer one question. Cost and margin
    are not among it - this view is read by Sales and Support.
    """

    permission_classes = [CustomerAccess]

    def get(self, request, pk):
        customer = Customer.objects.filter(pk=pk).first()
        if customer is None:
            return Response({"detail": "That customer does not exist."}, status=404)

        return Response({
            "id": customer.pk,
            "full_name": customer.full_name,
            "phone": customer.phone,
            "email": customer.email,
            "customer_type": customer.customer_type,
            "created_at": customer.created_at,
            "sites": self._sites(customer),
            "enquiries": self._enquiries(customer),
            "orders": self._orders(customer),
            "equipment": self._equipment(customer),
            "tickets": self._tickets(customer),
            "telegram": self._telegram(customer),
        })

    # --- the parts -----------------------------------------------------

    def _sites(self, customer):
        return [
            {"id": site.pk, "address_line": site.address_line, "city": site.city,
             "state": site.state, "pincode": site.pincode}
            for site in customer.sites.all().order_by("id")
        ]

    def _enquiries(self, customer):
        enquiries = (
            Enquiry.objects
            .filter(site__customer=customer)
            .select_related("site", "owner")
            .order_by("-id")[:RECENT]
        )
        return [
            {"id": enquiry.pk, "reference": enquiry.reference, "status": enquiry.status,
             "owner_name": enquiry.owner.get_full_name() if enquiry.owner else "",
             "created_at": enquiry.created_at}
            for enquiry in enquiries
        ]

    def _orders(self, customer):
        from apps.orders.models import Order

        orders = (
            Order.objects
            .filter(customer=customer)
            .select_related("quotation", "quotation__quote")
            .order_by("-id")[:RECENT]
        )
        return [
            {"id": order.pk, "reference": order.reference, "status": order.status,
             "gross": str(order.gross_payable_incl_tax),
             "outstanding": str(order.outstanding),
             "created_at": order.created_at}
            for order in orders
        ]

    def _equipment(self, customer):
        """Delivered and installed units, with cover beside each."""
        from apps.inventory.models import SerializedUnit, StockStatus
        from apps.warranties.models import AssetWarranty

        units = (
            SerializedUnit.objects
            .filter(customer=customer,
                    status__in=[StockStatus.DELIVERED, StockStatus.INSTALLED])
            .select_related("product")
            .order_by("id")
        )
        cover = {
            warranty.unit_id: warranty
            for warranty in AssetWarranty.objects.filter(unit__in=units)
        }
        return [
            {"id": unit.pk, "asset_id": unit.asset_id,
             "serial_number": unit.serial_number,
             "product": unit.product.name,
             "warranty_status": cover[unit.pk].status if unit.pk in cover else "none",
             "covered_until": (cover[unit.pk].coverage_expires_on
                               if unit.pk in cover else None)}
            for unit in units
        ]

    def _tickets(self, customer):
        from apps.support.models import ServiceTicket

        tickets = (
            ServiceTicket.objects
            .filter(customer=customer)
            .order_by("-id")[:RECENT]
        )
        return [
            {"id": ticket.pk, "reference": ticket.reference, "status": ticket.status,
             "priority": ticket.priority, "fault": ticket.fault_description,
             "complaint_at": ticket.complaint_at}
            for ticket in tickets
        ]

    def _telegram(self, customer):
        from apps.messaging.models import TelegramBinding

        binding = (
            TelegramBinding.objects
            .filter(customer=customer, revoked_at__isnull=True)
            .order_by("-id")
            .first()
        )
        return {"linked": binding is not None,
                "chat_name": binding.chat_name if binding else ""}
