import os
import json
import requests
import argparse
import asyncio
from dotenv import load_dotenv
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

async def main():

    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description="Fetch, Scrape, Analyze, and Report on Google Trends.")
    parser.add_argument("--geo", type=str, default="NZ", help="Geographic location for Google Trends (e.g., 'US', 'NZ').")
    parser.add_argument("--time", type=str, default="past_7_days", help="Time frame for Google Trends (e.g., 'past_24_hours').")
    parser.add_argument("--trends_output", type=str, default="trend_queries.md", help="Output file for trend queries.")
    parser.add_argument("--scrape_output", type=str, default="trend_scrape.json", help="Output file for the scraped content.")
    parser.add_argument("--report_output", type=str, default="trend_analysis_report.json", help="Output file for the final enhanced JSON report.")
    args = parser.parse_args()

    # Load environment variables from a .env file
    load_dotenv()
    searchapi_key = os.getenv("SearchAPI_KEY")
    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    # Ensure all required API keys are available
    if not all([searchapi_key, firecrawl_api_key, openai_api_key]):
        print("Error: One or more API keys not found. Please create a .env file with SearchAPI_KEY, FIRECRAWL_API_KEY, and OPENAI_API_KEY.")
        return

    # Step 1: Fetch the Google Trends data
    trends_data = fetch_google_trends(api_key=searchapi_key, geo=args.geo, time=args.time)

    # Step 2: Generate and save search queries from the trends data
    all_queries = []
    if trends_data:
        generate_and_save_queries(trends_data, args.trends_output)
        try:
            with open(args.trends_output, 'r', encoding='utf-8') as f:
                all_queries = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Error: Could not find {args.trends_output} to read queries.")
            return
    else:
        print("Could not fetch trends data. Exiting.")
        return

    # Step 3: Concurrently scrape the web for each query
    scraped_results = []
    if all_queries:
        app = AsyncFirecrawlApp(api_key=firecrawl_api_key)
        scrape_semaphore = asyncio.Semaphore(15)
        
        print(f"🔥 Starting concurrent scrape for {len(all_queries)} queries...")
        tasks = [search_and_scrape_task(app, scrape_semaphore, query) for query in all_queries]
        results = await asyncio.gather(*tasks)
        scraped_results = [res for res in results if res]

        with open(args.scrape_output, 'w', encoding='utf-8') as f:
            json.dump(scraped_results, f, indent=4)
        print(f"\n✅ Full scrape of {len(scraped_results)} items saved to {args.scrape_output}")
    else:
        print("No queries were available to process for scraping.")
        return
        
    # Step 4: Concurrently analyze each scraped item with the LLM
    final_report = []
    if scraped_results:
        client = AsyncOpenAI(api_key=openai_api_key)
        analysis_semaphore = asyncio.Semaphore(10) # Semaphore for OpenAI API to avoid rate limits
        print(f"\n🤖 Starting concurrent LLM analysis for {len(scraped_results)} items...")

        analysis_tasks = [analyze_with_openai(client, analysis_semaphore, item) for item in scraped_results]
        llm_analyses = await asyncio.gather(*analysis_tasks)
        
        # Combine original data with the new analysis, excluding scraped_content
        for i, item in enumerate(scraped_results):
            report_item = {
                "trend_query": item["trend_query"],
                "llm_analysis": llm_analyses[i]
            }
            final_report.append(report_item)

        # Step 5: Save the final, enhanced report
        with open(args.report_output, 'w', encoding='utf-8') as f:
            json.dump(final_report, f, indent=4)
        print(f"\n🎉 Success! Full analysis of {len(final_report)} items saved to {args.report_output}")
    else:
        print("No scraped content was available to analyze.")

if __name__ == "__main__":
    asyncio.run(main())
