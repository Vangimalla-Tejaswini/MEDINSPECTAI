import asyncio
from agents.phase3_store import query_rules
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

async def check():
    for market in ["India", "Australia", "Canada"]:
        results = await query_rules(market, "product name labelling", top=3)
        print(f"{market}: {len(results)} results in AI Search")

asyncio.run(check())