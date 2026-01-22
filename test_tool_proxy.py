import os
from dotenv import load_dotenv
import pytest
import requests
import threading
from flask import Flask, request, jsonify
import scalekit.client
import socket
import time

# Load environment variables from .env
load_dotenv()

# Initialize Scalekit client using env variables
client = scalekit.client.ScalekitClient(
    env_url=os.environ.get("SCALEKIT_ENV_URL"),
    client_id=os.environ.get("SCALEKIT_CLIENT_ID"),
    client_secret=os.environ.get("SCALEKIT_CLIENT_SECRET")
)

def get_connected_account_token(connection_name, identifier):
    actions = client.actions
    response = actions.get_connected_account(
        connection_name=connection_name,
        identifier=identifier
    )
    oauth = response.connected_account.authorization_details.get("oauth_token", {})
    return oauth.get("access_token"), oauth.get("refresh_token")

# Function to get a free port
def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port

# Fake provider server
def create_provider_app(captured):
    app = Flask(__name__)

    @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
    def proxy(path):
        captured['path'] = '/' + path
        captured['query'] = request.query_string.decode()
        captured['headers'] = dict(request.headers)
        return jsonify({"ok": True})

    return app

def run_provider_server(app, port):
    app.run(port=port, debug=False, use_reloader=False)

# Test cases
test_cases = [
    {
        "name": "Gmail path version",
        "connection_name": "gmail",
        "identifier": "Pranesh",
        "api_path": "/v1",
        "user_path": "users/me/profile",
        "version": "/v1",
        "expected_path": "/v1/users/me/profile",
    },
    {
        "name": "Google Analytics header version",
        "connection_name": "google_analytics",
        "identifier": "Pranesh",
        "api_path": "/analytics",
        "user_path": "report",
        "version": "header:X-API-Version:v2",
        "expected_path": "/analytics/report",
        "expected_header": "v2",
    },
]

# Build proxied URL
def build_proxied_url(base_url, api_path, user_path):
    return f"{base_url.rstrip('/')}/{api_path.lstrip('/').rstrip('/')}/{user_path.lstrip('/')}"

# Test function
@pytest.mark.parametrize("tc", test_cases)
def test_proxy_versioning(tc):
    captured = {}

    # Start fake provider on a dynamic free port
    app = create_provider_app(captured)
    port = get_free_port()
    thread = threading.Thread(target=run_provider_server, args=(app, port))
    thread.daemon = True
    thread.start()

    # Wait a bit for the server to start
    time.sleep(0.5)

    base_url = f"http://localhost:{port}"
    proxied_url = build_proxied_url(base_url, tc['api_path'], tc['user_path'])

    # Fetch real access token from Scalekit
    access_token, _ = get_connected_account_token(tc['connection_name'], tc['identifier'])

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # Apply header versioning if needed
    if tc.get("version") and tc["version"].startswith("header:"):
        parts = tc["version"].split(":")
        if len(parts) == 3:
            headers[parts[1]] = parts[2]

    # Apply query-based versioning if applicable
    params = {}
    if tc.get("version") and not tc["version"].startswith("header:"):
        params["api-version"] = tc["version"]

    # Make the HTTP request
    resp = requests.get(proxied_url, headers=headers, params=params)
    assert resp.status_code == 200, f"HTTP request failed: {resp.status_code} {resp.text}"

    # Validate captured request
    assert captured['path'] == tc['expected_path'], f"Path mismatch: {captured['path']}"
    if tc.get("expected_header"):
        headers_lower = {k.lower(): v for k, v in captured['headers'].items()}
        assert headers_lower.get("x-api-version") == tc["expected_header"], \
            f"Header mismatch: {captured['headers'].get('X-API-Version')}"

