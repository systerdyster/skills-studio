#!/usr/bin/env python3
"""The Skills Studio server. Python standard library only.

    skills-studio [--project DIR] [--port N]        (the plugin puts skills-studio on PATH)

Binds to 127.0.0.1 only and prints a URL with a random token; every request must carry that token
(the page sends it as a header) and a local Host. Serves the studio page, the project's graph (scan,
wires, findings), one skill at a time and how much each is used (/skill-doctor), and takes tasks: each is checked against a fresh scan —
only the project's own skills may be changed — and written to .skills-studio/inbox/ for the
session, which alone does the work."""

import argparse
import hmac
import json
import os
import secrets
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent / "bin"))

from sx import graph, insights  # noqa: E402
from sx.insights import InsightsError  # noqa: E402
from sx import usage as skill_usage  # noqa: E402
from sx.state import StudioPaths, running  # noqa: E402
from sx.tasks import TaskError, in_flight, submit  # noqa: E402

HERE = Path(__file__).resolve().parent
MAX_BODY = 256 * 1024
GRAPH_MAX_AGE = 2.0


def live_graph(project, home):
    """Returns a function giving the current graph, rebuilt at most every GRAPH_MAX_AGE seconds."""
    lock = threading.Lock()
    cache = {"at": None, "data": None}

    def current(fresh=False):
        with lock:
            if fresh or cache["at"] is None or time.monotonic() - cache["at"] >= GRAPH_MAX_AGE:
                cache["data"] = graph.build(project, home)
                cache["at"] = time.monotonic()
            return cache["data"]
    return current


def make_handler(project, home, token, port, usage):
    paths = StudioPaths(project)
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    current_graph = live_graph(project, home)

    class Handler(BaseHTTPRequestHandler):
        server_version = "skills-studio"

        def log_message(self, fmt, *args):
            sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

        def _send(self, status, body, content_type="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                             "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj, ensure_ascii=False))

        def _authorised(self):
            if self.headers.get("Host") not in allowed_hosts:
                return False
            supplied = self.headers.get("X-Studio-Token") or parse_qs(urlparse(self.path).query).get("token", [""])[0]
            return hmac.compare_digest(supplied, token)

        def do_GET(self):
            url = urlparse(self.path)
            if not self._authorised():
                return self._json(403, {"error": "missing or wrong token"})
            if url.path == "/":
                page = HERE / "studio.html"
                return self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            if url.path == "/graph":
                data = current_graph()
                return self._json(200, {**data, "skills": [_without_body(s) for s in data["skills"]]})
            if url.path == "/skill":
                wanted = parse_qs(url.query).get("id", [""])[0]
                for skill in current_graph()["skills"]:
                    if skill["id"] == wanted:
                        return self._json(200, skill)
                return self._json(404, {"error": f"no skill {wanted!r}"})
            if url.path == "/usage":
                return self._json(200, _usage_view(usage, current_graph()["skills"]))
            if url.path == "/tasks":
                return self._json(200, {"tasks": [{k: v for k, v in t.items() if k not in ("before", "after")}
                                                  for t in in_flight(paths)]})
            return self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._authorised():
                return self._json(403, {"error": "missing or wrong token"})
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc not in allowed_hosts:
                return self._json(403, {"error": "cross-origin request refused"})
            route = urlparse(self.path).path
            if route not in ("/task", "/close", "/usage", "/dismiss", "/restore"):
                return self._json(404, {"error": "not found"})
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._json(415, {"error": "expected application/json"})
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._json(413, {"error": "body missing or too large"})
            try:
                raw = json.loads(self.rfile.read(length))
                if route == "/close":
                    return self._close()
                if route == "/usage":
                    usage.refresh()
                    return self._json(202, _usage_view(usage, current_graph()["skills"]))
                if route == "/dismiss":
                    insights.dismiss(paths, raw, graph.texts(current_graph(fresh=True)["skills"]))
                    current_graph(fresh=True)
                    return self._json(200, {"dismissed": True})
                if route == "/restore":
                    insights.restore(paths, raw)
                    current_graph(fresh=True)
                    return self._json(200, {"restored": True})
                task = submit(paths, raw, current_graph(fresh=True)["skills"])
            except json.JSONDecodeError:
                return self._json(400, {"error": "invalid JSON"})
            except (TaskError, InsightsError) as e:
                return self._json(400, {"error": str(e)})
            return self._json(202, task)

        def _close(self):
            """Closing from the page: a close task tells the session to stop watching and let go of
            the lease, then the server stops itself (from another thread: shutdown waits for the
            serving loop, which is running this request)."""
            task = submit(paths, {"kind": "close"}, [])
            self._json(202, task)
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        do_PUT = do_DELETE = do_PATCH = lambda self: self._json(405, {"error": "method not allowed"})

    return Handler


def _without_body(skill):
    return {k: v for k, v in skill.items() if k != "body"}


def _usage_view(usage, skills):
    state = usage.state()
    return {"status": state["status"], "fetched_at": state["fetched_at"], "error": state["error"],
            "skills": skill_usage.match(state["rows"], skills)}


def serve(project, home, port=0, token=None, usage=None):
    """The server, not yet serving. `usage` fetches only when asked; run() asks once at start."""
    token = token or secrets.token_urlsafe(24)
    usage = usage or skill_usage.Usage(skill_usage.report_from_claude(Path(project)))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), None)
    bound = httpd.server_address[1]
    httpd.RequestHandlerClass = make_handler(Path(project), Path(home), token, bound, usage)
    httpd.usage = usage
    return httpd, token, bound


def run(project, home, port=0):
    """Serves until interrupted or terminated — or, when this project's studio already runs, prints
    its URL and returns."""
    paths = StudioPaths(project)
    existing = running(paths)
    if existing:
        print(f"Skills Studio: {existing['url']}", flush=True)
        print(f"Already running (pid {existing['pid']}); not starting another.", flush=True)
        return existing
    httpd, token, port = serve(project, home, port)
    httpd.usage.refresh()
    url = f"http://127.0.0.1:{port}/?token={token}"
    paths.ensure()
    paths.server.write_text(json.dumps({
        "url": url, "port": port, "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }))
    os.chmod(paths.server, 0o600)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    print(f"Skills Studio: {url}", flush=True)
    print("Ctrl-C to stop. Anyone with this URL can queue tasks for this project's skills.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        try:
            if json.loads(paths.server.read_text()).get("pid") == os.getpid():
                paths.server.unlink()
        except (OSError, ValueError):
            pass
    return None


def main():
    ap = argparse.ArgumentParser(description="Skills Studio on 127.0.0.1")
    ap.add_argument("--project", default=".", help="project folder (default: current)")
    ap.add_argument("--home", default=str(Path.home()), help="home folder (default: yours)")
    ap.add_argument("--port", type=int, default=0, help="port (default: a free one)")
    args = ap.parse_args()
    run(Path(args.project).resolve(), Path(args.home).resolve(), args.port)


if __name__ == "__main__":
    main()
