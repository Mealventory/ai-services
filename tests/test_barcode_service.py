from unittest.mock import Mock, patch

import pytest

from services import barcode_service
from services.barcode_service import USER_AGENT, clear_barcode_cache, resolve_barcode


@pytest.fixture(autouse=True)
def clear_cache():
    clear_barcode_cache()
    yield
    clear_barcode_cache()


def test_resolves_milk_and_caches_openfoodfacts_response():
    response = Mock()
    response.json.return_value = {
        "status": 1,
        "product": {
            "product_name": "Whole Milk",
            "brands": "Kroger",
            "categories_tags": ["en:dairies", "en:milks"],
            "image_front_url": "http://images.openfoodfacts.org/milk.jpg",
        },
    }

    with patch("services.barcode_service.requests.get", return_value=response) as get:
        first = resolve_barcode("011110038333")
        second = resolve_barcode("011110038333")

    assert first == second
    assert first["name"] == "Whole Milk"
    assert first["brand"] == "Kroger"
    assert first["category"] == "Dairy"
    assert first["storage_zone"] == "fridge"
    assert first["image_url"] == "https://images.openfoodfacts.org/milk.jpg"
    assert first["shelf_life_days"] == 3
    assert first["shelf_life"]["food_state"] == "opened"
    get.assert_called_once_with(
        "https://world.openfoodfacts.org/api/v2/product/011110038333.json",
        headers={"User-Agent": USER_AGENT},
        timeout=(0.5, 1.0),
    )


def test_unknown_product_returns_fallback_payload():
    response = Mock()
    response.json.return_value = {"status": 0, "status_verbose": "product not found"}
    with patch("services.barcode_service.requests.get", return_value=response):
        result = resolve_barcode("999999999993")

    assert result == {
        "found": False,
        "barcode": "999999999993",
        "source": "openfoodfacts",
        "lookup_status": "not_found",
    }


def test_openfoodfacts_404_is_a_product_miss_not_an_outage():
    response = Mock()
    response.status_code = 404
    with patch("services.barcode_service.requests.get", return_value=response):
        result = resolve_barcode("011110038333")

    assert result["found"] is False
    assert result["lookup_status"] == "not_found"


def test_curated_kroger_milk_fallback_supplies_image_and_refrigerated_shelf_life():
    with patch("services.barcode_service.requests.get") as get:
        result = resolve_barcode("0001111090645")

    assert result["found"] is True
    assert result["source"] == "kroger_fallback"
    assert result["name"] == "Kroger Vitamin D Whole Milk Gallon"
    assert result["brand"] == "Kroger"
    assert result["storage_zone"] == "fridge"
    assert result["image_url"].endswith("0001111090645")
    assert result["shelf_life_days"] == 3
    get.assert_not_called()


def test_rejects_unsupported_barcode_length():
    with pytest.raises(ValueError, match="8, 12, or 13 digits"):
        resolve_barcode("12345")


@pytest.mark.parametrize("barcode", [
    "96385074",       # GTIN-8
    "011110038333",   # UPC-A / GTIN-12
    "0001111090645",  # EAN-13 curated Kroger fallback (corrected check digit)
])
def test_valid_supported_formats_pass_check_digit_validation(barcode):
    with patch("services.barcode_service.requests.get") as get:
        # A valid 13-digit fallback is resolved locally; other formats reach OFF.
        result = resolve_barcode(barcode)

    assert result["barcode"] == barcode
    if barcode == "0001111090645":
        assert result["source"] == "kroger_fallback"
        get.assert_not_called()
    else:
        get.assert_called_once()


@pytest.mark.parametrize("barcode", [
    "96385075",       # invalid GTIN-8 check digit
    "011110038334",   # invalid UPC-A check digit
    "0001111090642",  # old fallback number has an invalid EAN-13 check digit
    "123456789013",   # invalid UPC-A check digit
    "01111003833A",   # nonnumeric
    "1234567",        # unsupported length
])
def test_invalid_barcodes_are_rejected_before_openfoodfacts_or_fallback(barcode):
    with patch("services.barcode_service.requests.get") as get:
        with pytest.raises(ValueError):
            resolve_barcode(barcode)

    get.assert_not_called()


def test_upstream_failure_is_not_reported_as_not_found_or_cached():
    response = Mock()
    response.json.return_value = {"status": 0}
    with patch(
        "services.barcode_service.requests.get",
        side_effect=[barcode_service.requests.RequestException("offline"), response],
    ) as get:
        unavailable = resolve_barcode("011110038333")
        not_found = resolve_barcode("011110038333")

    assert unavailable["lookup_status"] == "unavailable"
    assert not_found["lookup_status"] == "not_found"
    assert get.call_count == 2
