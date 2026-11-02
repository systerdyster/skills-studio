"""Layout writes are atomic and safe when two arrive at once: the page saves on move and on drop."""

import tempfile
import threading
import unittest
from pathlib import Path

from sx import layout
from sx.state import StudioPaths


class ConcurrentWriteTest(unittest.TestCase):
    def test_simultaneous_writes_all_succeed(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = StudioPaths(Path(tmp))
            errors = []

            def write(n):
                try:
                    for _ in range(30):
                        layout.write(paths, {"positions": {"a": [n, n]}})
                except Exception as error:  # noqa: BLE001 - any failure fails the test
                    errors.append(error)

            threads = [threading.Thread(target=write, args=(n,)) for n in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            self.assertIn(layout.read(paths)["positions"]["a"][0], range(6))
            self.assertEqual(sorted(p.name for p in paths.root.iterdir()), ["layout.json"])


if __name__ == "__main__":
    unittest.main()
