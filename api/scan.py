from fastapi import APIRouter, UploadFile, File

router = APIRouter()

@router.post("/")
async def scan_receipt(file: UploadFile = File(...)):
    return {
        "message": "Image received",
        "filename": file.filename
    }