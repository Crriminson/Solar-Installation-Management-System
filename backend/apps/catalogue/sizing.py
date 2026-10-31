"""
Turning a package version and a survey into quantities (F04).

F05 builds quotations on these. Anything missing raises SizingError with
a sentence naming it, so a quotation is blocked rather than guessed. See
spec.md F05.

Units: distance in metres, load in kW, duration in hours, storage in
kWh. All arithmetic is Decimal. Every result rounds up, because being
short on site costs a second trip and being over does not.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from .models import Product, QuantityBasis


class SizingError(Exception):
    """A required input is missing, named in the message."""


@dataclass(frozen=True)
class PartLine:
    product: Product
    quantity: Decimal


def round_up_to_stocking_unit(quantity, stocking_quantity):
    """Rounds up to the next whole multiple of what the item is stocked in."""
    multiples = (quantity / stocking_quantity).to_integral_value(rounding=ROUND_CEILING)
    return multiples * stocking_quantity


def cable_quantity(distance_m, version, product):
    """
    Metres of cable for a surveyed route.

    distance × waste factor + termination buffer, rounded up to the
    stocking unit. Both figures come from the version, so a reissued
    quotation reproduces the same quantity (D027).
    """
    needed = distance_m * version.cable_waste_factor + version.cable_termination_buffer_m
    return round_up_to_stocking_unit(needed, product.stocking_quantity)


def battery_quantity(load_kw, backup_hours, version, product):
    """
    Batteries for an off-grid load, rounded up to a whole battery.

    Energy needed is load × backup hours. Each battery gives its stored
    kWh × the depth of discharge. Never inferred from panel capacity,
    which says nothing about what must keep running or for how long.
    """
    needed_kwh = load_kw * backup_hours
    usable_kwh = product.storage_kwh * version.battery_depth_of_discharge
    return (needed_kwh / usable_kwh).to_integral_value(rounding=ROUND_CEILING)


def parts_list(version, revision):
    """Every line of a version as a product and a quantity for this survey."""
    return [
        PartLine(product=line.product, quantity=_line_quantity(line, version, revision))
        for line in version.lines.select_related("product")
    ]


def _line_quantity(line, version, revision):
    if line.basis == QuantityBasis.CABLE_ROUTE:
        return cable_quantity(revision.cable_distance_m, version, line.product)

    if line.basis == QuantityBasis.BATTERY_LOAD:
        if revision.critical_load_kw is None or revision.backup_duration_hours is None:
            raise SizingError(
                "This package needs the survey's critical load and backup duration."
            )
        return battery_quantity(
            revision.critical_load_kw, revision.backup_duration_hours,
            version, line.product,
        )

    return line.quantity
