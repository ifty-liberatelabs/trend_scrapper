import requests
from dotenv import load_dotenv
import os
import json

# --- Load Environment Variables ---
load_dotenv()
api_key = os.getenv("SearchAPI_KEY")

# --- Check for API Key ---
if not api_key:
    print("Error: SearchAPI_KEY not found in .env file or environment variables.")
    exit()

# --- API Request Parameters ---
url = "https://www.searchapi.io/api/v1/search"
params = {
    "engine": "youtube_trends",
    "bp": "now",
    "gl": "NZ",
    "hl": "en",
    "api_key": api_key
}

print("Fetching YouTube trends from SearchAPI.io...")

try:
    # --- Execute the API Request ---
    response = requests.get(url, params=params)
    response.raise_for_status()

    # --- Process the Successful Response ---
    # Save the raw JSON data to a file
    with open("youtube_trends_output.json", "w", encoding="utf-8") as f:
        f.write(response.text)
    print("Successfully saved full data to youtube_trends_output.json")

    # Parse the JSON for further processing
    data = response.json()

    # --- Generate the Markdown File ---
    if 'trending' in data and data['trending']:
        with open("youtube_trends.md", "w", encoding="utf-8") as md_file:
            md_file.write("# New Zealand YouTube Trends\n\n")
            md_file.write("This file lists the current trending videos by position and provides a direct link.\n\n")

            for video in data['trending']:
                position = video.get('position')
                link = video.get('link')

                if position is not None and link is not None:
                    md_file.write(f"* **Position {position}:** {link}\n")
        
        print("Successfully generated youtube_trends.md with trend positions and links.")
    else:
        print("Warning: 'trending' key not found or empty in the API response. MD file not generated.")

    # --- NEW: Re-analyze JSON and save only links ---
    print("\nRe-analyzing JSON to extract links...")
    if 'trending' in data and data['trending']:
        # Extract all the 'link' values from the 'trending' list
        trending_links = [video.get('link') for video in data['trending'] if 'link' in video]
        
        # Create a new dictionary to hold the list of links
        links_output = {'trending_links': trending_links}
        
        # Save the new data to a separate JSON file
        with open("youtube_trending_links.json", "w", encoding="utf-8") as f_links:
            json.dump(links_output, f_links, indent=2, ensure_ascii=False)
            
        print("Successfully saved extracted links to youtube_trending_links.json")
    else:
        print("Warning: 'trending' key not found in the data. Cannot extract links.")


except requests.exceptions.RequestException as e:
    print(f"An error occurred during the API request: {e}")
except json.JSONDecodeError:
    print("Failed to parse JSON from the response. The API might be down or returned invalid data.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")