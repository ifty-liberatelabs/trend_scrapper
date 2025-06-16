import requests

# Requirements: 
# Required Business account 
# Required to setup an app with proper app details
# The app details will be reviewed by developer
# After getting approved the bearer token for authentication can be used
# Usage: 
# Has trends api:  GET /trends/keywords/{region}/top/{trend_type} 
# here region is the location (e.g. US,CA) and trend_type are keywords like (e.g. growth, mothly, yearly)
# headers uses bearer token

bearer_token = '<your_bearer_token_here>'  #this token should be obtained after setting up the app and getting it approved


region = 'US'  # Example region
trend_type = 'growth'  # Example trend type


headers = {
    'Authorization': f'Bearer {bearer_token}',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}

response = requests.get('https://api.pinterest.com/v5/trends/keywords/{region}/top/{trend_type}?region={region}&trend_type={trend_type}', headers=headers)
if response.status_code == 200:
    data = response.json()
    print(data)
    