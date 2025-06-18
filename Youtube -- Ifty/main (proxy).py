import requests
from dotenv import load_dotenv
import os
import json
import re
from youtube_transcript_api import YouTubeTranscriptApi
import concurrent.futures
import time
import asyncio
from openai import AsyncOpenAI

load_dotenv()
searchapi_key = os.getenv("SearchAPI_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")


def extract_video_id(url):
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

    url = video_data['link']
    title = video_data['title']
    print(f"📄 Fetching transcript for: \"{title}\"")
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            video_id = extract_video_id(url)
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
            transcript_text = " ".join(entry['text'] for entry in transcript_list).replace('\n', ' ')
            return {"title": title, "video_url": url, "video_id": video_id, "status": "Success", "transcript": transcript_text}
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                time.sleep(2)
    return {"title": title, "video_url": url, "video_id": "unknown", "status": "Failed", "error": f"All attempts failed. Last error: {last_exception}"}

async def analyze_transcript_with_openai(client: AsyncOpenAI, semaphore: asyncio.Semaphore, transcript_data: dict) -> dict:

    async with semaphore:
        trend_title = transcript_data['title']

        # Check if the transcript is available and create the appropriate prompt
        if transcript_data.get("status") == "Success" and transcript_data.get("transcript"):
            print(f"🧠 Analyzing TRANSCRIPT for: \"{trend_title}\"")
            prompt = (
                f"Please analyze the following transcript for the video titled '{trend_title}'. "
                "Provide a one-sentence, instantly understandable context summary. "
                "Then, provide a more detailed summary as 5 distinct bullet points. "
                "Finally, classify the topic into a single category.\n\n"
                f"Content:\n{transcript_data['transcript'][:15000]}"
            )
        else:
            print(f"🧠 Analyzing TITLE ONLY for: \"{trend_title}\" (transcript failed)")
            prompt = (
                f"A transcript for the video titled '{trend_title}' is not available. "
                "Based SOLELY on this title, please perform a trend analysis. "
                "Infer the likely topic and provide a one-sentence context summary. "
                "Then, generate up to 5 bullet points speculating on the key aspects of the topic. If you can only infer a few points, that is acceptable. "
                "Finally, classify the topic into a single category. Your analysis will be based on inference and common knowledge related to the title."
            )

        function_definition = {
            "name": "format_trend_analysis",
            "description": "Format the trend analysis into a structured JSON object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "A single, concise sentence that summarizes the core event. Instantly understandable."},
                    "summary": {"type": "array", "description": "A list of up to 5 brief, easy-to-understand bullet points summarizing the topic.", "items": {"type": "string"}},
                    "category": {"type": "string", "description": "A single category for the news topic (e.g., 'Technology', 'Sports', 'Politics')."}
                },
                "required": ["context", "summary", "category"]
            }
        }
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                functions=[function_definition],
                function_call={"name": "format_trend_analysis"},
            )
            return json.loads(response.choices[0].message.function_call.arguments)
        except Exception as e:
            print(f"❌ Error analyzing \"{trend_title}\" with OpenAI: {e}")
            return {"context": "Error during analysis.", "summary": ["Could not generate summary points."], "category": "Error"}


async def main():
    """
    Main asynchronous function to run the entire pipeline.
    """
    if not all([searchapi_key, openai_api_key]):
        print("Error: Required API keys (SearchAPI_KEY, OPENAI_API_KEY) not found in .env file.")
        return

    # --- Step 1: Fetch Trending Videos (Synchronous) ---
    api_url = "https://www.searchapi.io/api/v1/search"
    params = {"engine": "youtube_trends", "gl": "NZ", "hl": "en", "api_key": searchapi_key}
    print("Fetching YouTube trends from SearchAPI.io...")
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the API request: {e}")
        return

    # --- Step 2: Concurrently Fetch Transcripts ---
    if 'trending' in data and data['trending']:
        videos_to_process = [{'link': v.get('link'), 'title': v.get('title')} for v in data['trending'] if v.get('link') and v.get('title')]
        if not videos_to_process:
            print("No videos with both a link and title were found.")
            return

        transcript_results = []
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            tasks = [loop.run_in_executor(executor, fetch_transcript_for_video, video) for video in videos_to_process]
            transcript_results = await asyncio.gather(*tasks)

        # --- Step 3: Concurrently Analyze with OpenAI ---
        print(f"\n✅ Transcripts fetched. Now analyzing {len(transcript_results)} items with OpenAI...")
        client = AsyncOpenAI(api_key=openai_api_key)
        analysis_semaphore = asyncio.Semaphore(10)
        analysis_tasks = [analyze_transcript_with_openai(client, analysis_semaphore, result) for result in transcript_results]
        llm_analyses = await asyncio.gather(*analysis_tasks)

        # --- Step 4: Combine All Data and Save Final Report ---
        final_report_data = []
        for i, original_result in enumerate(transcript_results):
            combined_item = original_result.copy()
            combined_item["llm_analysis"] = llm_analyses[i]
            final_report_data.append(combined_item)

        print("\nSaving final analysis report...")
        with open("final_analysis_report.json", "w", encoding='utf-8') as f:
            json.dump({"final_report": final_report_data}, f, indent=4, ensure_ascii=False)
        print("✅ All done! Report saved to final_analysis_report.json")
    else:
        print("Warning: 'trending' key not found in the API response.")

if __name__ == "__main__":
    asyncio.run(main())