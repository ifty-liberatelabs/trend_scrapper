import os
import json
from datetime import datetime
from apify_client import ApifyClient
from dotenv import load_dotenv

def get_tiktok_trends(api_key: str, region_code: str = "NZ", limit: int = 5) -> list:
    """
    Connects to the Apify API to fetch raw trending TikTok video data.

    Args:
        api_key: Your Apify API key.
        region_code: The two-letter country code for the target region.
        limit: The maximum number of trending videos to retrieve.

    Returns:
        A list of raw data items for trending videos, or an empty list if an error occurs.
    """
    try:
        client = ApifyClient(api_key)
        run_input = {
            "isDownloadVideo": False,
            "isDownloadVideoCover": False,
            "limit": limit,
            "region": region_code
        }
        print(f"Starting the TikTok Trends scraper for region '{region_code}'...")
        actor_run = client.actor("novi/tiktok-trend-api").call(run_input=run_input)
        
        print("Scraping finished. Fetching results...")
        dataset_items = client.dataset(actor_run["defaultDatasetId"]).list_items().items
        return dataset_items
    except Exception as e:
        print(f"❌ An error occurred while fetching data: {e}")
        return []

def preprocess_tiktok_data(raw_data: list) -> list:
    """
    Extracts key fields from raw TikTok data and preprocesses them for analysis,
    excluding author information as requested.

    Args:
        raw_data: A list of raw video data dictionaries from the API.

    Returns:
        A list of cleaned and preprocessed video data dictionaries.
    """
    processed_list = []
    for item in raw_data:
        cha_list = item.get("cha_list") or []
        hashtags = [tag.get("cha_name", "") for tag in cha_list]
        created_at_unix = item.get("create_time", 0)
        created_at_iso = datetime.utcfromtimestamp(created_at_unix).isoformat() + "Z"

        processed_item = {
            "source_id": item.get("aweme_id"),
            "created_at": created_at_iso,
            "description": item.get("desc", "").strip(),
            "hashtags": hashtags,
            "statistics": item.get("statistics", {}),
            "music": {
                "title": item.get("music", {}).get("title"),
                "author": item.get("music", {}).get("author") # Corrected from "authorName"
            },
            "video_duration_seconds": item.get("video", {}).get("duration", 0) / 1000.0
        }
        processed_list.append(processed_item)
        
    return processed_list

def save_to_json(data: list, file_path: str):
    """
    Saves a list of dictionary data to a JSON file.

    Args:
        data: The list of data to save.
        file_path: The full path for the output file.
    """
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"✅ Data successfully saved to {file_path}")
    except Exception as e:
        print(f"❌ Could not save data to {file_path}. Error: {e}")

def main():
    """
    Main orchestrator function.
    """
    load_dotenv()
    apify_api_key = os.getenv("APIFY_KEY")

    if not apify_api_key:
        print("Error: APIFY_KEY environment variable not found.")
        return

    # 1. Fetch the raw data
    raw_dataset_items = get_tiktok_trends(api_key=apify_api_key, region_code="IN", limit=10)
    
    if not raw_dataset_items:
        print("No raw data fetched. Exiting.")
        return
        
    save_to_json(raw_dataset_items, "tiktok_raw.json")

    # 2. Preprocess the data
    print("\nPreprocessing the data...")
    preprocessed_data = preprocess_tiktok_data(raw_dataset_items)

    # 3. Show and save the preprocessed data
    print("\n--- Preprocessed Trend Data (Author data removed) ---")
    print(json.dumps(preprocessed_data, indent=4, ensure_ascii=False))
    print("-----------------------------------------------------\n")
    save_to_json(preprocessed_data, "tiktok_preprocessed.json")

if __name__ == "__main__":
    main()
