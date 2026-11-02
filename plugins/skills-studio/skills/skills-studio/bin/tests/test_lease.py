"""One studio session per project: the lease. It lapses unless renewed, so a session that died
does not hold the project for ever."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sx import lease
from sx.lease import LeaseHeld
from sx.state import StudioPaths

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


class LeaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = StudioPaths(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_free_lease_is_taken(self):
        held = lease.take(self.paths, "session-a", now=T0)
        self.assertEqual(held["holder"], "session-a")

    def test_holder_may_take_it_again(self):
        lease.take(self.paths, "session-a", now=T0)
        lease.take(self.paths, "session-a", now=T0 + timedelta(minutes=5))

    def test_live_lease_of_another_session_is_refused(self):
        lease.take(self.paths, "session-a", now=T0)
        with self.assertRaises(LeaseHeld) as caught:
            lease.take(self.paths, "session-b", now=T0 + timedelta(minutes=10))
        self.assertEqual(caught.exception.lease["holder"], "session-a")

    def test_lapsed_lease_is_taken_over(self):
        lease.take(self.paths, "session-a", now=T0)
        held = lease.take(self.paths, "session-b", now=T0 + lease.TTL + timedelta(seconds=1))
        self.assertEqual(held["holder"], "session-b")

    def test_renew_keeps_it_alive(self):
        lease.take(self.paths, "session-a", now=T0)
        lease.renew(self.paths, "session-a", now=T0 + lease.TTL - timedelta(minutes=1))
        with self.assertRaises(LeaseHeld):
            lease.take(self.paths, "session-b", now=T0 + lease.TTL + timedelta(minutes=1))

    def test_renew_by_another_session_is_refused(self):
        lease.take(self.paths, "session-a", now=T0)
        with self.assertRaises(LeaseHeld):
            lease.renew(self.paths, "session-b", now=T0)

    def test_release_frees_it(self):
        lease.take(self.paths, "session-a", now=T0)
        lease.release(self.paths, "session-a")
        lease.take(self.paths, "session-b", now=T0)

    def test_release_removes_a_lapsed_lease_too(self):
        lease.take(self.paths, "session-a", now=datetime(2020, 1, 1, tzinfo=timezone.utc))
        lease.release(self.paths, "session-a")
        self.assertFalse(self.paths.lease.exists())

    def test_release_by_another_session_leaves_it(self):
        lease.take(self.paths, "session-a", now=T0)
        lease.release(self.paths, "session-b")
        with self.assertRaises(LeaseHeld):
            lease.take(self.paths, "session-b", now=T0)

    def test_unreadable_lease_counts_as_free(self):
        self.paths.root.mkdir(parents=True)
        self.paths.lease.write_text("{not json")
        lease.take(self.paths, "session-a", now=T0)


if __name__ == "__main__":
    unittest.main()
