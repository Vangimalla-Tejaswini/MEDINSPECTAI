import os
import json
import httpx
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

BLOB_KEY         = os.getenv("BLOB_PRIMARY_KEY")
BLOB_UPLOAD_EP   = os.getenv("BLOB_UPLOAD_ENDPOINT")
BLOB_DOWNLOAD_EP = os.getenv("BLOB_DOWNLOAD_ENDPOINT")
BLOB_FOLDER      = "medinspectai"

SEARCH_KEY       = os.getenv("SEARCH_PRIMARY_KEY")
SEARCH_UPLOAD_EP = os.getenv("SEARCH_UPLOAD_ENDPOINT")
SEARCH_QUERY_EP  = os.getenv("SEARCH_QUERY_ENDPOINT")

HEADERS_BLOB = {
    "Ocp-Apim-Subscription-Key": BLOB_KEY,
    "Content-Type": "text/plain"
}

HEADERS_SEARCH = {
    "Ocp-Apim-Subscription-Key": SEARCH_KEY,
    "Content-Type": "application/json"
}


# ── BLOB STORAGE ─────────────────────────────────────────────────

async def save_rules_to_blob(market: str, rules: list[dict]) -> str:
    filename = f"{market.upper()}.json"
    payload  = {"market": market.upper(), "total": len(rules), "rules": rules}
    full_url = f"{BLOB_UPLOAD_EP}/{BLOB_FOLDER}/{filename}"
    print(f"[Phase 3] Uploading to blob URL: {full_url}")

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        response = await client.put(
            full_url,
            headers=HEADERS_BLOB,
            content=json.dumps(payload)
        )
        print(f"[Phase 3] Blob response: {response.status_code} {response.text[:300]}")
        if response.status_code not in [200, 201, 204]:
            raise Exception(f"Blob upload failed: {response.status_code} {response.text}")
        print(f"[Phase 3] Saved {len(rules)} rules to blob: {filename}")
        return f"{BLOB_FOLDER}/{filename}"


async def load_rules_from_blob(market: str) -> dict:
    filename = f"{market.upper()}.json"
    full_url = f"{BLOB_DOWNLOAD_EP}/{BLOB_FOLDER}/{filename}"
    print(f"[Phase 3] Downloading from blob URL: {full_url}")

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        response = await client.get(
            full_url,
            headers={"Ocp-Apim-Subscription-Key": BLOB_KEY}
        )
        print(f"[Phase 3] Blob download response: {response.status_code}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise Exception(f"Blob download failed: {response.status_code} {response.text}")
        return response.json()


# ── AI SEARCH ─────────────────────────────────────────────────────

async def create_search_index() -> None:
    """Create AI Search index with our rules schema."""
    index_schema = {
        "fields": [
            {"name": "id",            "type": "Edm.String", "key": True,  "searchable": False},
            {"name": "market",        "type": "Edm.String", "key": False, "searchable": True,  "filterable": True},
            {"name": "field",         "type": "Edm.String", "key": False, "searchable": True},
            {"name": "mandatory",     "type": "Edm.String", "key": False, "searchable": False, "filterable": True},
            {"name": "bold_required", "type": "Edm.String", "key": False, "searchable": False},
            {"name": "min_font_size", "type": "Edm.String", "key": False, "searchable": False},
            {"name": "location",      "type": "Edm.String", "key": False, "searchable": True},
            {"name": "exact_text",    "type": "Edm.String", "key": False, "searchable": True},
            {"name": "reference",     "type": "Edm.String", "key": False, "searchable": True},
            {"name": "braille",       "type": "Edm.String", "key": False, "searchable": False},
            {"name": "language",      "type": "Edm.String", "key": False, "searchable": True},
            {"name": "content",       "type": "Edm.String", "key": False, "searchable": True}
        ]
    }

    index_endpoint = os.getenv("SEARCH_INDEX_ENDPOINT")
    print(f"[Phase 3] Creating index at: {index_endpoint}")

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        response = await client.put(
            index_endpoint,
            headers=HEADERS_SEARCH,
            json=index_schema
        )
        print(f"[Phase 3] Index create response: {response.status_code} {response.text[:300]}")
        if response.status_code not in [200, 201, 204]:
            raise Exception(f"Index creation failed: {response.status_code} {response.text}")
        print(f"[Phase 3] Index created/updated ✅")


async def index_rules_in_search(market: str, rules: list[dict]) -> int:
    documents = []
    for rule in rules:
        documents.append({
            "id":            rule.get("rule_id", "").replace("-", "_"),
            "market":        market.upper(),
            "field":         rule.get("field", ""),
            "mandatory":     str(rule.get("mandatory", False)),
            "bold_required": str(rule.get("bold_required", False)),
            "min_font_size": str(rule.get("min_font_size_pt", "")),
            "location":      rule.get("location", ""),
            "exact_text":    rule.get("exact_text", "") or "",
            "reference":     rule.get("reference", ""),
            "braille":       str(rule.get("braille_required", False)),
            "language":      rule.get("language_required", "English"),
            "content":       f"{rule.get('field','')} {rule.get('location','')} {rule.get('reference','')} {rule.get('exact_text','') or ''}"
        })

    print(f"[Phase 3] Indexing {len(documents)} rules in AI Search for {market}")

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        response = await client.post(
            SEARCH_UPLOAD_EP,
            headers=HEADERS_SEARCH,
            json={"value": documents}
        )
        print(f"[Phase 3] Search index response: {response.status_code} {response.text[:300]}")
        if response.status_code not in [200, 201, 207]:
            raise Exception(f"Search index failed: {response.status_code} {response.text}")
        print(f"[Phase 3] Indexed {len(documents)} rules successfully ✅")
        return len(documents)


async def query_rules(market: str, query: str, top: int = 5) -> list[dict]:
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        response = await client.post(
            SEARCH_QUERY_EP,
            headers=HEADERS_SEARCH,
            json={
                "search": query,
                "filter": f"market eq '{market.upper()}'",
                "top":    top,
                "select": "id,market,field,mandatory,reference,exact_text,location"
            }
        )
        if response.status_code != 200:
            raise Exception(f"Search query failed: {response.status_code} {response.text}")
        return response.json().get("value", [])


# ── FULL PHASE 3 PIPELINE ─────────────────────────────────────────

async def store_and_index(market: str, rules: list[dict]) -> dict:
    blob_path     = await save_rules_to_blob(market, rules)
    await create_search_index()
    indexed_count = await index_rules_in_search(market, rules)

    return {
        "market":        market.upper(),
        "blob_path":     blob_path,
        "indexed_count": indexed_count,
        "status":        "stored and indexed ✅"
    }