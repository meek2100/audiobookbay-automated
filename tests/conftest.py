# tests/conftest.py
from unittest.mock import patch

import pytest

from app import create_app


@pytest.fixture
def app():
    """
    Creates the 'World' for the tests: A Flask application instance
    configured specifically for testing (safe paths, disabled CSRF).
    """
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
            "SAVE_PATH_BASE": "/tmp/test_downloads",
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,  # Disable CSRF for easier functional testing
        }
    )

    yield app


@pytest.fixture
def client(app):
    """
    The observer within the world: A test client to make requests.
    """
    return app.test_client()


@pytest.fixture
def runner(app):
    """
    A CLI runner for command-line context.
    """
    return app.test_cli_runner()


@pytest.fixture(autouse=True)
def mock_sleep():
    """
    Globally mock time.sleep for all tests in this package to speed up execution.
    Automatically applied to all tests.
    """
    with patch("time.sleep") as mock_sleep:
        yield mock_sleep


@pytest.fixture
def real_world_html():
    """Returns a real HTML snippet from Audiobook Bay for testing."""
    return """
<div class="post">
    <div class="postTitle">
        <h2><a href="/abss/a-game-of-thrones-chapterized/" rel="bookmark">A Game of Thrones (A Song of Ice and Fire, Book 1) (Chapterized) - George R. R. Martin</a></h2>
    </div>
    <div class="postInfo">
        Category: Adults&nbsp; Bestsellers&nbsp; Fantasy&nbsp; Literature&nbsp; <br>
        Language: English<span style="margin-left:100px;">Keywords: A Game of Thrones&nbsp; </span><br>
    </div>
    <div class="postContent">
        <div class="center">
            <p class="center">Shared by:<a href="#">jason444555</a></p>
            <p class="center">
                <a href="/abss/a-game-of-thrones-chapterized/">
                    <img src="/images/cover.jpg" alt="A Game of Thrones" width="250">
                </a>
            </p>
        </div>
        <p style="text-align:center;">
            Posted: 14 Sep 2021<br>
            Format: <span style="color:#a00;">M4B</span> / Bitrate: <span style="color:#a00;">96 Kbps</span><br>
            File Size: <span style="color:#00f;">1.37</span> GBs
        </p>
    </div>
</div>
"""


@pytest.fixture
def details_html():
    """Returns a mock Details page HTML."""
    return """
<div class="post">
    <div class="postTitle"><h1>A Game of Thrones</h1></div>
    <div class="postInfo">
        Language: English
    </div>
    <div class="postContent">
        <img itemprop="image" src="/cover.jpg">
        <p>Format: <span>M4B</span> / Bitrate: <span>96 Kbps</span></p>
        <span class="author" itemprop="author">George R.R. Martin</span>
        <span class="narrator" itemprop="author">Roy Dotrice</span>
        <div class="desc">
            <p>This is a great book.</p>
            <a href="https://example.com/spam">Spam Link</a>
        </div>
    </div>
    <table class="torrent_info">
        <tr><td>Tracker:</td><td>udp://tracker.opentrackr.org:1337/announce</td></tr>
        <tr><td>File Size:</td><td>1.37 GBs</td></tr>
        <tr><td>Info Hash:</td><td>eb154ac7886539c4d01eae14908586e336cdb550</td></tr>
    </table>
</div>
"""
