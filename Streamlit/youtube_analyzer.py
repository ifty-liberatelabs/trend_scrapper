# youtube_analyzer.py
import asyncio
import json
import re
import time
import requests
import concurrent.futures
from youtube_transcript_api import YouTubeTranscriptApi
from openai import AsyncOpenAI

def extract_video_id(url):
    patterns = [r'watch\?v=([^&]+)', r'youtu\.be/([^?&]+)', r'embed/([^?&]+)']
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

async def run_youtube_analysis_pipeline(searchapi_key: str, openai_api_key: str, gl: str, hl: str):
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
    if not videos_to_process:
        print("No videos with both a link and title were found.")
        return []
        
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        tasks = [loop.run_in_executor(executor, fetch_transcript_for_video, video) for video in videos_to_process]
        transcript_results = await asyncio.gather(*tasks)
        
    print(f"\n✅ Transcripts fetched. Now analyzing {len(transcript_results)} items with OpenAI...")
    client = AsyncOpenAI(api_key=openai_api_key)
    analysis_semaphore = asyncio.Semaphore(10)
    analysis_tasks = [analyze_transcript_with_openai(client, analysis_semaphore, result) for result in transcript_results]
    llm_analyses = await asyncio.gather(*analysis_tasks)
    
    final_report_data = []
    for i, original_result in enumerate(transcript_results):
        combined_item = original_result.copy()
        combined_item["llm_analysis"] = llm_analyses[i]
        final_report_data.append(combined_item)
        
    print(f"✅ YouTube analysis pipeline complete. Returning {len(final_report_data)} items.")
    return {"final_report": final_report_data}