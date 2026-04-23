import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SERP_API_KEY = os.getenv("SERP_API_KEY")

# ── Market-specific search queries ──────────────────────────────
MARKET_QUERIES = {
    "USA": [
        "FDA 21 CFR 201 pharmaceutical labelling requirements latest guidance",
        "FDA drug packaging labelling circular 2024 2025 site:fda.gov",
    ],
    "UK": [
        "MHRA pharmaceutical labelling packaging requirements 2024 2025",
        "MHRA human medicines regulations labelling guidance site:gov.uk",
    ],
    "India": [
        "CDSCO drug labelling rules packaging requirements latest circular site:cdsco.gov.in",
        "Drugs Cosmetics Rules 1945 labelling amendment 2024 2025",
    ],
    "Australia": [
        "TGA labelling requirements medicines packaging Australia 2024 2025",
        "TGA therapeutic goods order standard for labels site:tga.gov.au",
    ],
    "Canada": [
        "Health Canada drug labelling packaging requirements 2024 2025",
        "Health Canada pharmaceutical labelling guidance site:canada.ca",
    ],
}

# ── Trusted domains per market ───────────────────────────────────
TRUSTED_DOMAINS = {
    "USA":       ["fda.gov", "ecfr.gov", "federalregister.gov"],
    "UK":        ["gov.uk", "legislation.gov.uk", "mhra.gov.uk"],
    "India":     ["cdsco.gov.in", "mohfw.gov.in"],
    "Australia": ["tga.gov.au", "legislation.gov.au"],
    "Canada":    ["canada.ca", "healthcanada.gc.ca"],
}


async def search_regulatory_docs(market: str) -> list[dict]:
    """
    Phase 1 — Search SERP API for regulatory documents for a given market.
    Returns a list of {title, url, snippet, type} dicts.
    """
    if market not in MARKET_QUERIES:
        raise ValueError(f"Unsupported market: {market}")

    results = []
    queries = MARKET_QUERIES[market]
    trusted = TRUSTED_DOMAINS[market]

    async with httpx.AsyncClient(timeout=15) as client:
        for query in queries:
            response = await client.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": SERP_API_KEY,
                    "engine": "google",
                    "num": 5,
                }
            )

            if response.status_code != 200:
                print(f"[SERP] Failed for query: {query} — {response.status_code}")
                continue

            data = response.json()
            organic = data.get("organic_results", [])

            for item in organic:
                url = item.get("link", "")
                domain = url.split("/")[2] if url.startswith("http") else ""

                # Determine file type
                if url.endswith(".pdf"):
                    doc_type = "PDF"
                elif any(url.endswith(ext) for ext in [".html", ".htm"]):
                    doc_type = "HTML"
                else:
                    doc_type = "HTML"  # default assume HTML

                # Filter to trusted domains only
                is_trusted = any(t in domain for t in trusted)

                results.append({
                    "title":     item.get("title", ""),
                    "url":       url,
                    "snippet":   item.get("snippet", ""),
                    "type":      doc_type,
                    "trusted":   is_trusted,
                    "market":    market,
                    "query":     query,
                })

    # Prioritise trusted sources first
    results.sort(key=lambda x: (not x["trusted"], x["type"] != "PDF"))
    return results


async def discover_all_markets() -> dict:
    """Run Phase 1 for all supported markets."""
    markets = os.getenv("SUPPORTED_MARKETS", "USA,UK,India,Australia,Canada").split(",")
    all_results = {}
    for market in markets:
        print(f"[Phase 1] Discovering docs for: {market}")
        all_results[market] = await search_regulatory_docs(market.strip())
    return all_results