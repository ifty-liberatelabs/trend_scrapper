import os
import json
from apify_client import ApifyClient
from dotenv import load_dotenv

def get_tiktok_trends(api_key: str, region_code: str = "NZ", limit: int = 5) -> list:

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
    processed_list = []
    for i, item in enumerate(raw_data):
        processed_item = {
            "video_number": i + 1,
            "description": item.get("desc", "").strip(),
            "link": item.get("share_url")
        }
        processed_list.append(processed_item)
    return processed_list

def save_to_json(data: list, file_path: str):

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"✅ Simplified data successfully saved to {file_path}")
    except Exception as e:
        print(f"❌ Could not save data to {file_path}. Error: {e}")

def main():
    load_dotenv()
    apify_api_key = os.getenv("APIFY_KEY")

    if not apify_api_key:
        print("Error: APIFY_KEY environment variable not found.")
        return

    # 1. Fetch the raw data
    raw_dataset_items = get_tiktok_trends(api_key=apify_api_key)
    
    if not raw_dataset_items:
        print("No raw data fetched. Exiting.")
        return
    
    # 2. Preprocess the data into the simplified format
    print("\nSimplifying raw data...")
    simplified_data = preprocess_tiktok_data(raw_dataset_items)

    # 3. Save the simplified data to a new JSON file
    save_to_json(simplified_data, "tiktok_simplified.json")
    
    # Optional: Display the simplified data in the console
    print("\n--- Simplified Data Preview ---")
    print(json.dumps(simplified_data, indent=4, ensure_ascii=False))
    print("-------------------------------\n")


if __name__ == "__main__":
    main()