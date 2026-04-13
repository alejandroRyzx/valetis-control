import urllib.request
import urllib.error
import json
import base64

with open('static/valetis-logo.png', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode('utf-8')

app_id = "u458i170nltDI9"
api_key = "zOjPzh4QjEYfflpJH0urT9Zr40Z0E9LpoKjQfEYEb8MI4pHTcj"

payload = {
    "app_id": app_id,
    "key": api_key,
    "image": img_b64
}

req = urllib.request.Request(
    "https://zpk.systems/api/plate-scanner",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req) as response:
        print("Success:", response.read().decode())
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code)
    print("Body:", e.read().decode())
except Exception as e:
    print("Other Error:", e)
