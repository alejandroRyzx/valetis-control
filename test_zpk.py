import urllib.request
import urllib.error
import json
import base64

with open('static/valetis-logo.png', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode('utf-8')

app_id = "u454i168nm3j5M"
api_key = "nxQDBePua5Uj3l9wrjA5BxsCIBUWpo6ifs8cYLlDLuxt7RSOBy"

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
