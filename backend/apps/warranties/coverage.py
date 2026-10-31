"""
The calendar arithmetic behind a warranty (F12).

Pure functions with no database, so the leap-day rule can be read and
tested on its own. Coverage dates are Asia/Kolkata calendar dates.
"""

import calendar
from datetime import date, timedelta

MONTHS_PER_YEAR = 12


def coverage_expiry(start, months):
    """
    The first date a warranty no longer covers.

    Expiry is exclusive, so this is the same day of the month, `months`
    later. Where that day does not exist, as with 29 February two years
    on, it moves forward to the 1st of the next month (D049). Moving back
    to the 28th would make the 27th the last covered day, one day short
    of the term the customer bought.
    """
    elapsed = start.year * MONTHS_PER_YEAR + (start.month - 1) + months
    year, month_index = divmod(elapsed, MONTHS_PER_YEAR)
    month = month_index + 1

    days_in_month = calendar.monthrange(year, month)[1]
    if start.day <= days_in_month:
        return date(year, month, start.day)
    return date(year, month, days_in_month) + timedelta(days=1)
