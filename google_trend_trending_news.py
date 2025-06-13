import requests
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("SearchAPI_KEY")

url = "https://www.searchapi.io/api/v1/search"
params = {
  "engine": "google_trends_trending_now_news",
  "news_token": "W1szNzg1OTAzODk1LCJlbiIsIlVTIl0sWzM4MTg0MzM4NzMsImVuIiwiVVMiXSxbMzc5MTEyNDM2OCwiZW4iLCJVUyJdLFszODE4NzIwNDYwLCJlbiIsIlVTIl0sWzM4MDY4MTQ0OTUsImVuIiwiVVMiXSxbMzgxNzAyNjkxNCwiZW4iLCJVUyJdLFszNzg5ODA4NzA2LCJlbiIsIlVTIl0sWzM4MTQ2OTg3MDcsImVuIiwiVVMiXSxbMzc5ODU4OTQ0NiwiZW4iLCJVUyJdXQ==",  
  # Replace with your actual news token (will be obtained from by running google trends trending now API)
  "api_key": api_key
}

response = requests.get(url, params=params)
print(response.text)
