# To check Rules in blob
import asyncio
import httpx
import urllib3
import os
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

BLOB_KEY      = os.getenv("BLOB_PRIMARY_KEY")
BLOB_DOWNLOAD = os.getenv("BLOB_DOWNLOAD_ENDPOINT")
BLOB_FOLDER   = "medinspectai"
MARKETS       = ["USA", "UK", "India", "Australia", "Canada"]

async def check():
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        for market in MARKETS:
            print(f"\n{'='*40}")
            print(f"Market: {market}")
            print(f"{'='*40}")

            # Check rules file
            url = f"{BLOB_DOWNLOAD}/{BLOB_FOLDER}/{market}.json"
            response = await client.get(
                url,
                headers={"Ocp-Apim-Subscription-Key": BLOB_KEY}
            )

            if response.status_code == 200:
                data = response.json()
                rules = data.get("rules", [])
                print(f"✅ Rules stored: {len(rules)}")
                print(f"   Sample fields extracted:")
                fields = list(set(r.get("field","") for r in rules))
                for f in fields[:8]:
                    print(f"   → {f}")
            else:
                print(f"❌ No rules found ({response.status_code})")

            # Check links file
            url2 = f"{BLOB_DOWNLOAD}/{BLOB_FOLDER}/{market}_links.json"
            response2 = await client.get(
                url2,
                headers={"Ocp-Apim-Subscription-Key": BLOB_KEY}
            )
            if response2.status_code == 200:
                data2 = response2.json()
                print(f"✅ Links stored: {data2.get('total_links', 0)}")
            else:
                print(f"❌ No links file found")

if __name__ == "__main__":
    asyncio.run(check())