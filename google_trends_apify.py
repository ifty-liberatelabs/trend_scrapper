import os
import json
from apify_client import ApifyClient
from dotenv import load_dotenv

def main():
    load_dotenv()
    apify_api_key = os.getenv("APIFY_KEY")

    client = ApifyClient(apify_api_key)

    run_input = {
        "geo": "IN",                    # The geographic region for the search (IN = India).
        "isMultiple": False,            # Set to true if you are comparing multiple search terms.
        "isPublic": False,              # Determines if the run's results are publicly visible on Apify.
        "searchTerms": ["webscraping"], # The list of keywords to search for on Google Trends.
        "skipDebugScreen": False,       # A developer option to bypass a debugging screen on the scraper.
        "timeRange": "now 1-d",         # The time frame for the trend data (last 24 hours).
        "viewedFrom": "in",             # The country code to simulate viewing the results from.
    }

    try:
        print("Starting the Google Trends scraper...")
        actor_run = client.actor("emastra/google-trends-scraper").call(run_input=run_input)

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
