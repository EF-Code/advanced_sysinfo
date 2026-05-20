import json
import os
import tempfile
import unittest
from argparse import Namespace
from unittest import mock
from io import StringIO

import advanced_sysinfo


class SectionSelectionTests(unittest.TestCase):
    def test_resolve_section_aliases(self) -> None:
        selected, errors = advanced_sysinfo.resolve_section_selection(["CPU", "Memory"], None)
        self.assertEqual(selected, ["cpu", "memory"])
        self.assertEqual(errors, [])

    def test_resolve_unknown_sections_reports_errors(self) -> None:
        selected, errors = advanced_sysinfo.resolve_section_selection(["cpu", "unknown"], ["bogus"])
        self.assertEqual(selected, ["cpu"])
        self.assertEqual(
            errors,
            [
                "Unknown sections requested: unknown",
                "Unknown sections excluded: bogus",
            ],
        )

    def test_build_report_captures_selection_errors(self) -> None:
        args = Namespace(
            sections=["cpu", "missing"],
            exclude_sections=None,
            include_sensitive=False,
            metric_snapshot={},
            baseline=None,
        )
        report = advanced_sysinfo.build_report(args)
        self.assertEqual(report["metadata"]["selected_sections"], ["cpu"])
        self.assertEqual(report["metadata"]["selection_errors"], ["Unknown sections requested: missing"])
        self.assertIn("cpu", report["metadata"]["section_timings_seconds"])
        self.assertIn("runtime_capabilities", report["metadata"])


class HealthTests(unittest.TestCase):
    def test_compute_health_score_is_lenient_for_normal_usage(self) -> None:
        score = advanced_sysinfo.compute_health_score(20.0, 45.0, 60.0)
        self.assertGreaterEqual(score, 90)

    def test_compute_health_score_penalizes_over_thresholds(self) -> None:
        score = advanced_sysinfo.compute_health_score(95.0, 92.0, 96.0)
        self.assertLess(score, 60)


class EnvironmentTests(unittest.TestCase):
    @mock.patch.dict(
        os.environ,
        {
            "HOME": "/tmp/demo",
            "MY_SECRET_TOKEN": "topsecret",
            "NORMAL_VAR": "visible",
        },
        clear=True,
    )
    def test_environment_redacts_values_by_default(self) -> None:
        args = Namespace(include_sensitive=False)
        result = advanced_sysinfo.gather_environment(args)
        self.assertEqual(result["Selected vars"]["HOME"], "/tmp/demo")
        self.assertEqual(result["Sensitive var names"], ["MY_SECRET_TOKEN"])
        self.assertNotIn("All vars", result)

    def test_non_secret_session_style_names_are_not_flagged(self) -> None:
        self.assertFalse(advanced_sysinfo.is_sensitive_env_key("DESKTOP_SESSION"))
        self.assertFalse(advanced_sysinfo.is_sensitive_env_key("PWD"))
        self.assertTrue(advanced_sysinfo.is_sensitive_env_key("OPENAI_API_KEY"))

    @mock.patch.dict(
        os.environ,
        {
            "HOME": "/tmp/demo",
            "MY_SECRET_TOKEN": "topsecret",
        },
        clear=True,
    )
    def test_environment_can_include_sensitive_values(self) -> None:
        args = Namespace(include_sensitive=True)
        result = advanced_sysinfo.gather_environment(args)
        self.assertEqual(result["All vars"]["MY_SECRET_TOKEN"], "topsecret")


class BaselineTests(unittest.TestCase):
    def test_baseline_comparison_reports_drift(self) -> None:
        args = Namespace(
            baseline_report={"generated": "yesterday", "metrics": {"cpu_percent": 10.0}},
            baseline_error=None,
            metric_snapshot={"cpu_percent": 25.5},
            baseline="baseline.json",
            baseline_threshold=10.0,
        )
        result = advanced_sysinfo.gather_baseline_comparison(args)
        self.assertEqual(result["Drift detected"], ["cpu_percent"])

    def test_load_baseline_rejects_non_object_json(self) -> None:
        with tempfile.NamedTemporaryFile("w+", delete=False) as handle:
            handle.write(json.dumps(["bad"]))
            path = handle.name
        try:
            baseline, error = advanced_sysinfo.load_baseline(path)
        finally:
            os.unlink(path)
        self.assertIsNone(baseline)
        self.assertEqual(error, "Baseline file must contain a JSON object.")

    def test_write_text_file_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "nested", "report.json")
            error = advanced_sysinfo.write_text_file(target, '{"ok": true}')
            self.assertIsNone(error)
            with open(target, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), '{"ok": true}')


class CommandTests(unittest.TestCase):
    def test_commands_skip_env_without_sensitive_mode(self) -> None:
        args = Namespace(include_sensitive=False)
        with mock.patch.object(advanced_sysinfo, "safe_subprocess", return_value={"stdout": "", "stderr": "", "returncode": 0}):
            result = advanced_sysinfo.gather_commands(args)
        self.assertIn("env", result)
        self.assertEqual(result["env"]["status"], "Skipped by default to avoid leaking environment values.")


class CliTests(unittest.TestCase):
    def test_list_sections_exits_successfully(self) -> None:
        stdout = StringIO()
        with mock.patch("sys.stdout", stdout):
            exit_code = advanced_sysinfo.main(["--list-sections"])
        self.assertEqual(exit_code, 0)
        self.assertIn("cpu\tCPU", stdout.getvalue())

    def test_main_rejects_negative_package_limit(self) -> None:
        stderr = StringIO()
        with mock.patch("sys.stderr", stderr):
            exit_code = advanced_sysinfo.main(["--max-packages", "-1"])
        self.assertEqual(exit_code, 2)
        self.assertIn("--max-packages must be 0 or greater", stderr.getvalue())

    def test_fail_on_warnings_returns_non_zero(self) -> None:
        stdout = StringIO()
        with mock.patch("sys.stdout", stdout):
            exit_code = advanced_sysinfo.main(["--sections", "missing", "--fail-on-warnings"])
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
