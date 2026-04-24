import asyncio
import json
import httpx
import urllib3
import os
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

SEARCH_KEY      = os.getenv("SEARCH_PRIMARY_KEY")
SEARCH_QUERY_EP = os.getenv("SEARCH_QUERY_ENDPOINT")
BLOB_KEY        = os.getenv("BLOB_PRIMARY_KEY")
BLOB_UPLOAD     = os.getenv("BLOB_UPLOAD_ENDPOINT")
BLOB_FOLDER     = "medinspectai"
MARKETS         = ["India", "Australia", "Canada"]

HEADERS_SEARCH = {
    "Ocp-Apim-Subscription-Key": SEARCH_KEY,
    "Content-Type": "application/json"
}

HEADERS_BLOB = {
    "Ocp-Apim-Subscription-Key": BLOB_KEY,
    "Content-Type": "text/plain"
}


async def fetch_all_rules_from_search(market: str) -> list[dict]:
    """Fetch ALL rules for a market from AI Search."""
    all_results = []
    skip = 0
    top  = 50  # fetch 50 at a time

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        while True:
            response = await client.post(
                SEARCH_QUERY_EP,
                headers=HEADERS_SEARCH,
                json={
                    "search": "*",
                    "filter": f"market eq '{market.upper()}'",
                    "top":    top,
                    "skip":   skip,
                    "select": "id,market,field,mandatory,bold_required,min_font_size,location,exact_text,reference,braille,language"
                }
            )

            if response.status_code != 200:
                print(f"❌ Search failed: {response.status_code} {response.text}")
                break

            results = response.json().get("value", [])
            if not results:
                break

            all_results.extend(results)
            print(f"[{market}] Fetched {len(all_results)} rules so far...")
            skip += top

            if len(results) < top:
                break

    return all_results


async def save_to_blob(market: str, rules: list[dict]) -> None:
    """Save recovered rules back to blob."""
    payload  = {
        "market": market.upper(),
        "total":  len(rules),
        "rules":  rules
    }
    full_url = f"{BLOB_UPLOAD}/{BLOB_FOLDER}/{market.upper()}.json"

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        response = await client.put(
            full_url,
            headers=HEADERS_BLOB,
            content=json.dumps(payload)
        )
        if response.status_code in [200, 201, 204]:
            print(f"[{market}] ✅ Saved to blob")
        else:
            print(f"[{market}] ❌ Blob save failed: {response.status_code}")


def save_locally(market: str, rules: list[dict]) -> None:
    """Save recovered rules to local JSON file."""
    os.makedirs("rules", exist_ok=True)
    filepath = f"rules/{market.upper()}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "market": market.upper(),
            "total":  len(rules),
            "rules":  rules
        }, f, indent=2)
    print(f"[{market}] ✅ Saved locally: {filepath}")


async def recover():
    for market in MARKETS:
        print(f"\n{'='*40}")
        print(f"Recovering: {market}")
        print(f"{'='*40}")

        rules = await fetch_all_rules_from_search(market)
        print(f"[{market}] Total rules recovered: {len(rules)}")

        if rules:
            await save_to_blob(market, rules)
            save_locally(market, rules)
        else:
            print(f"[{market}] ⚠️ No rules found in AI Search")

    print(f"\n✅ Recovery complete!")
    print(f"Check backend/rules/ folder in VS Code!")


if __name__ == "__main__":
    asyncio.run(recover())