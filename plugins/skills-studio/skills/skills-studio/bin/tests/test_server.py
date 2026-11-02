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
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def tearDown(self):
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

    def test_analysis_is_empty_before_any(self):
        self.assertEqual(self.request("GET", "/analysis"), (200, {"suggestions": []}))


if __name__ == "__main__":
    unittest.main()
