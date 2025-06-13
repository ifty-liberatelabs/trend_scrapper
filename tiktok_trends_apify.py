import os
import json
from datetime import datetime
from apify_client import ApifyClient
from dotenv import load_dotenv

def preprocess_data(raw_data):
    """
    Extracts key fields from raw TikTok data and preprocesses them for analysis.
    """
    processed_list = []
    for item in raw_data:
        # Get the list of challenges/hashtags, defaulting to an empty list if it's None or missing.
        cha_list = item.get("cha_list") or []
        # Extract hashtags into a simple list of strings
        hashtags = [tag.get("cha_name", "") for tag in cha_list]

        # Convert Unix timestamp to a human-readable ISO 8601 format
        created_at_unix = item.get("create_time", 0)
        created_at_iso = datetime.utcfromtimestamp(created_at_unix).isoformat() + "Z"

        processed_item = {
            "source_id": item.get("aweme_id"),
            "created_at": created_at_iso,
            "description": item.get("desc", "").strip(),
            "hashtags": hashtags,
            "statistics": item.get("statistics", {}),
            "author": {
                "nickname": item.get("author", {}).get("nickname"),
                "unique_id": item.get("author", {}).get("unique_id"),
                "region": item.get("author", {}).get("region")
            },
            "music": {
                "title": item.get("music", {}).get("title"),
                "author": item.get("music", {}).get("authorName")
            },
            "video_duration_seconds": item.get("video", {}).get("duration", 0) / 1000.0
        }
        processed_list.append(processed_item)
        
    return processed_list

def main():
    """
    Main function to scrape, preprocess, and display TikTok data.
    """
    load_dotenv()
    apify_api_key = os.getenv("APIFY_KEY")

    if not apify_api_key:
        print("Error: APIFY_KEY environment variable not found.")
        print("Please create a .env file and add your Apify API key.")
        return

    client = ApifyClient(apify_api_key)

    run_input = {
        "isDownloadVideo": False,
        "isDownloadVideoCover": False,
        "limit": 10,
        "region": "IN"
    }

    try:
        # Step 1: Scrape the raw data
        print("Starting the Tiktok Trends scraper...")
        actor_run = client.actor("novi/tiktok-trend-api").call(run_input=run_input)

        print("Scraping finished. Fetching raw results...")
        raw_dataset_items = client.dataset(actor_run["defaultDatasetId"]).list_items().items
        
        if not raw_dataset_items:
            print("No results found from the scraper.")
            return
            
        # Save raw data to original file
        with open("tiktok.json", "w", encoding="utf-8") as f:
            json.dump(raw_dataset_items, f, ensure_ascii=False, indent=4)
        print("Raw output saved to tiktok.json")

        # Step 2: Preprocess the data
        print("\nPreprocessing the data...")
        preprocessed_data = preprocess_data(raw_dataset_items)

        # Step 3: Show the preprocessed data
        print("\n--- Preprocessed Trend Data ---")
        for item in preprocessed_data:
            print(json.dumps(item, indent=4, ensure_ascii=False))
        print("-----------------------------\n")

        # Save the preprocessed data to a new file
        with open("tiktok_preprocessed.json", "w", encoding="utf-8") as f:
            json.dump(preprocessed_data, f, ensure_ascii=False, indent=4)
        print("Preprocessed output saved to tiktok_preprocessed.json")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()