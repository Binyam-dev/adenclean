from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"


class AdenCleanHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    if not STATIC_DIR.is_dir():
        raise RuntimeError(f"Static site directory not found: {STATIC_DIR}")

    server = ThreadingHTTPServer(("0.0.0.0", 5000), AdenCleanHandler)
    print("AdenClean is available on port 5000.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down AdenClean.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
