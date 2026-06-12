
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN = "8848818821:AAHleXHHqPZN35Pp_27pNn0pfSsQXL5Fq9M"

url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

response = requests.get(url, verify=False)
print(response.json())