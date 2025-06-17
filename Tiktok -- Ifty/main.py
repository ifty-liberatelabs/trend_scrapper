import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

# Set your endpoint
API_URL = "https://api.openai.com/v1/audio/transcriptions"  # Change if your endpoint is different

def transcribe_tiktok(tiktok_url):
    payload = {
        "model": "gpt-4o-mini-transcribe",
        "response_format": "json",
        "task": "transcription",
        "tiktokUrl": tiktok_url
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    response = requests.post(API_URL, headers=headers, json=payload)
    if response.status_code == 200:
        print("Transcription Result:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    url = input("Enter TikTok URL: ").strip()
    transcribe_tiktok(url)
