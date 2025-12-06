import os

from . import create_app

# Create the application instance using the factory.
# This global 'app' variable is what Gunicorn looks for by default.
app = create_app()

if __name__ == "__main__":  # pragma: no cover
    # NOTE: This block is for local debugging only. Production uses entrypoint.sh.
    # Local Development Entry Point
    host = os.getenv("LISTEN_HOST", "0.0.0.0")  # nosec B104

    port_str = os.getenv("LISTEN_PORT", "5078")
    try:
        port = int(port_str)
    except ValueError:
        print(f"Invalid LISTEN_PORT '{port_str}'. Defaulting to 5078.")
        port = 5078

    app.run(host=host, port=port)
