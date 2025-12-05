import os
import json
import webbrowser
import requests
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID")
CLIENT_SECRET = os.getenv("UPSTOX_CLIENT_SECRET")
REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI")

AUTH_URL = (
    "https://api.upstox.com/v2/login/authorization/dialog"
    f"?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
)
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"

app = Flask(__name__)
auth_code = None


def update_env_token(token):
    env_file = ".env"
    lines = []
    with open(env_file, "r") as f:
        lines = f.readlines()

    with open(env_file, "w") as f:
        for line in lines:
            if line.startswith("UPSTOX_ACCESS_TOKEN="):
                f.write(f"UPSTOX_ACCESS_TOKEN={token}\n")
            else:
                f.write(line)


@app.route("/")
def capture_token_root():
    global auth_code
    auth_code = request.args.get("code")
    return "Authentication Successful. You may close this window now."


def exchange_code_for_token(code):
    payload = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    res = requests.post(TOKEN_URL, data=payload)

    if res.status_code != 200:
        raise Exception(f"Token Exchange Failed: {res.text}")

    data = res.json()
    access_token = data.get("access_token")

    update_env_token(access_token)
    print("Access token updated in .env file.")

    return data


def get_token():
    global auth_code

    # Start Flask server
    import threading
    server = threading.Thread(
        target=lambda: app.run(port=80, debug=False, use_reloader=False)
    )
    server.daemon = True
    server.start()

    # Open browser for login
    print("Opening Upstox login page...")
    webbrowser.open(AUTH_URL)

    print("Waiting for login... OTP + Allow + Redirect...")
    while auth_code is None:
        pass

    print("Auth code received. Exchanging for token...")
    print("Auth Code:", auth_code)
    return exchange_code_for_token(auth_code)


if __name__ == "__main__":
    token = get_token()
    print("New token:", token["access_token"])
