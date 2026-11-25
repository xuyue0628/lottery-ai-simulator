import os
import unittest
from pathlib import Path
from unittest.mock import patch

from lottery_sim import dashboard


class PackagingScriptTests(unittest.TestCase):
    def test_dashboard_command_uses_python_workflow(self):
        with patch.dict(
            os.environ,
            {"LOTTERY_CLI_EXE": "", "LOTTERY_PYTHON": "/opt/venv/bin/python"},
            clear=False,
        ):
            command = dashboard._dashboard_command("daily", "ssq", {})

        self.assertIsNotNone(command)
        self.assertEqual(command[:4], ["/opt/venv/bin/python", "-m", "lottery_sim.cli", "workflow-daily"])
        self.assertNotIn("pwsh", command)

    def test_workflow_can_call_packaged_exe_cli(self):
        workflow = Path("src/lottery_sim/workflow.py").read_text(encoding="utf-8")

        self.assertIn("LOTTERY_CLI_EXE", workflow)
        self.assertIn("--cli", workflow)

    def test_run_script_bootstraps_dependencies_and_starts_launcher(self):
        script = Path("run.sh").read_text(encoding="utf-8")

        self.assertIn("set -euo pipefail", script)
        self.assertIn("requirements.txt", script)
        self.assertIn("launcher.py", script)
        self.assertIn("LOTTERY_HOST", script)
        self.assertIn("LOTTERY_PORT", script)

    def test_build_exe_prefers_venv_python_and_installs_requirements(self):
        build_script = Path("scripts/build_exe.ps1").read_text(encoding="utf-8")

        self.assertIn(".venv", build_script)
        self.assertIn("$PythonExe", build_script)
        self.assertIn("-m pip install -r requirements.txt", build_script)
        self.assertIn("-m PyInstaller", build_script)

    def test_docker_runtime_uses_china_timezone(self):
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
        compose = Path("docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("TZ=Asia/Shanghai", dockerfile)
        self.assertIn("tzdata", dockerfile)
        self.assertIn("/etc/localtime", dockerfile)
        self.assertIn("TZ: ${TZ:-Asia/Shanghai}", compose)
        self.assertNotIn("LOTTERY_POWERSHELL", dockerfile)
        self.assertNotIn("LOTTERY_POWERSHELL", compose)

    def test_readme_documents_chinese_packaging_and_default_password(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("## Docker 服务", readme)
        self.assertIn("## Windows EXE 打包", readme)
        self.assertIn("默认账号密码", readme)
        self.assertIn("账号：admin", readme)
        self.assertIn("密码：admin", readme)
        self.assertIn("GitHub Release", readme)


if __name__ == "__main__":
    unittest.main()
