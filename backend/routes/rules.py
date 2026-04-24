from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agents.phase1_discover import search_regulatory_docs, discover_all_markets
from agents.phase2_extract   import process_document
from agents.phase3_store     import store_and_index, load_rules_from_blob, query_rules

router = APIRouter(prefix="/rules", tags=["Rules"])


class ExtractRequest(BaseModel):
    pdf_url: str
    market:  str

class QueryRequest(BaseModel):
    market: str
    query:  str
    top:    int = 5


@router.get("/discover/{market}")
async def discover_market(market: str):
    try:
        results = await search_regulatory_docs(market.upper())
        return {"market": market.upper(), "total": len(results), "results": results}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/discover-all")
async def discover_all():
    results = await discover_all_markets()
    return {"markets": list(results.keys()), "results": results}


@router.post("/extract")
async def extract_rules(req: ExtractRequest):
    """Phase 2 — Extract structured rules from a PDF URL."""
    try:
        result = await process_document(req.pdf_url, req.market.upper())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/store")
async def store_rules(req: ExtractRequest):
    """Phase 2 + 3 — Extract from PDF then store and index rules."""
    try:
        extracted = await process_document(req.pdf_url, req.market.upper())
        stored    = await store_and_index(req.market.upper(), extracted["rules"])
        return {**extracted, **stored}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/load/{market}")
async def load_rules(market: str):
    """Load cached rules from Blob Storage."""
    try:
        data = await load_rules_from_blob(market.upper())
        if not data:
            raise HTTPException(status_code=404, detail=f"No rules found for {market}")
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search_rules(req: QueryRequest):
    """Semantic search over indexed rules."""
    try:
        results = await query_rules(req.market.upper(), req.query, req.top)
        return {"market": req.market.upper(), "query": req.query, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))