import asyncio

from fastapi import APIRouter, HTTPException, Path

from services.barcode_service import resolve_barcode

router = APIRouter()


@router.get("/{barcode}")
async def resolve_product_barcode(
    barcode: str = Path(..., description="UPC-A or EAN-13 barcode"),
):
    """Resolve a UPC/EAN barcode into product metadata and storage guidance."""
    try:
        async with asyncio.timeout(1.5):
            result = await asyncio.to_thread(resolve_barcode, barcode)
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
