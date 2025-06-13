import os
import json
from apify_client import ApifyClient
from dotenv import load_dotenv

def main():
    load_dotenv()
    apify_api_key = os.getenv("APIFY_KEY")

    client = ApifyClient(apify_api_key)

    run_input = {
        "isDownloadVideo": False,       # Set to true to download the video files (can be slow).
        "isDownloadVideoCover": False,  # Set to true to download the video's cover image/thumbnail.
        "limit": 10,                    # The maximum number of trending videos to retrieve.
        "region": "IN"                  # The two-letter country code for the target region (IN = India).
    }

    try:
        print("Starting the Tiktok Trends scraper...")
        actor_run = client.actor("novi/tiktok-trend-api").call(run_input=run_input)

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
