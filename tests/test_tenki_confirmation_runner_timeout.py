import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from ygo_eval.native_tenki_placement_confirmation import _normal_runner_timeout, _run_process


class ConfirmationRunnerTimeoutTests(unittest.TestCase):
    def test_timeout_uses_remaining_window_after_a_slow_precharge_scan(self):
        timeout = _normal_runner_timeout({"started_at": 1000}, now=1061.25)
        self.assertAlmostEqual(timeout, 7138.75)
        self.assertGreater(timeout, 60)

    def test_timeout_rejects_clock_before_window_start(self):
        with self.assertRaisesRegex(ValueError, "confirmation_window_clock_before_start"):
            _normal_runner_timeout({"started_at": 1000}, now=999.99)

    def test_timeout_rejects_exactly_thirty_seconds_remaining(self):
        with self.assertRaisesRegex(ValueError, "confirmation_window_insufficient_time"):
            _normal_runner_timeout({"started_at": 1000}, now=8170)

    def test_timeout_rejects_malformed_frozen_start(self):
        for value in (True, -1, 1000.0, "1000"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "confirmation_window_start_invalid"):
                    _normal_runner_timeout({"started_at": value}, now=1001)

    def test_normal_runner_requires_and_forwards_the_computed_window_timeout(self):
        repo = Path(__file__).resolve().parents[1]
        scratch = repo / "data/runtime/p1-tenki-runner-repair-offline-2026-10-23/test-fixtures" / f"timeout-{uuid4().hex}"
        scratch.mkdir(parents=True)
        input_path = scratch / "stage-input.json"
        input_path.write_bytes(b"{}")
        runner = scratch / "runner.exe"
        runner.write_bytes(b"runner")
        completed = subprocess.CompletedProcess([str(runner)], 0, b"{}", b"")
        with patch(
            "ygo_eval.tenki_placement_diagnostics.capture_process_diagnostic",
            return_value=({}, completed),
        ) as capture, patch(
            "ygo_eval.native_tenki_placement_confirmation._diagnostic_hash",
            return_value="a" * 64,
        ):
            with self.assertRaisesRegex(ValueError, "confirmation_runner_window_timeout_required"):
                _run_process(runner, input_path, repo, scratch, "normal", prepared_hash="b" * 64)
            capture.assert_not_called()

            _run_process(
                runner,
                input_path,
                repo,
                scratch,
                "normal",
                prepared_hash="b" * 64,
                timeout=7138.75,
            )
            self.assertEqual(capture.call_args.kwargs["timeout"], 7138.75)


if __name__ == "__main__":
    unittest.main()
