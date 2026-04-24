import os
import httpx
import asyncio
import json
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

DOC_INTEL_KEY           = os.getenv("DOC_INTEL_KEY")
DOC_INTEL_LAYOUT_EP     = os.getenv("DOC_INTEL_LAYOUT_ENDPOINT")
DOC_INTEL_LAYOUT_RESULT = os.getenv("DOC_INTEL_LAYOUT_RESULT")
GPT52_API_KEY           = os.getenv("GPT52_API_KEY")
GPT52_ENDPOINT          = os.getenv("GPT52_ENDPOINT")
GPT52_DEPLOYMENT        = os.getenv("GPT52_DEPLOYMENT")
GPT52_API_VERSION       = os.getenv("GPT52_API_VERSION")

HEADERS_DOC = {
    "Ocp-Apim-Subscription-Key": DOC_INTEL_KEY,
    "Content-Type": "application/json"
}

HEADERS_GPT = {
    "api-key": GPT52_API_KEY,
    "Content-Type": "application/json"
}

CHUNK_SIZE = 15000  # chars per GPT call

EXTRACTION_PROMPT = """
You are a pharmaceutical regulatory expert.
Extract all labelling and packaging rules from the text below.
Return ONLY a valid JSON array — no preamble, no markdown, no explanation.
If no rules are found in this chunk, return an empty array: []

Each rule object must have these exact fields:
{
  "rule_id": "TEMP-001",
  "field": "product_name",
  "mandatory": true,
  "bold_required": false,
  "min_font_size_pt": null,
  "location": "outer_carton",
  "exact_text": null,
  "language_required": "English",
  "braille_required": false,
  "reference": "21 CFR 201.10"
}

Rules to extract: product name, strength/dosage, route of administration,
warnings, storage instructions, expiry date, batch number, manufacturer details,
barcode/QR requirements, braille, language requirements, font size minimums.

Only extract rules that are clearly stated. Do not invent rules.
"""


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into overlapping chunks to avoid missing rules at boundaries."""
    chunks = []
    overlap = 500  # overlap between chunks to catch boundary rules
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap  # overlap with previous chunk
    return chunks


async def analyze_pdf_with_doc_intel(pdf_url: str) -> str:
    """Send PDF URL to Azure Doc Intelligence Layout and get raw text back."""
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        response = await client.post(
            DOC_INTEL_LAYOUT_EP,
            headers=HEADERS_DOC,
            json={"urlSource": pdf_url}
        )
        if response.status_code not in [200, 202]:
            raise Exception(f"Doc Intel submit failed: {response.status_code} {response.text}")

        print(f"[Phase 2] Submit status: {response.status_code}")

        operation_url = response.headers.get("Operation-Location", "")
        result_id = operation_url.split("/analyzeResults/")[-1].split("?")[0]
        print(f"[Phase 2] Result ID: {result_id}")

        if not result_id:
            raise Exception("Could not extract result ID from Operation-Location")

    # Build poll URL using gateway
    poll_url = DOC_INTEL_LAYOUT_RESULT.replace("{layout-resultId}", result_id)
    print(f"[Phase 2] Polling via gateway: {poll_url}")

    async with httpx.AsyncClient(timeout=60, verify=False) as poll_client:
        for attempt in range(40):
            await asyncio.sleep(5)
            result = await poll_client.get(
                poll_url,
                headers={"Ocp-Apim-Subscription-Key": DOC_INTEL_KEY}
            )
            result_data = result.json()
            status = result_data.get("status")
            print(f"[Phase 2] Poll attempt {attempt+1} — status: {status}")

            if status == "succeeded":
                pages = result_data.get("analyzeResult", {}).get("pages", [])
                full_text = ""
                for page in pages:
                    for line in page.get("lines", []):
                        full_text += line.get("content", "") + "\n"
                print(f"[Phase 2] Extracted {len(full_text)} characters")
                return full_text

            elif status == "failed":
                raise Exception(f"Doc Intel analysis failed: {result_data}")

            elif "error" in result_data:
                raise Exception(f"Doc Intel poll error: {result_data['error']}")

        raise Exception("Doc Intel timed out after 200 seconds")


async def call_gpt_on_chunk(chunk: str, market: str, chunk_num: int) -> list[dict]:
    """Send a single chunk to GPT and get rules back."""
    async with httpx.AsyncClient(timeout=60, verify=False) as client:
        response = await client.post(
            f"{GPT52_ENDPOINT}/openai/deployments/{GPT52_DEPLOYMENT}/chat/completions?api-version={GPT52_API_VERSION}",
            headers=HEADERS_GPT,
            json={
                "messages": [
                    {"role": "system", "content": EXTRACTION_PROMPT},
                    {"role": "user",   "content": f"Market: {market}\nChunk {chunk_num}:\n\n{chunk}"}
                ],
                "temperature": 0,
                "max_completion_tokens": 4000
            }
        )

        if response.status_code != 200:
            print(f"[Phase 2] GPT failed on chunk {chunk_num}: {response.status_code}")
            return []

        content = response.json()["choices"][0]["message"]["content"]
        content = content.strip()

        # Clean markdown if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        try:
            rules = json.loads(content)
            if not isinstance(rules, list):
                return []
            print(f"[Phase 2] Chunk {chunk_num} → {len(rules)} rules found")
            return rules
        except json.JSONDecodeError:
            print(f"[Phase 2] Chunk {chunk_num} → JSON parse failed, skipping")
            return []


def deduplicate_rules(rules: list[dict]) -> list[dict]:
    """Remove duplicate rules based on field + exact_text + location combo."""
    seen = set()
    unique = []
    for rule in rules:
        key = (
            rule.get("field", ""),
            rule.get("exact_text", "") or "",
            rule.get("location", "")
        )
        if key not in seen:
            seen.add(key)
            unique.append(rule)
    return unique


async def extract_rules_with_gpt(raw_text: str, market: str) -> list[dict]:
    """Chunk the full text and call GPT on each chunk, merge all rules."""
    chunks = chunk_text(raw_text, CHUNK_SIZE)
    print(f"[Phase 2] Split into {len(chunks)} chunks of ~{CHUNK_SIZE} chars each")

    all_rules = []

    for i, chunk in enumerate(chunks):
        print(f"[Phase 2] Processing chunk {i+1}/{len(chunks)}...")
        rules = await call_gpt_on_chunk(chunk, market, i+1)
        all_rules.extend(rules)
        await asyncio.sleep(1)  # small delay to avoid rate limiting

    # Deduplicate
    unique_rules = deduplicate_rules(all_rules)
    print(f"[Phase 2] Total rules before dedup: {len(all_rules)}")
    print(f"[Phase 2] Total rules after dedup:  {len(unique_rules)}")

    # Assign final rule IDs
    for i, rule in enumerate(unique_rules):
        rule["rule_id"] = f"{market.upper()}-{str(i+1).zfill(3)}"
        rule["market"]  = market.upper()

    return unique_rules


async def process_document(pdf_url: str, market: str) -> dict:
    """Full Phase 2 pipeline: PDF URL → structured rules JSON."""
    print(f"[Phase 2] Processing PDF for {market}: {pdf_url}")

    raw_text = await analyze_pdf_with_doc_intel(pdf_url)
    print(f"[Phase 2] Extracted {len(raw_text)} characters from PDF")

    rules = await extract_rules_with_gpt(raw_text, market)
    print(f"[Phase 2] Final rule count for {market}: {len(rules)}")

    return {
        "market": market.upper(),
        "source": pdf_url,
        "rules":  rules,
        "total":  len(rules)
    }