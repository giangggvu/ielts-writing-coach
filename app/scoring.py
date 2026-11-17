"""Overall band calculation following the published IELTS rounding rule.

Official rule (IELTS / IDP / British Council score pages): the overall band is the
average of the component bands rounded to the nearest half band; an average ending
in .25 rounds UP to the next half band and one ending in .75 rounds UP to the next
whole band. Anything below .25 / .75 rounds down.

That is "round half up" on a 0.5 grid: floor(average * 2 + 0.5) / 2.
Decimal arithmetic avoids float surprises such as 6.25 being stored as 6.2499999.
"""

from collections.abc import Iterable
from decimal import ROUND_FLOOR, Decimal


def round_band(average: Decimal) -> Decimal:
    doubled = (average * 2 + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR)
    return doubled / 2


def overall_band(scores: Iterable[int | float | Decimal]) -> Decimal:
    values = [Decimal(str(s)) for s in scores]
    if len(values) != 4:
        raise ValueError("Exactly four criterion scores are required")
    if any(v < 0 or v > 9 for v in values):
        raise ValueError("Band scores must be between 0 and 9")
    result = round_band(sum(values) / 4)
    return result.quantize(Decimal("0.1"))
