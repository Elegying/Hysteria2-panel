import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / ".github/workflows"
CODEQL = (WORKFLOW_ROOT / "codeql.yml").read_text(encoding="utf-8")
DEPENDABOT = (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")


class SupplyChainTests(unittest.TestCase):
    def test_every_external_action_is_pinned_to_a_full_commit(self):
        action_pattern = re.compile(r"^\s*- uses: [^@\s]+@([^\s#]+)", re.MULTILINE)
        for workflow in sorted(WORKFLOW_ROOT.glob("*.yml")):
            source = workflow.read_text(encoding="utf-8")
            for reference in action_pattern.findall(source):
                with self.subTest(workflow=workflow.name, reference=reference):
                    self.assertRegex(reference, r"^[0-9a-f]{40}$")

    def test_codeql_scans_python_on_changes_and_a_schedule(self):
        self.assertIn("branches: [main]", CODEQL)
        self.assertIn("schedule:", CODEQL)
        self.assertIn("security-events: write", CODEQL)
        self.assertIn("name: codeql-python", CODEQL)
        self.assertIn("languages: python", CODEQL)
        self.assertIn("queries: security-extended", CODEQL)
        self.assertEqual(CODEQL.count("github/codeql-action/"), 2)
        self.assertEqual(CODEQL.count("# v4.37.9"), 2)

    def test_dependabot_covers_actions_and_the_flutter_client(self):
        self.assertIn("package-ecosystem: github-actions", DEPENDABOT)
        self.assertIn("package-ecosystem: pub", DEPENDABOT)
        self.assertIn("directory: /mobile", DEPENDABOT)
        self.assertEqual(DEPENDABOT.count("interval: monthly"), 2)


if __name__ == "__main__":
    unittest.main()
