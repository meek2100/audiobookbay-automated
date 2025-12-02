import os
import sys
import urllib.request


def health_check(timeout: int = 3):
    """
    Performs a health check against the local Flask application.
    Exits with 0 on success, 1 on failure.

    Args:
        timeout: The maximum time in seconds to wait for a response.
    """
    # Retrieve the port from environment variables, defaulting to 5078
    port = os.getenv("LISTEN_PORT", "5078")
    # Health check should always query localhost inside the container
    host = "127.0.0.1"
    # OPTIMIZATION: Use dedicated health endpoint (lighter than hitting the home page)
    url = f"http://{host}:{port}/health"

    try:
        # TIMEOUT ADDED: Prevents the healthcheck from hanging indefinitely
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status == 200:
                sys.exit(0)  # Success
            else:
                print(f"Health check failed with status: {response.status}", file=sys.stderr)
                sys.exit(1)  # Failure
    except Exception as e:
        # Print error to stderr so it shows up in docker logs if healthcheck fails
        print(f"Health check failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    health_check(timeout=3)
