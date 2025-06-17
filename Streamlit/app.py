import streamlit as st
import os
import json
import asyncio
from dotenv import load_dotenv

# Import the modularized analysis pipelines
from google_analyzer import run_google_analysis_pipeline
from youtube_analyzer import run_youtube_analysis_pipeline

# --- Streamlit Page Configuration ---
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
    # Load API keys from .env file
    load_dotenv()
    searchapi_key = os.getenv("SearchAPI_KEY")
    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    st.session_state['analysis_type'] = analysis_type
    
    with st.spinner(f"Analyzing {analysis_type}... Please check your terminal for detailed logs."):
        report_data = None
        if analysis_type == "Google Trends":
            if not all([searchapi_key, firecrawl_api_key, openai_api_key]):
                st.error("Error: API keys for SearchAPI, Firecrawl, and OpenAI not found in .env file.")
            else:
                report_data = asyncio.run(run_google_analysis_pipeline(
                    searchapi_key=searchapi_key, 
                    firecrawl_api_key=firecrawl_api_key, 
                    openai_api_key=openai_api_key,
                    geo=geo_param, 
                    time=time_frame_param
                ))
        else: # YouTube Trends
            if not all([searchapi_key, openai_api_key]):
                st.error("Error: API keys for SearchAPI and OpenAI not found in .env file.")
            else:
                report_data = asyncio.run(run_youtube_analysis_pipeline(
                    searchapi_key=searchapi_key,
                    openai_api_key=openai_api_key,
                    gl=geo_param,
                    hl=hl_param
                ))

    if report_data:
        st.success(f"🎉 Analysis complete! Displaying results below.")
        st.session_state['report_data'] = report_data
    else:
        st.error("Analysis did not complete successfully or returned no data.")

# --- Report Display ---
if 'report_data' in st.session_state:
    st.divider()
    st.header("📊 Analysis Report")
    
    # Define a dynamic file name for the download button
    report_filename = f"{st.session_state['analysis_type'].lower().replace(' ', '_')}_report.json"
    
    st.download_button(
        label=f"📥 Download Report ({report_filename})",
        data=json.dumps(st.session_state['report_data'], indent=4),
        file_name=report_filename,
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