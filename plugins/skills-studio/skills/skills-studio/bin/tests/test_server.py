"""The server, run for real on a free port: token and Host are required, tasks are checked before they
reach inbox/, and the graph is the project's scan, wires and findings."""

import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import server  # noqa: E402


def write_skill(root, name, body="# Body\n", description="Does the thing it is named for, when asked."):
    path = Path(root) / name / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"---\nname: {name}\ndescription: \"{description}\"\n---\n{body}")


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.project, self.home = root / "project", root / "home"
        skills = self.project / ".claude" / "skills"
        write_skill(skills, "close-feature", "Run `git-finish`, then `wiki-sync` skill.\n")
        write_skill(skills, "git-finish", description="Merge the branch and remove it once the case is approved.")
        write_skill(self.home / ".claude" / "skills", "brain-tdd", description="Drive a change test-first, red green blue.")
        self.httpd, self.token, self.port = server.serve(self.project, self.home)
        self.httpd_stopped = threading.Event()

        def serve():
            self.httpd.serve_forever(poll_interval=0.02)
            self.httpd_stopped.set()
        threading.Thread(target=serve, daemon=True).start()

    def tearDown(self):
        if not self.httpd_stopped.is_set():
            self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def request(self, method, path, body=None, token=True, host=None, origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            headers["X-Studio-Token"] = self.token
        if origin:
            headers["Origin"] = origin
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        try:
            return response.status, json.loads(raw)
        except ValueError:
            return response.status, raw

    def inbox(self):
        inbox = self.project / ".skills-studio" / "inbox"
        return sorted(inbox.glob("*.json")) if inbox.exists() else []

    def test_no_token_is_refused(self):
        self.assertEqual(self.request("GET", "/graph", token=False)[0], 403)

    def test_wrong_host_is_refused(self):
        self.assertEqual(self.request("GET", "/graph", host="evil.example:80")[0], 403)

    def test_token_in_the_query_opens_the_page(self):
        status, _ = self.request("GET", f"/?token={self.token}", token=False)
        self.assertEqual(status, 200)

    def test_graph_holds_skills_wires_and_findings(self):
        status, graph = self.request("GET", "/graph")
        self.assertEqual(status, 200)
        self.assertEqual({s["id"] for s in graph["skills"]}, {"close-feature", "git-finish", "brain-tdd"})
        self.assertIn({"from": "close-feature", "to": "git-finish"},
                      [{"from": w["from"], "to": w["to"]} for w in graph["wires"]])
        self.assertIn("wire-broken", {f["check"] for f in graph["findings"]})
        self.assertIn({"entry": ["close-feature"], "skills": ["close-feature", "git-finish"]}, graph["flows"])
        self.assertNotIn("body", graph["skills"][0])

    def test_one_skill_with_its_body(self):
        status, skill = self.request("GET", "/skill?id=close-feature")
        self.assertEqual(status, 200)
        self.assertIn("git-finish", skill["body"])

    def test_valid_task_lands_in_inbox(self):
        status, task = self.request("POST", "/task", {"kind": "link", "from": "close-feature", "to": "brain-tdd"})
        self.assertEqual(status, 202)
        self.assertEqual([p.stem for p in self.inbox()], [task["id"]])

    def test_task_naming_a_user_skill_as_target_is_refused(self):
        status, reply = self.request("POST", "/task", {"kind": "change", "skill": "brain-tdd", "text": "x"})
        self.assertEqual(status, 400)
        self.assertIn("read-only", reply["error"])
        self.assertEqual(self.inbox(), [])

    def test_cross_origin_post_is_refused(self):
        status, _ = self.request("POST", "/task", {"kind": "analyse"}, origin="http://evil.example")
        self.assertEqual(status, 403)
        self.assertEqual(self.inbox(), [])

    def test_close_tells_the_session_and_stops_the_server(self):
        status, task = self.request("POST", "/close", {})
        self.assertEqual(status, 202)
        self.assertEqual(task["kind"], "close")
        self.assertEqual([p.stem for p in self.inbox()], [task["id"]])
        self.httpd_stopped.wait(2)
        self.assertTrue(self.httpd_stopped.is_set())

    def test_close_needs_the_token(self):
        self.assertEqual(self.request("POST", "/close", {}, token=False)[0], 403)
        self.assertEqual(self.inbox(), [])

    def test_tasks_in_flight_are_listed(self):
        _, task = self.request("POST", "/task", {"kind": "link", "from": "close-feature", "to": "brain-tdd"})
        status, listed = self.request("GET", "/tasks")
        self.assertEqual(status, 200)
        self.assertEqual([(t["id"], t["state"]) for t in listed["tasks"]], [(task["id"], "waiting")])

    def test_layout_is_empty_before_any(self):
        self.assertEqual(self.request("GET", "/layout"), (200, {"positions": {}}))

    def test_layout_round_trips(self):
        layout = {"positions": {"close-feature": [10, 20.5], "brain-tdd": [300, 40]}}
        self.assertEqual(self.request("POST", "/layout", layout)[0], 200)
        self.assertEqual(self.request("GET", "/layout"), (200, layout))

    def test_malformed_layout_is_refused(self):
        status, _ = self.request("POST", "/layout", {"positions": {"close-feature": ["x", 1]}})
        self.assertEqual(status, 400)
        self.assertEqual(self.request("GET", "/layout"), (200, {"positions": {}}))

    def test_vendored_canvas_library_is_served_without_token(self):
        status, body = self.request("GET", "/vendor/drawflow.min.js", token=False)
        self.assertEqual(status, 200)
        self.assertIn(b"Drawflow", body)

    def test_vendored_library_still_needs_a_local_host(self):
        self.assertEqual(self.request("GET", "/vendor/drawflow.min.js", host="evil.example:80")[0], 403)

    def test_vendor_files_outside_js_and_css_are_not_served(self):
        self.assertEqual(self.request("GET", "/vendor/drawflow.LICENSE")[0], 404)

    def test_analysis_is_empty_before_any(self):
        self.assertEqual(self.request("GET", "/analysis"), (200, {"suggestions": []}))


if __name__ == "__main__":
    unittest.main()
