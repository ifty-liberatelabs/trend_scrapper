import streamlit as st
import os
import json
import requests
import asyncio
import re
import time
import concurrent.futures
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from firecrawl import AsyncFirecrawlApp, ScrapeOptions
from openai import AsyncOpenAI


def fetch_google_trends(api_key: str, geo: str, time: str) -> dict:
    url = "https://www.searchapi.io/api/v1/search"
    params = {
        "engine": "google_trends_trending_now",
        "geo": geo,
        "time": time,
        "api_key": api_key
    }
    print(f"Fetching Google Trends for geo='{geo}' and time='{time}'...")
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ An error occurred during the API request: {e}")
    return {}

def generate_and_save_queries(trends_data: dict, output_filename: str = "trend_queries.md"):
    if "trends" not in trends_data or not trends_data["trends"]:
        print("No trends to process.")
        return
    all_queries = []
    for trend in trends_data["trends"]:
        keywords = trend.get("keywords", [])
        if not keywords:
            continue
        top_5_keywords = keywords[:5]
        keyword_part = ' OR '.join([f'{kw}' for kw in top_5_keywords])
        final_query = f"query='{keyword_part}'"
        all_queries.append(final_query)
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            for query_line in all_queries:
                f.write(query_line + '\n')
        print(f"✅ Successfully saved {len(all_queries)} queries to {output_filename}")
    except IOError as e:
        print(f"❌ Error saving queries to file: {e}")

async def search_and_scrape_task(app: AsyncFirecrawlApp, semaphore: asyncio.Semaphore, query: str) -> dict:
    actual_query = query.split("=")[1].strip("'")
    async with semaphore:
        print(f"🔎 Scraping for: '{actual_query}'")
        try:
            options = ScrapeOptions(formats=['markdown'])
            results = await app.search(query=actual_query, scrape_options=options)
            if results and results.get('data') and results['data'][0].get('markdown'):
                return {"trend_query": actual_query, "scraped_content": results['data'][0]['markdown']}
        except Exception as e:
            print(f"❌ Error scraping query '{actual_query}': {e}")
    return None

async def analyze_with_openai(client: AsyncOpenAI, semaphore: asyncio.Semaphore, trend_data: dict) -> dict:
    async with semaphore:
        print(f"🧠 Analyzing trend: '{trend_data['trend_query']}'")
        function_definition = {
            "name": "format_trend_analysis",
            "description": "Format the trend analysis into a structured JSON object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "A single, concise sentence that summarizes the core event. Instantly understandable."},
                    "summary": {"type": "array", "description": "A list of 5 brief, easy-to-understand bullet points summarizing the topic.", "items": {"type": "string"}},
                    "category": {"type": "string", "description": "A single category for the news topic (e.g., 'Technology', 'Sports')."}
                }, "required": ["context", "summary", "category"]
            }
        }
        try:
            prompt = (
                f"Please analyze the following content about the trend '{trend_data['trend_query']}'. "
                "Provide a one-sentence, instantly understandable context summary. "
                "Then, provide a more detailed summary as 5 distinct bullet points. "
                "Finally, classify the topic into a single category.\n\n"
                f"Content:\n{trend_data['scraped_content'][:15000]}"
            )
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                functions=[function_definition],
                function_call={"name": "format_trend_analysis"},
            )
            return json.loads(response.choices[0].message.function_call.arguments)
        except Exception as e:
            print(f"❌ Error analyzing trend '{trend_data['trend_query']}' with OpenAI: {e}")
            return {"context": "Error during analysis.", "summary": ["Could not generate summary points."], "category": "Error"}

async def run_google_analysis_pipeline(geo: str, time: str):
    trends_output = "trend_queries.md"
    scrape_output = "trend_scrape.json"
    report_output = "google_trend_analysis_report.json"
    load_dotenv()
    searchapi_key = os.getenv("SearchAPI_KEY")
    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not all([searchapi_key, firecrawl_api_key, openai_api_key]):
        st.error("Error: API keys for SearchAPI, Firecrawl, and OpenAI not found in .env file.")
        return None
    trends_data = fetch_google_trends(api_key=searchapi_key, geo=geo, time=time)
    all_queries = []
    if trends_data:
        generate_and_save_queries(trends_data, trends_output)
        try:
            with open(trends_output, 'r', encoding='utf-8') as f:
                all_queries = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            st.error(f"Error: Could not find {trends_output}.")
            return None
    else:
        st.warning("Could not fetch trends data.")
        return None
    scraped_results = []
    if all_queries:
        app = AsyncFirecrawlApp(api_key=firecrawl_api_key)
        scrape_semaphore = asyncio.Semaphore(15)
        tasks = [search_and_scrape_task(app, scrape_semaphore, query) for query in all_queries]
        results = await asyncio.gather(*tasks)
        scraped_results = [res for res in results if res]
        with open(scrape_output, 'w', encoding='utf-8') as f:
            json.dump(scraped_results, f, indent=4)
    else:
        return None
    final_report = []
    if scraped_results:
        client = AsyncOpenAI(api_key=openai_api_key)
        analysis_semaphore = asyncio.Semaphore(10)
        analysis_tasks = [analyze_with_openai(client, analysis_semaphore, item) for item in scraped_results]
        llm_analyses = await asyncio.gather(*analysis_tasks)
        for i, item in enumerate(scraped_results):
            report_item = {"trend_query": item["trend_query"], "scraped_content": item.get("scraped_content", "Scraped content not available."), "llm_analysis": llm_analyses[i]}
            final_report.append(report_item)
        with open(report_output, 'w', encoding='utf-8') as f:
            json.dump(final_report, f, indent=4)
    else:
        return None
    return report_output



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

async def run_youtube_analysis_pipeline(gl: str, hl: str):
    report_filename = "youtube_final_analysis_report.json"
    load_dotenv()
    searchapi_key = os.getenv("SearchAPI_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not all([searchapi_key, openai_api_key]):
        st.error("Error: Required API keys (SearchAPI_KEY, OPENAI_API_KEY) not found in .env file.")
        return None
    api_url = "https://www.searchapi.io/api/v1/search"
    params = {"engine": "youtube_trends", "gl": gl, "hl": hl, "api_key": searchapi_key}
    print("Fetching YouTube trends from SearchAPI.io...")
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"An error occurred during the API request: {e}")
        return None
    if 'trending' in data and data['trending']:
        videos_to_process = [{'link': v.get('link'), 'title': v.get('title')} for v in data['trending'] if v.get('link') and v.get('title')]
        if not videos_to_process:
            st.warning("No videos with both a link and title were found.")
            return None
        transcript_results = []
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
        print(f"\nSaving final analysis report to {report_filename}...")
        with open(report_filename, "w", encoding='utf-8') as f:
            json.dump({"final_report": final_report_data}, f, indent=4, ensure_ascii=False)
        print(f"✅ All done! Report saved to {report_filename}")
        return report_filename
    else:
        st.warning("Warning: 'trending' key not found in the API response.")
        return None


st.set_page_config(layout="wide", page_title="Trend Analyzer")
st.title("Trend Analyzer")
st.info("Select an analysis type, configure the options in the sidebar, and click 'Start Analysis'.")

# --- Sidebar for Configuration ---
with st.sidebar:
    st.header("⚙️ Configuration")
    analysis_type = st.selectbox("1. Select Analysis Type", ["Google Trends", "YouTube Trends"])
    
    st.divider()

    if analysis_type == "Google Trends":
        st.subheader("Google Trends Settings")
        geo_param = st.text_input("Geographic Location (geo)", value="NZ", help="Country code, e.g., US, UK, NZ, BD")
        time_frame_param = st.selectbox("Time Frame", ["past_4_hours", "past_12_hours", "past_24_hours", "past_7_days"], index=2)
    else: # YouTube Trends
        st.subheader("YouTube Trends Settings")
        geo_param = st.text_input("Country Code (gl)", value="NZ", help="Country code for YouTube trends, e.g., US, UK, NZ, BD")
        hl_param = st.text_input("Language Code (hl)", value="en", help="Language for the YouTube trends, e.g., en, es, fr")

    start_button = st.button("Start Analysis", type="primary", use_container_width=True)

# --- Main App Logic ---
if start_button:
    st.session_state['analysis_type'] = analysis_type # Store analysis type for display logic
    with st.spinner(f"Analyzing {analysis_type}... Please check your terminal for detailed logs."):
        if analysis_type == "Google Trends":
            report_file_path = asyncio.run(run_google_analysis_pipeline(geo=geo_param, time=time_frame_param))
        else: # YouTube Trends
            report_file_path = asyncio.run(run_youtube_analysis_pipeline(gl=geo_param, hl=hl_param))

    if report_file_path and os.path.exists(report_file_path):
        st.success(f"🎉 Analysis complete! Report saved to `{report_file_path}`.")
        with open(report_file_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
        st.session_state['report_data'] = report_data
        st.session_state['report_file_path'] = report_file_path
    else:
        st.error("Analysis did not complete successfully.")

# --- Report Display ---
if 'report_data' in st.session_state:
    st.divider()
    st.header("📊 Analysis Report")
    
    st.download_button(
        label=f"📥 Download Report ({st.session_state.get('report_file_path', 'report.json')})",
        data=json.dumps(st.session_state['report_data'], indent=4),
        file_name=st.session_state.get('report_file_path', 'report.json'),
        mime="application/json"
    )

    # --- Display Logic for GOOGLE TRENDS ---
    if st.session_state.get('analysis_type') == "Google Trends":
        report_items = st.session_state['report_data']
        for item in report_items:
            analysis = item.get("llm_analysis", {})
            if analysis and analysis.get("context") != "Error during analysis.":
                with st.container(border=True):
                    st.subheader(f"Trend Header: {analysis.get('context', 'No context available.')}")
                    st.caption(f"Category: {analysis.get('category', 'N/A')}")
                    st.divider()
                    st.markdown("**Key Highlights:**")
                    summary_points = analysis.get("summary", [])
                    if summary_points:
                        for point in summary_points:
                            st.markdown(f"- {point}")
                    with st.expander("View Raw Scraped Data (Markdown)"):
                        st.markdown(item.get("scraped_content", "No scraped data available."))
                    with st.expander("View Original Trend Query"):
                        st.code(item.get("trend_query", "No query found."))

    # --- Display Logic for YOUTUBE TRENDS ---
    elif st.session_state.get('analysis_type') == "YouTube Trends":
        report_items = st.session_state['report_data'].get("final_report", [])
        for item in report_items:
            analysis = item.get("llm_analysis", {})
            with st.container(border=True):
                st.subheader(f"Video Title: {item.get('title', 'No title available')}")
                st.markdown(f"**AI Summary:** {analysis.get('context', 'No AI context available.')}")
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
