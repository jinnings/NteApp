import requests

API_KEY = "b441d269-3828-408e-95ce-33964e359c98"
API_SECRET = "1mns0p4y1v"
REDIRECT_URI = "https://127.0.0.1:5000/"
CODE = "4XGfCC"

url = "https://api.upstox.com/v2/login/authorization/token"

data = {
    "code": CODE,
    "client_id": API_KEY,
    "client_secret": API_SECRET,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code"
}

headers = {
    "accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded"
}

response = requests.post(url, data=data, headers=headers)

print(response.json())