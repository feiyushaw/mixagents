import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "hooks" / "omp_bridge.py"


class OmpBridgeV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_bridge(self, args, input_text="", env=None):
        cmd = [sys.executable, str(SCRIPT)] + args + ["--state-directory", str(self.state_dir)]
        merged_env = dict(os.environ)
        if env:
            merged_env.update(env)
        return subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            env=merged_env,
        )

    def stage(self, text="Analyze code graph"):
        result = self.run_bridge(["--mode", "stage"], input_text=text)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["staged"])
        self.assertEqual(payload["schema"], 2)
        self.assertEqual(payload["agent_type"], "omp_worker")
        return payload

    def test_multiple_pending_handoffs(self):
        first = self.stage("Task 1")
        second = self.stage("Task 2")
        self.assertNotEqual(first["handoff_id"], second["handoff_id"])
        self.assertTrue(Path(first["pending_path"]).exists())
        self.assertTrue(Path(second["pending_path"]).exists())

    def test_run_with_mock_omp_jsonl(self):
        staged = self.stage("Analyze code graph")
        mock = self.state_dir / "mock_omp.py"
        mock.write_text(
            "import json, sys\n"
            "print(json.dumps({'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':'OMP_READY'}]},'usage':{'input':10,'output':2}}))\n"
            "print('mock warning', file=sys.stderr)\n",
            encoding="utf-8",
        )
        result = self.run_bridge(
            ["--mode", "run", "--handoff-id", staged["handoff_id"]],
            env={"OMP_BIN": f"{sys.executable} {mock}"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "success")
        self.assertIn("OMP_READY", payload["summary"])
        self.assertEqual(payload["parsed_json_events"], 1)
        self.assertEqual(payload["usage"]["input"], 10)
        self.assertIn("mock warning", payload["stderr_tail"])
        self.assertTrue(Path(payload["artifacts"]["omp_jsonl"]).exists())
        self.assertTrue(
            (self.state_dir / "completed" / f"{staged['handoff_id']}.json").exists()
        )

    def test_completed_run_is_idempotent(self):
        staged = self.stage("Task")
        mock = self.state_dir / "mock.py"
        mock.write_text(
            "import json\nprint(json.dumps({'type':'final','text':'done'}))\n",
            encoding="utf-8",
        )
        env = {"OMP_BIN": f"{sys.executable} {mock}"}
        first = self.run_bridge(
            ["--mode", "run", "--handoff-id", staged["handoff_id"]], env=env
        )
        second = self.run_bridge(
            ["--mode", "run", "--handoff-id", staged["handoff_id"]], env=env
        )
        self.assertEqual(first.returncode, 0)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))

    def test_invalid_handoff_id(self):
        result = self.run_bridge(["--mode", "run", "--handoff-id", "not-a-uuid"])
        self.assertEqual(result.returncode, 7)

    def test_default_cli_uses_json_mode_and_separator(self):
        staged = self.stage("-leading-dash assignment")
        mock = self.state_dir / "argv_mock.py"
        mock.write_text(
            "import json, sys\n"
            "print(json.dumps({'type':'final','text':'ARGS=' + repr(sys.argv[1:])}))\n",
            encoding="utf-8",
        )
        result = self.run_bridge(
            ["--mode", "run", "--handoff-id", staged["handoff_id"]],
            env={"OMP_BIN": f"{sys.executable} {mock}"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)["summary"]
        self.assertIn("'--print'", summary)
        self.assertIn("'--mode'", summary)
        self.assertIn("'json'", summary)
        self.assertIn("'--no-session'", summary)
        self.assertIn("'--'", summary)
        self.assertIn("'-leading-dash assignment'", summary)


if __name__ == "__main__":
    unittest.main()
