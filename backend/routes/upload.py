from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from agents.phase4_check import run_compliance_check

router = APIRouter(prefix="/check", tags=["Compliance Check"])


@router.post("/artwork")
async def check_artwork(
    file:   UploadFile = File(...),
    market: str        = Form(...)
):
    """
    Phase 4 — Upload packaging artwork PDF and check compliance.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files supported")

    supported = ["USA", "UK", "India", "Australia", "Canada", "Ireland"]
    if market.upper() not in [s.upper() for s in supported]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported market. Choose from: {supported}"
        )

    try:
        pdf_bytes = await file.read()
        print(f"[Upload] Received: {file.filename} ({len(pdf_bytes)} bytes) for {market}")

        result = await run_compliance_check(
            pdf_bytes  = pdf_bytes,
            market     = market.upper(),
            filename   = file.filename
        )
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))