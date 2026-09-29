from decimal import Decimal

import pytest
from components.cart import cart_total


def test_cart_total_for_multiple_items():
    assert cart_total([(Decimal("19.90"), 2), (Decimal("5.25"), 1)]) == Decimal("45.05")


def test_cart_total_for_empty_cart():
    assert cart_total([]) == Decimal("0.00")


def test_cart_rejects_invalid_quantity():
    with pytest.raises(ValueError, match="quantity must be positive"):
        cart_total([(Decimal("9.99"), 0)])
