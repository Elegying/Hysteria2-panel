import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseSignatureWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = (
            ROOT / ".github" / "workflows" / "release-signature.yml"
        ).read_text()

    def test_release_is_explicitly_dispatched_from_the_version_tag(self):
        source = self.release

        self.assertIn("workflow_dispatch:", source)
        self.assertIn("tag:", source)
        self.assertIn("required: true", source)
        self.assertNotIn("\n  release:", source)
        self.assertIn('RELEASE_TAG: ${{ inputs.tag }}', source)
        self.assertIn('test "${GITHUB_REF}" = "refs/tags/${RELEASE_TAG}"', source)
        self.assertIn("fetch-depth: 0", source)
        self.assertIn("persist-credentials: false", source)

    def test_release_tag_commit_must_equal_protected_main(self):
        source = self.release

        self.assertIn("fetch-depth: 0", source)
        self.assertIn("Verify release tag is current protected main", source)
        self.assertIn(
            "git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main",
            source,
        )
        self.assertIn('tag_commit="$(git rev-parse "${RELEASE_TAG}^{commit}")"', source)
        self.assertIn('main_commit="$(git rev-parse "origin/main^{commit}")"', source)
        self.assertIn('test "${tag_commit}" = "${main_commit}"', source)

    def test_release_requires_every_ci_job_including_full_installer_e2e(self):
        source = self.release
        ci_source = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        self.assertIn("checks: read", source)
        self.assertIn("Verify required CI checks", source)
        self.assertIn("/check-runs", source)
        for check_name in (
            "test (3.8)",
            "test (3.12)",
            "static-analysis",
            "managed-firewall-integration",
            "systemd-service-semantics",
            "full-installer-e2e",
            "rhel-firewall-package-contract",
        ):
            with self.subTest(check_name=check_name):
                self.assertIn(check_name, source)

        self.assertIn("  full-installer-e2e:\n", ci_source)

    def test_main_push_does_not_require_the_future_release_tag(self):
        ci_source = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        self.assertNotIn("Require the version tag to point at a main push", ci_source)
        self.assertNotIn(
            'git fetch --force origin "refs/tags/v${version}:refs/tags/v${version}"',
            ci_source,
        )

    def test_release_stays_draft_until_signed_assets_are_reverified(self):
        source = self.release

        self.assertIn("contents: write", source)
        self.assertIn("id-token: write", source)
        self.assertIn("Verify tag and source version", source)
        self.assertIn('expected = "v{}".format(version_match.group(1))', source)
        self.assertIn("--draft", source)
        self.assertIn("release is not a draft", source)
        self.assertIn(
            'gh release upload "${RELEASE_TAG}" install.sh install.sh.sigstore.json --clobber',
            source,
        )
        self.assertIn("gh release download", source)
        self.assertIn(
            'expected = {"install.sh", "install.sh.sigstore.json"}',
            source,
        )
        self.assertIn("draft release has unexpected asset set", source)
        self.assertIn("cmp --silent install.sh", source)
        self.assertIn("cosign sign-blob --yes --bundle install.sh.sigstore.json install.sh", source)
        self.assertIn("cosign verify-blob install.sh", source)
        self.assertIn("--certificate-identity", source)
        self.assertIn(
            "--certificate-oidc-issuer https://token.actions.githubusercontent.com",
            source,
        )
        self.assertIn("tampered-install.sh", source)
        publish = 'gh release edit "${RELEASE_TAG}" --draft=false'
        self.assertIn(publish, source)
        self.assertGreater(source.index(publish), source.index("gh release download"))
        self.assertGreater(source.index(publish), source.index("Verify required CI checks"))
        self.assertTrue(
            source.rstrip().endswith(
                'gh release edit "${RELEASE_TAG}" '
                "--draft=false --prerelease=false --latest"
            )
        )
        self.assertNotIn("COSIGN_PRIVATE_KEY", source)
        self.assertNotIn("secrets.", source)


class InstallerPlatformWorkflowTests(unittest.TestCase):
    def test_nightly_matrix_covers_debian_stable_on_both_architectures(self):
        source = (
            ROOT / ".github" / "workflows" / "installer-nightly.yml"
        ).read_text()

        self.assertEqual(source.count("platform: debian-stable"), 2)
        self.assertGreaterEqual(source.count("base_image: debian:stable"), 2)
        debian_entries = source.split("platform: debian-stable")[1:]
        self.assertTrue(any("architecture: amd64" in entry[:180] for entry in debian_entries))
        self.assertTrue(any("architecture: arm64" in entry[:180] for entry in debian_entries))


class DistributionSyntheticWorkflowTests(unittest.TestCase):
    def test_synthetic_checks_public_release_assets_without_credentials(self):
        workflow = ROOT / ".github" / "workflows" / "distribution-synthetic.yml"
        self.assertTrue(workflow.exists())
        source = workflow.read_text()

        self.assertIn("schedule:", source)
        self.assertIn("workflow_dispatch:", source)
        self.assertIn("permissions:\n  contents: read", source)
        self.assertIn("api.github.com/repos/${GITHUB_REPOSITORY}/releases/latest", source)
        self.assertIn(
            "releases/download/${RELEASE_TAG}",
            source,
        )
        self.assertIn('"${base}/install.sh"', source)
        self.assertIn(
            "raw.githubusercontent.com/${GITHUB_REPOSITORY}/${RELEASE_TAG}/install.sh",
            source,
        )
        self.assertIn("install.sh.sigstore.json", source)
        self.assertIn(
            'expected = {"install.sh", "install.sh.sigstore.json"}',
            source,
        )
        self.assertIn("latest release has unexpected asset set", source)
        self.assertIn("cmp --silent", source)
        self.assertIn("cosign verify-blob", source)
        self.assertIn("@refs/tags/${RELEASE_TAG}", source)
        self.assertIn("if: failure()", source)
        self.assertIn("::error title=Anonymous release distribution unavailable", source)
        self.assertNotIn("Authorization:", source)
        self.assertNotIn("GH_TOKEN", source)
        self.assertNotIn("github.token", source)
        self.assertNotIn("secrets.", source)


class ReleaseDocumentationTests(unittest.TestCase):
    def test_support_claims_are_tiered_by_actual_evidence(self):
        readme = (ROOT / "README.md").read_text()

        self.assertIn("定期完整 E2E", readme)
        self.assertIn("Ubuntu 24.04 LTS", readme)
        self.assertIn("Rocky Linux 9", readme)
        self.assertIn("Debian stable", readme)
        self.assertIn("待首次绿灯", readme)
        self.assertIn("尽力支持", readme)

    def test_release_runbook_documents_draft_promotion_and_remote_ruleset_gate(self):
        deployment = (ROOT / "docs" / "DEPLOYMENT.md").read_text()

        self.assertIn("gh release create", deployment)
        self.assertIn("--draft", deployment)
        self.assertIn("gh workflow run release-signature.yml", deployment)
        self.assertIn("--ref", deployment)
        self.assertIn("full-installer-e2e", deployment)
        self.assertIn("Protect main", deployment)
        self.assertIn("七项 required status checks", deployment)
        self.assertIn("ruleset", deployment.lower())


if __name__ == "__main__":
    unittest.main()
