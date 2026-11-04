from datetime import date
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from services.foodkeeper_engine import estimate_expiry


router = APIRouter()


class FoodKeeperRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    storage_zone: Literal["pantry", "fridge", "freezer"]
    purchase_date: date | None = None


@router.post("/predict-expiry")
def predict_foodkeeper_expiry(request: FoodKeeperRequest):
    result = estimate_expiry(request.name, request.storage_zone, request.purchase_date)
    return result or {"matched": False}
