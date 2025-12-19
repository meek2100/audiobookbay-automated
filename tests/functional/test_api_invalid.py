# File: tests/functional/test_api_invalid.py
"""Functional tests for invalid API inputs."""

import json


def test_send_invalid_title_type(client):
    """Test that sending an integer title to /send returns a 400 error."""
    payload = {
        "link": "http://example.com/details",
        "title": 12345,  # Invalid: Should be a string
    }

    response = client.post("/send", data=json.dumps(payload), content_type="application/json")

    assert response.status_code == 400
    assert "Title must be a string" in response.get_json()["message"]
