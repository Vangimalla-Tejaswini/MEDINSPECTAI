from fastapi import APIRouter, HTTPException
from agents.phase1_discover import search_regulatory_docs, discover_all_markets

router = APIRouter(prefix="/rules", tags=["Rules"])

@router.get("/discover/{market}")
async def discover_market(market: str):
    """Discover regulatory documents for a specific market."""
    try:
        results = await search_regulatory_docs(market.upper())
        return {
            "market": market.upper(),
            "total": len(results),
            "results": results
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/discover-all")
async def discover_all():
    """Discover regulatory documents for all markets."""
    results = await discover_all_markets()
    return {
        "markets": list(results.keys()),
        "results": results
    }