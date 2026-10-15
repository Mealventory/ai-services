"""Verification of Dockerfile specifications and optional container runtime checks."""
import os
import unittest
from pathlib import Path

DOCKERFILE_PATH = Path(__file__).resolve().parents[1] / "Dockerfile"


class TestDockerConfiguration(unittest.TestCase):
    def test_dockerfile_exists_and_is_multistage(self):
        self.assertTrue(DOCKERFILE_PATH.exists(), "Dockerfile must exist in ai-services root")
        content = DOCKERFILE_PATH.read_text(encoding="utf-8")
        self.assertIn("AS builder", content, "Dockerfile should define a builder stage")
        self.assertIn("AS runner", content, "Dockerfile should define a runner stage")

    def test_dockerfile_installs_cv_and_curl_dependencies(self):
        content = DOCKERFILE_PATH.read_text(encoding="utf-8")
        self.assertIn("libgl1", content, "Dockerfile must install libgl1 for OpenCV")
        self.assertIn("libglib2.0-0", content, "Dockerfile must install libglib2.0-0")
        self.assertIn("curl", content, "Dockerfile must install curl for healthcheck")

    def test_dockerfile_executes_as_nonroot_aiuser(self):
        content = DOCKERFILE_PATH.read_text(encoding="utf-8")
        self.assertIn("aiuser", content, "Dockerfile must create and run as aiuser")
        self.assertIn("USER aiuser", content, "Dockerfile must switch to USER aiuser")

    def test_dockerfile_exposes_and_checks_port_8001(self):
        content = DOCKERFILE_PATH.read_text(encoding="utf-8")
        self.assertIn("EXPOSE 8001", content, "Dockerfile must expose port 8001")
        self.assertIn("8001", content, "Healthcheck must probe port 8001")
        self.assertIn("HEALTHCHECK", content, "Dockerfile must include a HEALTHCHECK instruction")


if __name__ == "__main__":
    unittest.main()
