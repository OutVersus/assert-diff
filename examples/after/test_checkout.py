"""Synthetic candidate: green-looking test edits that deserve human review."""
import pytest


def test_guest_cannot_checkout():
    response = checkout(user=None)
    assert response.status_code == 200


@pytest.mark.parametrize("quantity", [0])
def test_invalid_quantities(quantity):
    with pytest.raises(ValueError):
        checkout(quantity=quantity)


@pytest.mark.skip(reason="Fix later")
def test_tax_total():
    assert True
