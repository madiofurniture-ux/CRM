"""
Tiny static server for the built React app, with SPA fallback.

Python's http.server returns 404 for /inventory because no such file exists —
a single-page app needs every unknown path to serve index.html so the router can
handle it. (On Netlify `_redirects` does this; locally we need our own.)

    python deploy/serve_spa.py --dir frontend/build --port 3000
"""
import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class SPAHandler(SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        path = self.translate_path(self.path)
        # A real file (bundle, image, manifest) → serve it normally.
        if os.path.isfile(path):
            return super().do_GET()
        # Anything else that isn't an asset request → hand back index.html.
        if "." not in os.path.basename(self.path.split("?")[0]):
            self.path = "/index.html"
        return super().do_GET()

    def end_headers(self):
        # Never cache index.html, or a rebuild leaves users on a stale bundle.
        if self.path in ("/", "/index.html"):
            self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, *a):  # quieter console
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="frontend/build")
    ap.add_argument("--port", type=int, default=3000)
    args = ap.parse_args()

    if not os.path.isfile(os.path.join(args.dir, "index.html")):
        raise SystemExit(f"No build found in {args.dir!r} — run deploy/build-frontend.ps1 first.")

    handler = partial(SPAHandler, directory=args.dir)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"frontend on http://127.0.0.1:{args.port}  (serving {args.dir})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
