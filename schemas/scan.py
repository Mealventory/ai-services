"""Typed, versioned scan response contracts for Mealventory AI microservice."""
from datetime import date, datetime
from typing import List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

ScanMode = Literal["food", "tag", "receipt"]
ScanResultType = Literal["food", "tag", "receipt", "mismatch", "unknown", "multi"]


class FoodItemDetail(BaseModel):
    """Granular metadata for detected food items."""
    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Normalized lowercase food item name")
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence score")
    label: Optional[str] = Field(default=None, description="Raw label description from model or vision")
    source: Optional[str] = Field(default=None, description="Detection pipeline source (vision_label, classification, mock_vision, ocr)")
    category: Optional[str] = Field(default=None, description="Predicted food category")
    quantity: Optional[Union[float, int]] = Field(default=None, description="Extracted numerical quantity")
    unit: Optional[str] = Field(default=None, description="Extracted unit of measurement")
    price: Optional[float] = Field(default=None, description="Extracted item price if detected on receipt")


class ScanResponse(BaseModel):
    """Canonical versioned response for all scan modes (food, receipt, tag, multi)."""
    model_config = ConfigDict(extra="allow")

    type: ScanResultType = Field(description="Detected scan result classification or outcome")
    requested_type: Optional[str] = Field(default=None, description="Mode requested by client")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall detection confidence score")
    items: List[str] = Field(default_factory=list, description="Array of detected food item names")
    item_details: List[FoodItemDetail] = Field(default_factory=list, description="Structured metadata per item")
    message: Optional[str] = Field(default=None, description="Explanatory message for unknown, mismatch, or low confidence")
    detected_type: Optional[str] = Field(default=None, description="Detected mode in case of mode mismatch")
    text_preview: Optional[str] = Field(default=None, description="Truncated preview of extracted OCR text")
    expiry_dates: List[str] = Field(default_factory=list, description="List of raw or formatted expiry date strings")
    needs_user_input: bool = Field(default=False, description="Flag indicating user clarification needed (e.g. tag without food name)")
    prompt: Optional[str] = Field(default=None, description="Instruction prompt presented to user when needs_user_input is True")


class ExpiryPredictionResponse(BaseModel):
    """Response model for heuristic expiry prediction."""
    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Food item name")
    purchase_date: date = Field(description="Purchase date used for prediction")
    predicted_expiry_date: Union[date, datetime] = Field(description="Predicted expiration date")


class MultiScanResponse(ScanResponse):
    """Specialized schema for multi-item produce and grocery scans."""
    type: Literal["multi"] = "multi"
    requested_type: Optional[str] = "multi"
