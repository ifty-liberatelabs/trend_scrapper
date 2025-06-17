import requests
from dotenv import load_dotenv
import os
import json
import re
from youtube_transcript_api import YouTubeTranscriptApi
import concurrent.futures
import time

# --- Load Environment Variables ---
load_dotenv()
api_key = os.getenv("SearchAPI_KEY")

# --- Helper Functions ---

def extract_video_id(url):
    """
    Handles various formats of YouTube URLs to extract the video ID.
    Returns the video ID or raises a ValueError if the URL is invalid.
    """
    patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([^&]+)',
        r'(?:https?://)?youtu\.be/([^?&]+)',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/([^?&]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Invalid or unsupported YouTube URL format: {url}")

def fetch_transcript_for_video(video_data, languages=['en'], max_retries=3):
    """
    Fetches a transcript for a single video, using its link and title.
    Includes a retry mechanism for handling transient failures.
    """
    url = video_data['link']
    title = video_data['title']
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            video_id = extract_video_id(url)
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
            transcript_text = " ".join(entry['text'] for entry in transcript_list).replace('\n', ' ')
            
            # On success, include the title in the return value
            return {
                "title": title,
                "video_url": url,
                "video_id": video_id,
                "status": "Success",
                "transcript": transcript_text
            }
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                # Use the title in the retry message
                print(f"  [RETRY {attempt + 1}/{max_retries}] Failed to fetch \"{title}\". Retrying in 2 seconds...")
                time.sleep(2)

    # If all retries fail, include the title in the error object
    video_id_on_fail = "unknown"
    try:
        video_id_on_fail = extract_video_id(url)
    except ValueError:
        pass

    return {
        "title": title,
        "video_url": url,
        "video_id": video_id_on_fail,
        "status": "Failed",
        "error": f"All {max_retries + 1} attempts failed. Last error: {last_exception}"
    }

# --- Main Execution Logic ---

def main():
    """
    Main function to run the entire pipeline.
    """
    if not api_key:
        print("Error: SearchAPI_KEY not found in .env file or environment variables.")
        return

    # --- Step 1: Fetch Trending Videos ---
    api_url = "https://www.searchapi.io/api/v1/search"
    params = {"engine": "youtube_trends", "gl": "NZ", "hl": "en", "api_key": api_key}
    
    print("Fetching YouTube trends from SearchAPI.io...")
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()
        
        with open("youtube_trends_output.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("Successfully saved full API data to youtube_trends_output.json")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the API request: {e}")
        return
    except json.JSONDecodeError:
        print("Failed to parse JSON from the response.")
        return

    # --- Step 2: Extract Video Data and Fetch Transcripts Concurrently ---
    if 'trending' in data and data['trending']:
        # Create a list of dictionaries, each containing the link and title
        videos_to_process = [
            {'link': video.get('link'), 'title': video.get('title')}
            for video in data['trending'] if video.get('link') and video.get('title')
        ]
        
        if not videos_to_process:
            print("No videos with both a link and title were found.")
            return

        print(f"\nFound {len(videos_to_process)} videos to process. Fetching transcripts concurrently...")
        
        all_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_video = {executor.submit(fetch_transcript_for_video, video): video for video in videos_to_process}
            
            for i, future in enumerate(concurrent.futures.as_completed(future_to_video), 1):
                video_data = future_to_video[future]
                try:
                    result = future.result()
                    all_results.append(result)
                    # Use the title in the progress message for better feedback
                    print(f"({i}/{len(videos_to_process)}) Processed: \"{video_data['title']}\" - Status: {result['status']}")
                except Exception as exc:
                    print(f"({i}/{len(videos_to_process)}) \"{video_data['title']}\" generated an unexpected exception: {exc}")

        # --- Step 3: Save the Aggregated Results to a Single JSON File ---
        print("\nSaving all fetched data to a single file...")
        final_output = {"video_transcripts_and_titles": all_results}
        with open("all_transcripts.json", "w", encoding="utf-8") as f_all:
            json.dump(final_output, f_all, indent=2, ensure_ascii=False)
        print("Successfully saved all transcript data to all_transcripts.json")

    else:
        print("Warning: 'trending' key not found in the API response.")

if __name__ == "__main__":
    main()