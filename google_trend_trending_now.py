import requests
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("SearchAPI_KEY")

url = "https://www.searchapi.io/api/v1/search"
params = {
  "engine": "google_trends_trending_now",
  "geo": "US",
  "time": "past_7_days",
  "api_key": api_key
}

response = requests.get(url, params=params)
print(response.text)
