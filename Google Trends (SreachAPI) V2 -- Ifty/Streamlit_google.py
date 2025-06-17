import streamlit as st
import os
import json
import requests
import asyncio
from dotenv import load_dotenv
from firecrawl import AsyncFirecrawlApp, ScrapeOptions
from openai import AsyncOpenAI

# ==============================================================================
# INTACT CODE - EXACTLY AS PROVIDED BY YOU
# ==============================================================================

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
    except requests.exceptions.HTTPError as http_err:
        print(f"❌ HTTP error occurred: {http_err}")
    except requests.exceptions.RequestException as e:
        print(f"❌ An error occurred during the API request: {e}")
    return {}

def generate_and_save_queries(trends_data: dict, output_filename: str = "trend_queries.md"):
    if "trends" not in trends_data or not trends_data["trends"]:
        print("No trends to process.")
        return

    all_queries = []
    # Iterate through each trend in the data
    for trend in trends_data["trends"]:
        keywords = trend.get("keywords", [])
        if not keywords:
            continue
        # Take the top 5 keywords for a more focused query
        top_5_keywords = keywords[:5]
        # Join keywords with "OR" to create a broad search query
        keyword_part = ' OR '.join([f'{kw}' for kw in top_5_keywords])
        # Format the final query string
        final_query = f"query='{keyword_part}'"
        all_queries.append(final_query)

    try:
        # Write all generated queries to the output file
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
            results = await app.search(
                query=actual_query,
                scrape_options=options
            )

            # Check if valid data was returned and extract the markdown
            if results and results.get('data') and results['data'][0].get('markdown'):
                return {
                    "trend_query": actual_query,
                    "scraped_content": results['data'][0]['markdown']
                }
        except Exception as e:
            # Catch any exceptions during the scraping process
            print(f"❌ Error scraping query '{actual_query}': {e}")
    return None

async def analyze_with_openai(client: AsyncOpenAI, semaphore: asyncio.Semaphore, trend_data: dict) -> dict:

    async with semaphore:
        print(f"🧠 Analyzing trend: '{trend_data['trend_query']}'")

        # Define the structured output format we want from the model
        function_definition = {
            "name": "format_trend_analysis",
            "description": "Format the trend analysis into a structured JSON object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "A single, concise sentence that summarizes the core event. Instantly understandable."
                    },
                    "summary": {
                        "type": "array",
                        "description": "A list of 5 brief, easy-to-understand bullet points summarizing the topic in more detail.",
                        "items": {"type": "string"}
                    },
                    "category": {
                        "type": "string",
                        "description": "A single category for the news topic (e.g., 'Technology', 'Sports', 'Politics')."
                    }
                },
                "required": ["context", "summary", "category"]
            }
        }

        try:
            prompt = (
                f"Please analyze the following content about the trend '{trend_data['trend_query']}'. "
                "Provide a one-sentence, instantly understandable context summary. "
                "Then, provide a more detailed summary as 5 distinct bullet points. "
                "Finally, classify the topic into a single category.\n\n"
                f"Content:\n{trend_data['scraped_content'][:15000]}" # Limit content length to be safe
            )

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                functions=[function_definition],
                function_call={"name": "format_trend_analysis"},
            )

            # Extract and parse the JSON from the model's response
            analysis_json = json.loads(response.choices[0].message.function_call.arguments)
            return analysis_json

        except Exception as e:
            print(f"❌ Error analyzing trend '{trend_data['trend_query']}' with OpenAI: {e}")
            return {
                "context": "Error during analysis.",
                "summary": ["Could not generate summary points."],
                "category": "Error"
            }

# ==============================================================================
# STREAMLIT WRAPPER
# ==============================================================================

async def run_analysis_pipeline(geo: str, time: str):
    """
    This function adapts your main logic to be called by Streamlit.
    """
    # Use default filenames from the original script
    trends_output = "trend_queries.md"
    scrape_output = "trend_scrape.json"
    report_output = "trend_analysis_report.json"

    load_dotenv()
    searchapi_key = os.getenv("SearchAPI_KEY")
    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not all([searchapi_key, firecrawl_api_key, openai_api_key]):
        st.error("Error: API keys not found in .env file.")
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

        # ### CHANGE 1: Pass scraped_content to the final report for display ###
        for i, item in enumerate(scraped_results):
            report_item = {
                "trend_query": item["trend_query"],
                "scraped_content": item.get("scraped_content", "Scraped content not available."),
                "llm_analysis": llm_analyses[i]
            }
            final_report.append(report_item)

        with open(report_output, 'w', encoding='utf-8') as f:
            json.dump(final_report, f, indent=4)
    else:
        return None

    return report_output

# ==============================================================================
# STREAMLIT UI
# ==============================================================================

st.set_page_config(layout="wide", page_title="Trend Analysis Runner")
st.title("🚀 Trend Analysis Runner")

st.info(
    "This application runs the provided Python script. Configure the settings in the sidebar and click 'Start Analysis'.\n\n"
    "**Note**: Detailed progress is printed to the terminal."
)

with st.sidebar:
    st.header("⚙️ Configuration")
    geo = st.text_input("Geographic Location", value="NZ", help="e.g., US, UK, NZ, BD")
    time_frame = st.selectbox(
        "Time Frame",
        options=["past_4_hours", "past_12_hours", "past_24_hours", "past_7_days", "past_30_days"],
        index=3
    )
    start_button = st.button("Start Analysis", type="primary", use_container_width=True)

if start_button:
    with st.spinner("Analysis in progress... Please check your terminal for detailed logs."):
        report_file_path = asyncio.run(run_analysis_pipeline(geo, time_frame))

    if report_file_path and os.path.exists(report_file_path):
        st.success(f"🎉 Analysis complete! Report saved to `{report_file_path}`.")
        with open(report_file_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
        st.session_state['report_data'] = report_data
        st.session_state['report_file_path'] = report_file_path
    else:
        st.error("Analysis did not complete successfully.")

# ### CHANGE 2 & 3: Apply the requested formatting to the output display ###
if 'report_data' in st.session_state:
    st.divider()
    st.header("📊 Analysis Report")

    st.download_button(
        label=f"📥 Download Report ({st.session_state['report_file_path']})",
        data=json.dumps(st.session_state['report_data'], indent=4),
        file_name=st.session_state['report_file_path'],
        mime="application/json"
    )

    for item in st.session_state['report_data']:
        analysis = item.get("llm_analysis", {})
        if analysis and analysis.get("context") != "Error during analysis.":
            with st.container(border=True):
                # Request 1: Add "Trend Header:" prefix
                st.subheader(f"Trend Header: {analysis.get('context', 'No context available.')}")
                st.caption(f"Category: {analysis.get('category', 'N/A')}")
                st.divider()

                # Request 2: Add "Key Highlights:" label
                st.markdown("**Key Highlights:**")
                summary_points = analysis.get("summary", [])
                if summary_points:
                    for point in summary_points:
                        st.markdown(f"- {point}")

                # Request 3: Add expander for raw scraped data
                with st.expander("View Raw Scraped Data (Markdown)"):
                    st.markdown(item.get("scraped_content", "No scraped data available."))

                with st.expander("View Original Trend Query"):
                    st.code(item.get("trend_query", "No query found."))