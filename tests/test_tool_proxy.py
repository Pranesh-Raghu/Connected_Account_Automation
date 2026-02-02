import os
import json
import socket
import threading
from typing import Any, Dict, Optional
import pytest
import requests
import yaml
from flask import Flask, request, jsonify, make_response
from dotenv import load_dotenv

import scalekit.client
from scalekit.common.exceptions import ScalekitNotFoundException

load_dotenv()

def load_test_cases_from_yaml(file_path: str) -> list:
    with open(file_path, "r") as f:
        return yaml.safe_load(f).get("provider_test_cases", [])

PROVIDER_TEST_CASES = load_test_cases_from_yaml(
    os.path.join(os.path.dirname(__file__), "provider_testcases.yaml")
)

client = scalekit.client.ScalekitClient(
    env_url=os.getenv("SCALEKIT_ENV_URL"),
    client_id=os.getenv("SCALEKIT_CLIENT_ID"),
    client_secret=os.getenv("SCALEKIT_CLIENT_SECRET"),
)

def get_connected_account_token(connection_name: str, identifier: str) -> Optional[str]:
    try:
        resp = client.actions.get_connected_account(
            connection_name=connection_name,
            identifier=identifier,
        )
    except ScalekitNotFoundException:
        pytest.skip(f"Connected account not found for connection_name='{connection_name}', identifier='{identifier}'")
    # DO NOT log or return the token here. Only use it for the Authorization header.
    return (resp.connected_account.authorization_details.get("oauth_token", {}) or {}).get("access_token")

def get_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def _proxy_handler_factory(captured: dict):
    def handler(path):
        # Collect request body for inspection
        req_body = request.get_data(as_text=True)
        captured['body'] = req_body

        # Make sure to capture the request headers
        captured['headers'] = dict(request.headers)

        # Always return some dummy informative response body for the test
        resp_json = {"received": req_body}
        resp_obj = make_response(jsonify(resp_json), 200)

        # Also capture the response that will be sent, as a string (real body)
        # Flask jsonify returns application/json and its data is available via get_data(as_text=True)
        resp_body = resp_obj.get_data(as_text=True)
        captured['response_raw'] = resp_body
        captured['response'] = resp_json

        return resp_obj
    return handler

def create_provider_app(captured: dict) -> Flask:
    app = Flask(__name__)
    app.add_url_rule(
        '/<path:path>',
        view_func=_proxy_handler_factory(captured),
        methods=['GET', 'POST']
    )
    return app

def run_provider_server(app: Flask, port: int):
    app.run(port=port, debug=False, use_reloader=False)

def build_url(api_path: str, user_path: str) -> str:
    # The call should be api_path + proxy path, not using env_url.
    api = api_path.rstrip("/")
    user = user_path.lstrip("/")
    if user:
        return f"{api}/{user}"
    return f"{api}"

@pytest.mark.parametrize("tc", PROVIDER_TEST_CASES)
def test_tool_proxy(tc: Dict[str, Any]):
    captured: Dict[str, Any] = {}

    app = create_provider_app(captured)
    port = get_free_port()
    thread = threading.Thread(target=run_provider_server, args=(app, port), daemon=True)
    thread.start()

    import time
    time.sleep(0.3)

    # The actual call should be api_path + proxy path, not via env_url.
    url = build_url(tc.get("api_path", ""), tc.get("user_path", ""))
    token = get_connected_account_token(tc.get("connection_name", ""), "Pranesh")
    method = tc.get("method")
    body = tc.get("body")

    headers = {"Authorization": f"Bearer {token}"}

    if method == "GET":
        resp = requests.get(url, headers=headers)
    else:
        if body is not None:
            resp = requests.post(url, headers=headers, json=body)
        else:
            headers["Content-Type"] = "application/json"
            resp = requests.post(url, headers=headers, data="{}")

    # Log the HTTP response body in all formats (str, bytes, json if possible)
    # Also immediately log status code and all response headers for debugging.
    print("\n========== HTTP RESPONSE ==========")
    print("Status code:", resp.status_code)
    print("Headers:", dict(resp.headers))
    print("---------- BODY FORMATS ----------")
    try:
        print("As string:", resp.text)
    except Exception as e:
        print("Could not decode as text:", e)

    try:
        print("As bytes:", resp.content)
    except Exception as e:
        print("Could not get as bytes:", e)

    try:
        print("As JSON:", resp.json())
    except Exception:
        print("Response not valid JSON")

    print("==================================")

    # Flush stdout to guarantee printing during pytest runs
    import sys
    sys.stdout.flush()