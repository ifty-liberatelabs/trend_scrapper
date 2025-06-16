import os
import json
import requests
from dotenv import load_dotenv

def fetch_google_trends(api_key: str, geo: str = "NZ", time: str = "past_7_days") -> dict:

    url = "https://www.searchapi.io/api/v1/search"
    params = {
      "engine": "google_trends_trending_now",
      "geo": geo,
      "time": time,
      "api_key": api_key
    }
    
    print(f"Fetching Google Trends for geo='{geo}'...")
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ An error occurred during the API request: {e}")
        return {}

def main():
    load_dotenv()
    api_key = os.getenv("SearchAPI_KEY")

    if not api_key:
        print("Error: SearchAPI_KEY environment variable not found.")
        print("Please create a .env file and add your SearchAPI.io key.")
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "google_trending_now.json")

    data = fetch_google_trends(api_key=api_key, geo="NZ", time="past_7_days")

    if data:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"✅ Data successfully saved to {output_path}")
        
        print("\n--- Fetched Data Output ---")
        print(json.dumps(data, indent=4))
    else:
        print("No data was fetched.")


if __name__ == "__main__":
    main()
