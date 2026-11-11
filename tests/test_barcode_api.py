import pytest
from fastapi import HTTPException

from api.barcode import _validate_barcode_or_422


@pytest.mark.parametrize("barcode", ["96385075", "011110038334", "0001111090642"])
def test_invalid_check_digit_uses_documented_client_error_before_lookup(barcode):
    with pytest.raises(HTTPException) as error:
        _validate_barcode_or_422(barcode)

    assert error.value.status_code == 422
    assert error.value.detail == "Barcode has an invalid check digit"
