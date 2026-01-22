import requests
import time
import json

# FIX: Removed the double slash // before 'mq_apis'
BASE_URL = "https://data-api.megalis.bretagne.bzh/mq_apis/actes/v1/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://data.megalis.bretagne.bzh/"
}

# FIX: Re-added query: "" and ensured SIREN is string
QUERY_PARAMS = {
    "query": "",
    "siren": "200054724",
    "lignes": "10",
    "page_suivante": None
}

all_results = []
# Using a Session object is a proven way to bypass "Invalid Request" errors
session = requests.Session()

print("Starting scrape...")

while True:
    try:
        # Use session.get instead of requests.get
        response = session.get(BASE_URL, headers=HEADERS, params=QUERY_PARAMS)

        if response.status_code != 200:
            print(f"--- ERROR DETAILS ---")
            print(f"Status Code: {response.status_code}")
            print(f"Response Body: {response.text}")
            break

        data = response.json()
        new_items = data.get('resultats', [])
        all_results.extend(new_items)
        
        print(f"Collected {len(new_items)} items. Total: {len(all_results)}")

        next_cursor = data.get("page_suivante")
        if not next_cursor:
            print("No more pages found.")
            break

        QUERY_PARAMS["page_suivante"] = next_cursor
        time.sleep(0.2) # Slightly longer wait to be safe
    
    except Exception as e:
        print(f"An error occurred: {e}")
        break

with open("documents.json", "w", encoding="utf-8") as f: # update this -- moved manually for now...
    json.dump(all_results, f, ensure_ascii=False, indent=2)