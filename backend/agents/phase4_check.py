import os
import httpx
import asyncio
import json
import base64
import urllib3
import fitz
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

GPT52_API_KEY         = os.getenv("GPT52_API_KEY")
GPT52_ENDPOINT        = os.getenv("GPT52_ENDPOINT")
GPT52_DEPLOYMENT      = os.getenv("GPT52_DEPLOYMENT")
GPT52_API_VERSION     = os.getenv("GPT52_API_VERSION")
DOC_INTEL_KEY         = os.getenv("DOC_INTEL_KEY")
DOC_INTEL_READ_EP     = os.getenv("DOC_INTEL_READ_ENDPOINT")
DOC_INTEL_READ_RESULT = os.getenv("DOC_INTEL_READ_RESULT")
SEARCH_KEY            = os.getenv("SEARCH_PRIMARY_KEY")
SEARCH_QUERY_EP       = os.getenv("SEARCH_QUERY_ENDPOINT")

HEADERS_GPT = {
    "api-key": GPT52_API_KEY,
    "Content-Type": "application/json"
}

HEADERS_SEARCH = {
    "Ocp-Apim-Subscription-Key": SEARCH_KEY,
    "Content-Type": "application/json"
}

COMBINED_PROMPT = """
You are a senior pharmaceutical regulatory compliance expert.
You are given:
1. An actual IMAGE of a packaging artwork page (for visual inspection)
2. Extracted TEXT from the same page (for reading small text)
3. Regulatory rules for the market

Use BOTH the image AND the text together for maximum accuracy:
- Use IMAGE for: font sizes, braille, layout, positioning, colors
- Use TEXT for: reading small body text, ingredients, warnings, addresses

Return ONLY a valid JSON array — no preamble, no markdown, no explanation.
Each item must have exactly these fields:
{
  "rule_id": "UK-001",
  "field": "product_name",
  "status": "PASS",
  "reason": "Detailed reason citing both visual and text evidence",
  "severity": "critical",
  "location_hint": "exact location on packaging",
  "evidence": "text: found | visual: bold font front panel",
  "bbox": {"x": 10, "y": 20, "width": 50, "height": 10}
}

bbox = bounding box as percentage of image (0-100)
status = "PASS" or "FAIL" or "CANNOT_DETERMINE"
severity = "critical" or "major" or "minor"

IMPORTANT:
- If text extraction shows content but image unclear → trust text → PASS
- If image shows content but text missed it → trust image → PASS
- Only FAIL if BOTH text AND image confirm field is missing/wrong
- CANNOT_DETERMINE only if genuinely impossible from either source
- Always return a JSON array even if all rules pass
"""


def pdf_to_images(pdf_bytes: bytes, dpi: int = 100) -> list[str]:
    """Convert PDF pages to base64 PNG images."""
    doc    = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page_num in range(len(doc)):
        page      = doc[page_num]
        mat       = fitz.Matrix(dpi/72, dpi/72)
        pix       = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        b64       = base64.b64encode(img_bytes).decode("utf-8")
        images.append(b64)
        print(f"[Phase 4] Page {page_num+1} → {len(img_bytes)//1024}KB PNG")
    doc.close()
    return images


def pdf_to_text_per_page(pdf_bytes: bytes) -> list[str]:
    """Extract text from PDF pages using PyMuPDF."""
    doc   = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        texts.append(text)
        print(f"[Phase 4] Page {page_num+1} text → {len(text)} chars")
    doc.close()
    return texts


async def fetch_rules_from_search(market: str) -> list[dict]:
    """Load all rules for a market from AI Search."""
    all_rules = []
    skip      = 0

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        while True:
            response = await client.post(
                SEARCH_QUERY_EP,
                headers=HEADERS_SEARCH,
                json={
                    "search": "*",
                    "filter": f"market eq '{market.upper()}'",
                    "top":    50,
                    "skip":   skip,
                    "select": "id,market,field,mandatory,reference,exact_text,location,bold_required,braille,language"
                }
            )
            if response.status_code != 200:
                raise Exception(f"Search failed: {response.status_code}")

            results = response.json().get("value", [])
            if not results:
                break

            all_rules.extend(results)
            skip += 50
            if len(results) < 50:
                break

    print(f"[Phase 4] Loaded {len(all_rules)} rules for {market}")
    return all_rules


async def check_page_combined(
    image_b64: str,
    page_text: str,
    rules:     list[dict],
    market:    str,
    page_num:  int
) -> list[dict]:
    """Send page image + text + rules to GPT for combined compliance check."""

    # Process rules in batches of 20
    all_violations = []
    batch_size     = 20
    batches        = [rules[i:i+batch_size] for i in range(0, len(rules), batch_size)]

    for batch_num, batch in enumerate(batches):
        print(f"[Phase 4] Checking batch {batch_num+1}/{len(batches)} ({len(batch)} rules)...")
        rules_text = json.dumps(batch, indent=2)

        async with httpx.AsyncClient(timeout=120, verify=False) as client:
            response = await client.post(
                f"{GPT52_ENDPOINT}/openai/deployments/{GPT52_DEPLOYMENT}/chat/completions?api-version={GPT52_API_VERSION}",
                headers=HEADERS_GPT,
                json={
                    "messages": [
                        {
                            "role": "system",
                            "content": COMBINED_PROMPT
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"""Market: {market}
Page: {page_num}
Rule Batch: {batch_num+1}/{len(batches)}

REGULATORY RULES TO CHECK:
{rules_text}

EXTRACTED TEXT FROM PAGE:
{page_text[:3000]}

Visually inspect the image AND use the extracted text to check each rule above.
Return JSON array with one entry per rule."""
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image_b64}",
                                        "detail": "high"
                                    }
                                }
                            ]
                        }
                    ],
                    "temperature": 0,
                    "max_completion_tokens": 4000
                }
            )

            print(f"[Phase 4] GPT status: {response.status_code}")
            print(f"[Phase 4] GPT response length: {len(response.text)}")

            if response.status_code != 200:
                print(f"[Phase 4] GPT error: {response.text[:300]}")
                continue

            content = response.json()["choices"][0]["message"]["content"].strip()
            print(f"[Phase 4] GPT content length: {len(content)}")
            print(f"[Phase 4] GPT content preview: {content[:200]}")

            # Clean markdown
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            try:
                violations = json.loads(content)
                if not isinstance(violations, list):
                    print(f"[Phase 4] Batch {batch_num+1} → not a list, skipping")
                    continue
                print(f"[Phase 4] Batch {batch_num+1} → {len(violations)} checks")
                all_violations.extend(violations)
            except json.JSONDecodeError as e:
                print(f"[Phase 4] Batch {batch_num+1} → JSON parse failed: {e}")
                print(f"[Phase 4] Raw content: {content[:300]}")
                continue

        await asyncio.sleep(1)  # small delay between batches

    return all_violations


async def run_compliance_check(
    pdf_bytes: bytes,
    market:    str,
    filename:  str
) -> dict:
    """Full Phase 4: PDF → text + images → combined GPT check → violations."""
    print(f"[Phase 4] Starting COMBINED compliance check for {market}: {filename}")

    # Step 1 — Load rules
    rules = await fetch_rules_from_search(market)
    if not rules:
        raise Exception(f"No rules found for market: {market}")

    # Step 2 — Extract BOTH images and text
    print(f"[Phase 4] Extracting images and text from PDF...")
    images     = pdf_to_images(pdf_bytes, dpi=100)
    page_texts = pdf_to_text_per_page(pdf_bytes)
    print(f"[Phase 4] PDF has {len(images)} pages")

    # Step 3 — Check each page
    all_violations = []
    for i in range(len(images)):
        print(f"[Phase 4] Processing page {i+1}/{len(images)}...")
        violations = await check_page_combined(
            image_b64 = images[i],
            page_text = page_texts[i] if i < len(page_texts) else "",
            rules     = rules,
            market    = market,
            page_num  = i + 1
        )
        for v in violations:
            v["page"] = i + 1
        all_violations.extend(violations)

    # Step 4 — Summarize
    fails    = [v for v in all_violations if v.get("status") == "FAIL"]
    passes   = [v for v in all_violations if v.get("status") == "PASS"]
    critical = [v for v in fails if v.get("severity") == "critical"]

    summary = {
        "filename":       filename,
        "market":         market.upper(),
        "pages":          len(images),
        "total_checks":   len(all_violations),
        "passed":         len(passes),
        "failed":         len(fails),
        "critical":       len(critical),
        "overall_status": "FAIL" if critical else "PASS",
        "violations":     all_violations
    }

    print(f"[Phase 4] ✅ Done — {len(fails)} failures, {len(critical)} critical")
    return summary