import asyncio
import json
import re
import requests
from openai import AsyncOpenAI
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
import os
os.environ['GRPC_VERBOSITY'] = 'ERROR'

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

async def fetch_transcript_with_gemini(video_data: dict, semaphore: asyncio.Semaphore, model) -> dict:
    """
    Fetches a video transcript using the Gemini model with error handling and retries.
    """
    async with semaphore:
        url = video_data['link']
        title = video_data['title']
        print(f"📄 Retriving context with Gemini for: \"{title}\"")
        
        max_retries = 3
        base_delay = 5

        for attempt in range(max_retries):
            try:
                response = await model.generate_content_async(
                    ["Provide a full and accurate transcript of the audio in this video.", url],
                    request_options={"timeout": 600}
                )
                transcript_text = response.text.replace('\n', ' ')
                video_id = extract_video_id(url)
                return {"title": title, "video_url": url, "video_id": video_id, "status": "Success", "transcript": transcript_text}
            except google_exceptions.ResourceExhausted:
                if attempt < max_retries - 1:
                    wait_time = base_delay * (2 ** attempt)
                    print(f"Rate limit hit for \"{title}\". Retrying in {wait_time}s... (Attempt {attempt + 2}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    continue # Final attempt failed, loop will exit
            except Exception as e:
                # Handle other unexpected errors
                print(f"❌ An unexpected error occurred for \"{title}\": {e}")
                try:
                    video_id = extract_video_id(url)
                except ValueError:
                    video_id = "unknown"
                return {"title": title, "video_url": url, "video_id": video_id, "status": "Failed", "error": str(e)}

        # This block is reached if all retries fail due to rate limiting
        print(f"❌ All retry attempts failed for \"{title}\" due to persistent rate limiting.")
        try:
            video_id = extract_video_id(url)
        except ValueError:
            video_id = "unknown"
        return {"title": title, "video_url": url, "video_id": video_id, "status": "Failed", "error": "All retry attempts failed due to rate limiting."}


async def analyze_transcript_with_openai(client: AsyncOpenAI, semaphore: asyncio.Semaphore, transcript_data: dict) -> dict:
    """
    Analyzes a transcript with OpenAI, with a fallback to title-only analysis.
    """
    async with semaphore:
        trend_title = transcript_data['title']
        if transcript_data.get("status") == "Success" and transcript_data.get("transcript"):
            print(f"🧠 Analyzing TRANSCRIPT for: \"{trend_title}\"")
            prompt = (f"Please analyze the following transcript for the video titled '{trend_title}'. "
                      "Provide a one-sentence, instantly understandable context summary. "
                      "Then, provide a more detailed summary as 5 distinct bullet points. "
                      "Finally, classify the topic into a single category.\n\n"
                      f"Content:\n{transcript_data['transcript'][:15000]}")
        else:
            print(f"🧠 Analyzing TITLE ONLY for: \"{trend_title}\" (transcript failed)")
            prompt = (f"A transcript for the video titled '{trend_title}' is not available. "
                      "Based SOLELY on this title, please perform a trend analysis. "
                      "Infer the likely topic and provide a one-sentence context summary. "
                      "Then, generate up to 5 bullet points speculating on the key aspects of the topic. "
                      "Finally, classify the topic into a single category.")
        function_definition = {
            "name": "format_trend_analysis",
            "description": "Format the trend analysis into a structured JSON object.",
            "parameters": {"type": "object", "properties": {"context": {"type": "string", "description": "A single, concise sentence that summarizes the core event."},
                                                         "summary": {"type": "array", "description": "A list of up to 5 brief, easy-to-understand bullet points summarizing the topic.", "items": {"type": "string"}},
                                                         "category": {"type": "string", "description": "A single category for the news topic."}},
                         "required": ["context", "summary", "category"]}
        }
        try:
            response = await client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], functions=[function_definition], function_call={"name": "format_trend_analysis"})
            return json.loads(response.choices[0].message.function_call.arguments)
        except Exception as e:
            print(f"❌ Error analyzing \"{trend_title}\" with OpenAI: {e}")
            return {"context": "Error during analysis.", "summary": ["Could not generate summary points."], "category": "Error"}

async def run_youtube_analysis_pipeline(searchapi_key: str, openai_api_key: str, gemini_api_key: str, gl: str, hl: str, video_limit: int = 10):
    """
    Runs the full YouTube trend analysis pipeline.
    """
    if not gemini_api_key:
        print("Error: GEMINI_API_KEY is required for the YouTube analysis pipeline.")
        return None
        
    # Configure the Gemini client
    genai.configure(api_key=gemini_api_key)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Fetch trending videos from SearchAPI.io
    api_url = "https://www.searchapi.io/api/v1/search"
    params = {"engine": "youtube_trends", "gl": gl, "hl": hl, "api_key": searchapi_key}
    print("Fetching YouTube trends from SearchAPI.io...")
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the API request: {e}")
        return None

    if 'trending' not in data or not data['trending']:
        print("Warning: 'trending' key not found in the API response.")
        return []
    
    videos_to_process = [{'link': v.get('link'), 'title': v.get('title')} for v in data['trending'] if v.get('link') and v.get('title')]
    
    if video_limit is not None and video_limit > 0:
        print(f"Limiting to the top {video_limit} trending videos.")
        videos_to_process = videos_to_process[:video_limit]

    if not videos_to_process:
        print("No videos with both a link and title were found.")
        return []
    
    # Fetch transcripts using Gemini
    transcript_semaphore = asyncio.Semaphore(10)
    transcript_tasks = [
        fetch_transcript_with_gemini(video, transcript_semaphore, gemini_model)
        for video in videos_to_process
    ]
    transcript_results = await asyncio.gather(*transcript_tasks)
        
    # Analyze transcripts (or titles) with OpenAI
    print(f"\n✅ Transcripts fetched. Now analyzing {len(transcript_results)} items with OpenAI...")
    client = AsyncOpenAI(api_key=openai_api_key)
    analysis_semaphore = asyncio.Semaphore(10)
    analysis_tasks = [analyze_transcript_with_openai(client, analysis_semaphore, result) for result in transcript_results]
    llm_analyses = await asyncio.gather(*analysis_tasks)
    
    # Combine results into the final report
    final_report_data = []
    for i, original_result in enumerate(transcript_results):
        combined_item = original_result.copy()
        combined_item["llm_analysis"] = llm_analyses[i]
        final_report_data.append(combined_item)
        
    print(f"✅ YouTube analysis pipeline complete. Returning {len(final_report_data)} items.")
    return {"final_report": final_report_data}