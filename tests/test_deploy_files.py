"""Guards for the hosting files, so a careless edit cannot break the first deploy or leak a secret."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(name):
    return (ROOT / name).read_text()


class DeployFileTests(unittest.TestCase):
    def test_render_blueprint_keeps_secrets_out_and_deploys_only_from_ci(self):
        render = text("render.yaml")
        self.assertIn("autoDeploy: false", render)
        self.assertIn("healthCheckPath: /api/health", render)
        self.assertIn("runtime: docker", render)
        # Every secret is declared without a value, so it is pasted in the dashboard, never committed.
        for key in ["ADMIN_PASSWORD", "GITHUB_PERSONAL_ACCESS_TOKEN", "MODEL_API_KEY", "GEMINI_API_KEY", "GITHUB_DEMO_REPO"]:
            self.assertRegex(render, rf"key: {key}\n\s+sync: false", key)
        self.assertNotRegex(render, r"(ghp_|github_pat_|AIza)")

    def test_dockerfile_listens_on_the_hosts_port_and_trusts_its_proxy(self):
        docker = text("Dockerfile")
        self.assertIn("${PORT}", docker)
        self.assertIn("--proxy-headers", docker)
        self.assertIn("USER agent", docker)
        self.assertIn("/api/health", docker)

    def test_dockerignore_keeps_secrets_and_data_out_of_the_image(self):
        ignored = set(text(".dockerignore").split())
        for item in [".env", ".env.*", "data"]:
            self.assertIn(item, ignored)

    def test_deploy_workflow_only_deploys_after_tests_and_checks_the_new_commit(self):
        deploy = (ROOT / "ci-pending" / "deploy.yml")
        if not deploy.exists():
            deploy = ROOT / ".github" / "workflows" / "deploy.yml"
        body = deploy.read_text()
        self.assertIn("needs: test", body)
        self.assertIn("RENDER_DEPLOY_HOOK_URL", body)
        self.assertIn("--expect-version", body)
        self.assertNotRegex(body, r"https://api\.render\.com/deploy/srv-")

    def test_every_documented_secret_is_in_the_env_example(self):
        example = text(".env.example")
        for key in ["ADMIN_USERNAME", "ADMIN_PASSWORD", "GITHUB_DEMO_REPO", "ALLOW_SIGNUP", "SIGNUP_CODE"]:
            self.assertRegex(example, rf"(?m)^#?\s*{key}=", key)


if __name__ == "__main__":
    unittest.main()
