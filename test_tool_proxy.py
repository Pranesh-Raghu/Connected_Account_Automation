# filename: test_tool_proxy.py
import pytest
import requests
import threading
from flask import Flask, request, jsonify

# ---------------------------
# Fake provider server
# ---------------------------
def create_provider_app(captured):
    app = Flask(__name__)

    @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
    def proxy(path):
        # Capture incoming request details
        captured['path'] = '/' + path
        captured['query'] = request.query_string.decode()
        captured['headers'] = dict(request.headers)
        return jsonify({"ok": True})

    return app

def run_provider_server(app, port):
    app.run(port=port, debug=False, use_reloader=False)

# ---------------------------
# Test cases
# ---------------------------
test_cases = [
    {
        "name": "Gmail path version",
        "api_path": "/v1",
        "user_path": "users/me/profile",
        "version": "/v1",
        "version_header": None,
        "expected_path": "/v1/users/me/profile",
        "expected_query": "",
        "expected_header": None,
    },
    {
        "name": "Jira query version",
        "api_path": "/api",
        "user_path": "issues",
        "version": "2024-01",
        "version_header": None,
        "expected_path": "/api/issues",
        "expected_query": "api-version=2024-01",
        "expected_header": None,
    },
    {
        "name": "Header version",
        "api_path": "/resources",
        "user_path": "items",
        "version": "header:X-API-Version:v2",
        "version_header": "v2",
        "expected_path": "/resources/items",
        "expected_query": "",
        "expected_header": "v2",
    },
]

# ---------------------------
# Helper: Build proxied URL
# ---------------------------
def build_proxied_url(base_url, api_path, user_path):
    return base_url + api_path + '/' + user_path

# ---------------------------
# Test function
# ---------------------------
@pytest.mark.parametrize("tc", test_cases)
def test_proxy_versioning(tc):
    captured = {}

    # Start fake provider
    app = create_provider_app(captured)
    port = 5000
    thread = threading.Thread(target=run_provider_server, args=(app, port))
    thread.daemon = True
    thread.start()

    # Build request URL
    base_url = f"http://localhost:{port}"
    proxied_url = build_proxied_url(base_url, tc['api_path'], tc['user_path'])

    # Prepare headers
    headers = {}
    if tc['version_header']:
        # Simulate header-based versioning
        parts = tc['version'].split(":")
        if len(parts) == 3:
            headers[parts[1]] = parts[2]

    # Simulate query-based version if applicable
    params = {}
    if tc['expected_query']:
        params['api-version'] = tc['version']

    # Make the HTTP request (simulate proxy behavior)
    resp = requests.get(proxied_url, headers=headers, params=params)
    assert resp.status_code == 200

    # Validate captured request
    assert captured['path'] == tc['expected_path'], f"Path mismatch: {captured['path']}"
    if tc['expected_query']:
        assert captured['query'] == tc['expected_query'], f"Query mismatch: {captured['query']}"
    if tc['expected_header']:
        assert captured['headers'].get("X-API-Version") == tc['expected_header'], \
            f"Header mismatch: {captured['headers'].get('X-API-Version')}"

    # Stop the server thread (Flask keeps running in daemon)
