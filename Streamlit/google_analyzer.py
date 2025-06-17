import asyncio
import json
import os
import requests
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

def generate_trend_queries(trends_data: dict) -> list:
    if "trends" not in trends_data or not trends_data["trends"]:
        print("No trends to process.")
        return []
    all_queries = []
    for trend in trends_data["trends"]:
        keywords = trend.get("keywords", [])
        if not keywords:
            continue
        top_5_keywords = keywords[:5]
        keyword_part = ' OR '.join([f'{kw}' for kw in top_5_keywords])
        all_queries.append(f"query='{keyword_part}'")
    print(f"✅ Successfully generated {len(all_queries)} queries.")
    return all_queries

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

async def analyze_scraped_content(client: AsyncOpenAI, semaphore: asyncio.Semaphore, trend_data: dict) -> dict:
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

async def run_google_analysis_pipeline(searchapi_key: str, firecrawl_api_key: str, openai_api_key: str, geo: str, time: str):
    trends_data = fetch_google_trends(api_key=searchapi_key, geo=geo, time=time)
    if not trends_data:
        print("Could not fetch trends data. Aborting pipeline.")
        return []

    all_queries = generate_trend_queries(trends_data)
    if not all_queries:
        print("No queries were generated. Aborting pipeline.")
        return []

    app = AsyncFirecrawlApp(api_key=firecrawl_api_key)
    scrape_semaphore = asyncio.Semaphore(15)
    scrape_tasks = [search_and_scrape_task(app, scrape_semaphore, query) for query in all_queries]
    scraped_results = await asyncio.gather(*scrape_tasks)
    scraped_results = [res for res in scraped_results if res] # Filter out None results
    
    if not scraped_results:
        print("Scraping did not yield any results. Aborting analysis.")
        return []

    client = AsyncOpenAI(api_key=openai_api_key)
    analysis_semaphore = asyncio.Semaphore(10)
    analysis_tasks = [analyze_scraped_content(client, analysis_semaphore, item) for item in scraped_results]
    llm_analyses = await asyncio.gather(*analysis_tasks)
    
    final_report = []
    for i, item in enumerate(scraped_results):
        report_item = {
            "trend_query": item["trend_query"], 
            "scraped_content": item.get("scraped_content", "Scraped content not available."), 
            "llm_analysis": llm_analyses[i]
        }
        final_report.append(report_item)
        
    print(f"✅ Google analysis pipeline complete. Returning {len(final_report)} items.")
    return final_report