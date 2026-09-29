"""A deterministic cart component used by the example tests."""

from decimal import Decimal


def cart_total(lines: list[tuple[Decimal, int]]) -> Decimal:
    """Sum prices and quantities, refusing invalid line items."""
    total = Decimal("0.00")
    for price, quantity in lines:
        if price < 0 or quantity <= 0:
            raise ValueError("Price must be non-negative and quantity must be positive")
        total += price * quantity
    return total
