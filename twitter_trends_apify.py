import os
import json
from apify_client import ApifyClient
from dotenv import load_dotenv

def main():
    load_dotenv()
    apify_api_key = os.getenv("APIFY_KEY")

    client = ApifyClient(apify_api_key)

    run_input = {
      "country": "new-zealand"
    }

    try:
        print("Starting the Twitter Trends scraper...")
        actor_run = client.actor("fastcrawler/x-twitter-trends-scraper-2025").call(run_input=run_input)

        print("Scraping finished. Fetching results...")
        dataset_items = client.dataset(actor_run["defaultDatasetId"]).list_items().items
        
        if not dataset_items:
            print("No results found.")
        else:
            print("\n--- Scraped Data ---")
            for item in dataset_items:
                print(json.dumps(item, indent=4))
            print("--------------------\n")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()




