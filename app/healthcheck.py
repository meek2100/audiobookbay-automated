import os
import sys
import urllib.request


def health_check():
    # Retrieve the port from environment variables, defaulting to 5078
    port = os.getenv("LISTEN_PORT", "5078")
    host = "127.0.0.1"
    url = f"http://{host}:{port}/"

    try:
        # urlopen raises an HTTPError for 4xx/5xx responses, which counts as a failure
        with urllib.request.urlopen(url) as response:
            if response.status == 200:
                sys.exit(0)  # Success
            else:
                sys.exit(1)  # Failure (status code not 200)
    except Exception as e:
        # Print error to stderr so it shows up in docker logs if healthcheck fails
        print(f"Health check failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    health_check()
