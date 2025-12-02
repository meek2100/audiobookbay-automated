def test_csrf_protection_enabled(app):
    """
    Verify that POST requests are rejected without a CSRF token
    when protection is actually enabled.
    This ensures that our security headers work in production mode.
    """
    # Temporarily enable CSRF for this specific test
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()

    # Attempt a POST request without the token (simulating an attack)
    response = client.post("/send", json={"link": "http://test.com", "title": "Test Book"})

    # Should fail with 400 Bad Request (CSRF Error)
    assert response.status_code == 400
    # Flask-WTF usually returns a text/html error or a 400 with a description
    # We check that it didn't succeed (200) and likely contains CSRF specific text if in debug,
    # or just the standard 400 code.
    assert b"The CSRF token is missing" in response.data or response.status_code == 400
