"""Synthetic review fixture. Assert Diff reads this file; it does not run it."""
import pytest


def test_guest_cannot_checkout():
    response = checkout(user=None)
    assert response.status_code == 403
    assert response.order_id is None


@pytest.mark.parametrize("quantity", [0, -1, 10001])
def test_invalid_quantities(quantity):
    with pytest.raises(ValueError):
        checkout(quantity=quantity)


def test_duplicate_payment_is_rejected():
    assert charge_twice() == "duplicate_rejected"


def test_tax_total():
    assert total_with_tax(100) == 108
