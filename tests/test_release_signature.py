import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseSignatureWorkflowTests(unittest.TestCase):
    def test_release_workflow_uses_keyless_oidc_and_checks_tampering(self):
        workflow = ROOT / ".github" / "workflows" / "release-signature.yml"
        source = workflow.read_text()

        self.assertIn("release:\n    types: [published]", source)
        self.assertIn("id-token: write", source)
        self.assertIn("contents: write", source)
        self.assertIn("Verify tag and source version", source)
        self.assertIn('expected = "v{}".format(version_match.group(1))', source)
        self.assertIn("cosign sign-blob --yes --bundle install.sh.sigstore.json install.sh", source)
        self.assertIn("cosign verify-blob install.sh", source)
        self.assertIn("--certificate-identity", source)
        self.assertIn("--certificate-oidc-issuer https://token.actions.githubusercontent.com", source)
        self.assertIn("tampered-install.sh", source)
        self.assertIn('gh release upload "${GITHUB_REF_NAME}" install.sh.sigstore.json --clobber', source)
        self.assertNotIn("COSIGN_PRIVATE_KEY", source)
        self.assertNotIn("secrets.", source)


if __name__ == "__main__":
    unittest.main()
