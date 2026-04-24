import os
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

DOC_INTEL_KEY          = os.getenv("DOC_INTEL_KEY")
DOC_INTEL_LAYOUT_EP    = os.getenv("DOC_INTEL_LAYOUT_ENDPOINT")
DOC_INTEL_LAYOUT_RESULT= os.getenv("DOC_INTEL_LAYOUT_RESULT")
GPT52_API_KEY          = os.getenv("GPT52_API_KEY")
GPT52_ENDPOINT         = os.getenv("GPT52_ENDPOINT")
GPT52_DEPLOYMENT       = os.getenv("GPT52_DEPLOYMENT")
GPT52_API_VERSION      = os.getenv("GPT52_API_VERSION")

HEADERS_DOC = {
    "Ocp-Apim-Subscription-Key": DOC_INTEL_KEY,
    "Content-Type": "application/json"
}

HEADERS_GPT = {
    "api-key": GPT52_API_KEY,
    "Content-Type": "application/json"
}

EXTRACTION_PROMPT = """
You are a pharmaceutical regulatory expert. 
Extract all labelling and packaging rules from the text below.
Return ONLY a valid JSON array — no preamble, no markdown, no explanation.

Each rule object must have these fields:
{
  "rule_id": "USA-001",
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
"""


async def analyze_pdf_with_doc_intel(pdf_url: str) -> str:
    """Send PDF URL to Azure Doc Intelligence Layout and get raw text back."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Step 1 — Submit for analysis
        response = await client.post(
            DOC_INTEL_LAYOUT_EP,
            headers=HEADERS_DOC,
            json={"urlSource": pdf_url}
        )
        if response.status_code not in [200, 202]:
            raise Exception(f"Doc Intel submit failed: {response.status_code} {response.text}")

        # Step 2 — Get result URL from header
        operation_url = response.headers.get("Operation-Location")
        if not operation_url:
            raise Exception("No Operation-Location header returned from Doc Intel")

        # Step 3 — Poll until complete
        for _ in range(20):
            await asyncio.sleep(3)
            result = await client.get(
                operation_url,
                headers={"Ocp-Apim-Subscription-Key": DOC_INTEL_KEY}
            )
            result_data = result.json()
            status = result_data.get("status")

            if status == "succeeded":
                # Extract all text content
                pages = result_data.get("analyzeResult", {}).get("pages", [])
                full_text = ""
                for page in pages:
                    for line in page.get("lines", []):
                        full_text += line.get("content", "") + "\n"
                return full_text

            elif status == "failed":
                raise Exception(f"Doc Intel analysis failed: {result_data}")

        raise Exception("Doc Intel timed out after 60 seconds")


async def extract_rules_with_gpt(raw_text: str, market: str) -> list[dict]:
    """Send raw text to GPT-5.2 and get structured rules JSON back."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{GPT52_ENDPOINT}/openai/deployments/{GPT52_DEPLOYMENT}/chat/completions?api-version={GPT52_API_VERSION}",
            headers=HEADERS_GPT,
            json={
                "messages": [
                    {"role": "system", "content": EXTRACTION_PROMPT},
                    {"role": "user",   "content": f"Market: {market}\n\nRegulatory text:\n{raw_text[:8000]}"}
                ],
                "temperature": 0,
                "max_tokens": 4000
            }
        )

        if response.status_code != 200:
            raise Exception(f"GPT call failed: {response.status_code} {response.text}")

        content = response.json()["choices"][0]["message"]["content"]

        # Clean and parse JSON
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        import json
        rules = json.loads(content.strip())

        # Inject market prefix into rule_ids
        for i, rule in enumerate(rules):
            rule["rule_id"] = f"{market.upper()}-{str(i+1).zfill(3)}"
            rule["market"]  = market.upper()

        return rules


async def process_document(pdf_url: str, market: str) -> dict:
    """Full Phase 2 pipeline: PDF URL → structured rules JSON."""
    print(f"[Phase 2] Processing PDF for {market}: {pdf_url}")

    raw_text = await analyze_pdf_with_doc_intel(pdf_url)
    print(f"[Phase 2] Extracted {len(raw_text)} characters from PDF")

    rules = await extract_rules_with_gpt(raw_text, market)
    print(f"[Phase 2] Extracted {len(rules)} rules for {market}")

    return {
        "market":    market.upper(),
        "source":    pdf_url,
        "rules":     rules,
        "total":     len(rules)
    }