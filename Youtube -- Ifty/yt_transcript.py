from youtube_transcript_api import YouTubeTranscriptApi
import re
import json

def extract_video_id(url):
    # Handles various formats of YouTube URLs
    patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([^&]+)',  # Standard URL
        r'(?:https?://)?youtu\.be/([^?&]+)',                      # Shortened URL
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/([^?&]+)'    # Embed URL
    ]
    for pattern in patterns:
        match = re.match(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Invalid YouTube URL.")

def fetch_transcript(url, languages=['en']):
    try:
        video_id = extract_video_id(url)
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
        llm_text = " ".join(entry['text'] for entry in transcript)
        llm_output = {
            "video_url": url,
            "video_id": video_id,
            "transcript": llm_text
        }
        print(json.dumps(llm_output, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    url = input("Paste your YouTube video link: ").strip()
    fetch_transcript(url)
