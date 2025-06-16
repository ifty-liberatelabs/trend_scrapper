import requests
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("SearchAPI_KEY")

url = "https://www.searchapi.io/api/v1/search"
params = {
  "engine": "youtube_trends",
  "bp": "now", #optional, now - All trending content. (Default), music - Music, gaming - Gaming, films - Films.  
  "gl": "us", #optional, Country code. Default is US.
  "hl": "en", #optional, Language code. Default is English.
  "api_key": api_key
}

response = requests.get(url, params=params)
print(response.text)
