import asyncio

from fastapi import APIRouter, HTTPException, Path

from services.barcode_service import resolve_barcode, validate_barcode

router = APIRouter()


def _validate_barcode_or_422(barcode: str) -> str:
    try:
        return validate_barcode(barcode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{barcode}")
async def resolve_product_barcode(
    barcode: str = Path(..., description="GTIN-8, UPC-A/GTIN-12, or EAN-13 barcode with a valid check digit"),
):
    """Resolve a UPC/EAN barcode into product metadata and storage guidance."""
    normalized_barcode = _validate_barcode_or_422(barcode)

    try:
        async with asyncio.timeout(1.5):
            result = await asyncio.to_thread(resolve_barcode, normalized_barcode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="OpenFoodFacts lookup timed out. Please retry shortly.",
        ) from None
    if result.get("lookup_status") == "unavailable":
        raise HTTPException(
            status_code=503,
            detail="OpenFoodFacts is temporarily unavailable. Please retry shortly.",
        )
    return result
