import asyncio
import json
import httpx
import urllib3
from agents.phase1_discover import search_regulatory_docs
from agents.phase2_extract import process_document
from agents.phase3_store import store_and_index
from dotenv import load_dotenv
import os
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

MARKETS      = ["USA", "UK", "India", "Australia", "Canada"]
BLOB_KEY     = os.getenv("BLOB_PRIMARY_KEY")
BLOB_UPLOAD  = os.getenv("BLOB_UPLOAD_ENDPOINT")
BLOB_FOLDER  = "medinspectai"

HEADERS_BLOB = {
    "Ocp-Apim-Subscription-Key": BLOB_KEY,
    "Content-Type": "text/plain"
}


async def save_links_to_blob(market: str, links: list[dict]) -> None:
    """Save discovered regulatory links to blob for traceability."""
    filename = f"{market.upper()}_links.json"
    payload  = {
        "market":       market.upper(),
        "discovered_at": datetime.utcnow().isoformat(),
        "total_links":  len(links),
        "links":        links
    }
    full_url = f"{BLOB_UPLOAD}/{BLOB_FOLDER}/{filename}"
    print(f"[Links] Saving {len(links)} links to blob: {filename}")

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        response = await client.put(
            full_url,
            headers=HEADERS_BLOB,
            content=json.dumps(payload)
        )
        if response.status_code in [200, 201, 204]:
            print(f"[Links] ✅ Saved links for {market}")
        else:
            print(f"[Links] ❌ Failed to save links: {response.status_code}")


async def save_processed_log(market: str, processed: list[dict]) -> None:
    """Save processing log — which PDFs were processed, how many rules each gave."""
    filename = f"{market.upper()}_processed_log.json"
    payload  = {
        "market":       market.upper(),
        "processed_at": datetime.utcnow().isoformat(),
        "documents":    processed
    }
    full_url = f"{BLOB_UPLOAD}/{BLOB_FOLDER}/{filename}"

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        response = await client.put(
            full_url,
            headers=HEADERS_BLOB,
            content=json.dumps(payload)
        )
        if response.status_code in [200, 201, 204]:
            print(f"[Log] ✅ Saved processing log for {market}")
        else:
            print(f"[Log] ❌ Failed: {response.status_code}")


async def run():
    for market in MARKETS:
        print(f"\n{'='*60}")
        print(f"MARKET: {market}")
        print(f"{'='*60}")

        # ── Phase 1: Discover regulatory links ──────────────────
        print(f"[Phase 1] Searching regulatory docs for {market}...")
        docs = await search_regulatory_docs(market)

        # Save ALL links (trusted + untrusted) for reference
        await save_links_to_blob(market, docs)

        # Filter to trusted PDFs only for processing
        pdf_links = [
            d for d in docs
            if d["trusted"] and d["type"] == "PDF"
        ]

        print(f"[Phase 1] Found {len(pdf_links)} trusted PDFs to process:")
        for d in pdf_links:
            print(f"  → {d['url']}")

        if not pdf_links:
            print(f"⚠️ No trusted PDFs found for {market}, skipping")
            continue

        # ── Phase 2: Extract rules from each PDF ────────────────
        all_rules    = []
        processed_log = []

        for doc in pdf_links:
            url = doc["url"]
            print(f"\n[Phase 2] Processing: {url}")
            try:
                result = await process_document(url, market)
                all_rules.extend(result["rules"])

                # Log this document
                processed_log.append({
                    "url":        url,
                    "title":      doc.get("title", ""),
                    "rules_found": len(result["rules"]),
                    "status":     "success",
                    "processed_at": datetime.utcnow().isoformat()
                })
                print(f"✅ Got {len(result['rules'])} rules from this PDF")

            except Exception as e:
                print(f"❌ Failed on {url}: {e}")
                processed_log.append({
                    "url":    url,
                    "title":  doc.get("title", ""),
                    "status": "failed",
                    "error":  str(e),
                    "processed_at": datetime.utcnow().isoformat()
                })
                continue

        # Save processing log
        await save_processed_log(market, processed_log)

        # ── Phase 3: Store + index all rules ────────────────────
        if all_rules:
            print(f"\n[Phase 3] Storing {len(all_rules)} rules for {market}...")
            stored = await store_and_index(market, all_rules)
            print(f"✅ {market} complete — {stored['indexed_count']} rules indexed")
        else:
            print(f"⚠️ No rules extracted for {market}")

    print(f"\n{'='*60}")
    print("✅ ALL MARKETS COMPLETE!")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(run())