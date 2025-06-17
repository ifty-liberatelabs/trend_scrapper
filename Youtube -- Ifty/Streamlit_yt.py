import streamlit as st
import os
import json
import requests
import re
import concurrent.futures
import time
import asyncio
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from openai import AsyncOpenAI

# ==============================================================================
# INTACT CODE - EXACTLY AS PROVIDED BY YOU
# All the functions below are from your new 'main.py' script.
# ==============================================================================

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
    # This is a SYNCHRONOUS function, as the library is not async.
    # It will be called within an executor to avoid blocking the async event loop.
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
    """
    Analyzes video data. If a transcript is available, it analyzes the transcript.
    If not, it analyzes the title.
    """
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

# ==============================================================================
# STREAMLIT WRAPPER
# ==============================================================================

async def run_youtube_analysis_pipeline(gl: str, hl: str):
    """
    This function adapts your main logic to be called by Streamlit.
    """
    report_filename = "final_analysis_report.json"

    # --- Load Environment Variables ---
    load_dotenv()
    searchapi_key = os.getenv("SearchAPI_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not all([searchapi_key, openai_api_key]):
        st.error("Error: Required API keys (SearchAPI_KEY, OPENAI_API_KEY) not found in .env file.")
        return None

    # --- Step 1: Fetch Trending Videos (Synchronous) ---
    api_url = "https://www.searchapi.io/api/v1/search"
    params = {"engine": "youtube_trends", "gl": gl, "hl": hl, "api_key": searchapi_key}
    print("Fetching YouTube trends from SearchAPI.io...")
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the API request: {e}")
        st.error(f"An error occurred during the API request: {e}")
        return None

    # --- Step 2: Concurrently Fetch Transcripts ---
    if 'trending' in data and data['trending']:
        videos_to_process = [{'link': v.get('link'), 'title': v.get('title')} for v in data['trending'] if v.get('link') and v.get('title')]
        if not videos_to_process:
            st.warning("No videos with both a link and title were found in the API response.")
            return None

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
            # The 'transcript' can be very long, so we don't need to save it again if we don't want to
            # but for displaying it in the UI, it's useful to keep it.
            combined_item["llm_analysis"] = llm_analyses[i]
            final_report_data.append(combined_item)

        print(f"\nSaving final analysis report to {report_filename}...")
        with open(report_filename, "w", encoding='utf-8') as f:
            # The final JSON has a root key "final_report" as per the original script
            json.dump({"final_report": final_report_data}, f, indent=4, ensure_ascii=False)
        print(f"✅ All done! Report saved to {report_filename}")
        return report_filename
    else:
        st.warning("Warning: 'trending' key not found in the API response.")
        return None

# ==============================================================================
# STREAMLIT UI
# ==============================================================================

st.set_page_config(layout="wide", page_title="YouTube Trend Analyzer")
st.title("🎬 YouTube Trend Analyzer")

st.info(
    "This application fetches trending YouTube videos, downloads their transcripts, and uses AI to create a summary.\n\n"
    "**Note**: Detailed progress is printed to the terminal."
)

with st.sidebar:
    st.header("⚙️ Configuration")
    gl_param = st.text_input("Country Code (gl)", value="NZ", help="Country code for YouTube trends, e.g., US, UK, NZ, BD")
    hl_param = st.text_input("Language Code (hl)", value="en", help="Language for the YouTube trends, e.g., en, es, fr")

    start_button = st.button("Analyze YouTube Trends", type="primary", use_container_width=True)

if start_button:
    with st.spinner("Analyzing YouTube trends... Please check your terminal for detailed logs."):
        report_file_path = asyncio.run(run_youtube_analysis_pipeline(gl=gl_param, hl=hl_param))

    if report_file_path and os.path.exists(report_file_path):
        st.success(f"🎉 Analysis complete! Report saved to `{report_file_path}`.")
        with open(report_file_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
        st.session_state['report_data'] = report_data
        st.session_state['report_file_path'] = report_file_path
    else:
        st.error("Analysis did not complete successfully.")

if 'report_data' in st.session_state:
    st.divider()
    st.header("📊 Analysis Report")

    st.download_button(
        label=f"📥 Download Report ({st.session_state['report_file_path']})",
        data=json.dumps(st.session_state['report_data'], indent=4),
        file_name=st.session_state['report_file_path'],
        mime="application/json"
    )

    # The data is nested under the 'final_report' key
    for item in st.session_state['report_data'].get("final_report", []):
        analysis = item.get("llm_analysis", {})
        
        with st.container(border=True):
            st.subheader(f"Video Title: {item.get('title', 'No title available')}")
            st.markdown(f"**AI Summary:** {analysis.get('context', 'No AI context available.')}")
            
            # Display transcript status and category
            status_color = "green" if item.get('status') == 'Success' else "orange"
            st.caption(f"Transcript Status: :{status_color}[{item.get('status')}] | Category: {analysis.get('category', 'N/A')}")
            
            st.divider()

            st.markdown("**Key Highlights:**")
            summary_points = analysis.get("summary", [])
            if summary_points:
                for point in summary_points:
                    st.markdown(f"- {point}")
            else:
                st.markdown("- No summary points were generated.")

            with st.expander("View Full Transcript"):
                if item.get("status") == "Success":
                    st.markdown(item.get("transcript", "Transcript not available."))
                else:
                    st.warning(f"Transcript could not be fetched. Error: {item.get('error', 'Unknown error')}")

            with st.expander("View Video URL"):
                st.markdown(item.get("video_url", "No URL available."))