import asyncio
import httpx
import json
import urllib3
import os
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

BLOB_KEY      = os.getenv("BLOB_PRIMARY_KEY")
BLOB_DOWNLOAD = os.getenv("BLOB_DOWNLOAD_ENDPOINT")
BLOB_FOLDER   = "medinspectai"
MARKETS       = ["USA", "UK", "India", "Australia", "Canada"]

async def download():
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        for market in MARKETS:
            url = f"{BLOB_DOWNLOAD}/{BLOB_FOLDER}/{market}.json"
            response = await client.get(
                url,
                headers={"Ocp-Apim-Subscription-Key": BLOB_KEY}
            )
            if response.status_code == 200:
                data = response.json()
                filepath = f"rules/{market}.json"
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                print(f"✅ {market}: {data.get('total', 0)} rules saved to {filepath}")
            else:
                print(f"❌ {market}: not found in blob ({response.status_code})")

if __name__ == "__main__":
    asyncio.run(download())