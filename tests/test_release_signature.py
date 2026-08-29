import importlib.util
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_RUN_PATH = ROOT / ".github" / "scripts" / "verify_release_run.py"
VERIFY_RUN_SPEC = importlib.util.spec_from_file_location(
    "verify_release_run", VERIFY_RUN_PATH
)
verify_release_run = importlib.util.module_from_spec(VERIFY_RUN_SPEC)
VERIFY_RUN_SPEC.loader.exec_module(verify_release_run)
SBOM_PATH = ROOT / ".github" / "scripts" / "generate_release_sbom.py"
SBOM_SPEC = importlib.util.spec_from_file_location("generate_release_sbom", SBOM_PATH)
generate_release_sbom = importlib.util.module_from_spec(SBOM_SPEC)
SBOM_SPEC.loader.exec_module(generate_release_sbom)


class ReleaseRunVerifierTests(unittest.TestCase):
    def _run(self, **changes):
        run = {
            "id": 20,
            "head_sha": "abc123",
            "head_branch": "v1.2.3",
            "event": "push",
            "path": ".github/workflows/ci.yml",
            "status": "completed",
            "conclusion": "success",
        }
        run.update(changes)
        return run

    def test_selector_binds_sha_tag_event_path_and_latest_result(self):
        payload = {
            "workflow_runs": [
                self._run(id=10, head_branch="main"),
                self._run(id=11, head_sha="wrong"),
                self._run(id=12, event="pull_request"),
                self._run(id=13, path=".github/workflows/other.yml"),
                self._run(id=20),
            ]
        }

        self.assertEqual(
            20,
            verify_release_run.select_successful_run(
                payload,
                "v1.2.3",
                "abc123",
                "push",
                ".github/workflows/ci.yml",
            ),
        )

        payload["workflow_runs"].append(self._run(id=21, conclusion="failure"))
        with self.assertRaises(verify_release_run.VerificationError):
            verify_release_run.select_successful_run(
                payload,
                "v1.2.3",
                "abc123",
                "push",
                ".github/workflows/ci.yml",
            )

    def test_selector_rejects_missing_or_malformed_evidence(self):
        for payload in ({}, {"workflow_runs": "bad"}, {"workflow_runs": [None]}):
            with self.subTest(payload=payload):
                with self.assertRaises(verify_release_run.VerificationError):
                    verify_release_run.select_successful_run(
                        payload,
                        "v1.2.3",
                        "abc123",
                        "push",
                        ".github/workflows/ci.yml",
                    )

    def test_job_verifier_rejects_missing_failed_and_newer_duplicate_jobs(self):
        required = ("one", "two")
        jobs = {
            "jobs": [
                {
                    "id": 1,
                    "name": "one",
                    "status": "completed",
                    "conclusion": "success",
                },
                {
                    "id": 2,
                    "name": "two",
                    "status": "completed",
                    "conclusion": "success",
                },
            ]
        }
        verify_release_run.verify_required_jobs(jobs, required)

        for invalid in (
            {"jobs": jobs["jobs"][:1]},
            {
                "jobs": jobs["jobs"]
                + [
                    {
                        "id": 3,
                        "name": "two",
                        "status": "completed",
                        "conclusion": "failure",
                    }
                ]
            },
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(verify_release_run.VerificationError):
                    verify_release_run.verify_required_jobs(invalid, required)

    def test_release_like_runs_require_a_tag_sentinel(self):
        for workflow, event in (
            ("ci.yml", "push"),
            ("installer-nightly.yml", "workflow_dispatch"),
        ):
            with self.subTest(workflow=workflow):
                source = (ROOT / ".github" / "workflows" / workflow).read_text()
                self.assertIn("release-ref-is-tag:", source)
                self.assertIn("GITHUB_REF_TYPE: ${{ github.ref_type }}", source)
                self.assertIn(
                    "github.event_name == '{}'".format(event), source
                )
                self.assertIn('test "${GITHUB_REF_TYPE}" = tag', source)
                self.assertIn(
                    'test "${GITHUB_REF}" = "refs/tags/${GITHUB_REF_NAME}"',
                    source,
                )


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

    def test_release_requires_exact_tag_ci_and_platform_runs(self):
        source = self.release
        ci_source = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        self.assertIn("actions: read", source)
        self.assertNotIn("checks: read", source)
        self.assertIn("Verify exact tag CI run", source)
        self.assertIn("/actions/workflows/ci.yml/runs", source)
        self.assertIn(".github/scripts/verify_release_run.py select-run", source)
        self.assertIn('--release-tag "${RELEASE_TAG}"', source)
        self.assertIn('--tag-commit "${TAG_COMMIT}"', source)
        self.assertIn("--event push", source)
        self.assertIn("--workflow-path .github/workflows/ci.yml", source)
        self.assertNotIn("/check-runs", source)
        for check_name in (
            "release-ref-is-tag",
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
        self.assertEqual(source.count("--required release-ref-is-tag"), 2)

        self.assertIn("  full-installer-e2e:\n", ci_source)
        self.assertIn("Verify exact tag installer platform run", source)
        self.assertIn("/actions/workflows/installer-nightly.yml/runs", source)
        self.assertIn("--event workflow_dispatch", source)
        self.assertIn(
            "--workflow-path .github/workflows/installer-nightly.yml", source
        )
        for check_name in (
            "release-ref-is-tag",
            "ubuntu-24.04 / amd64",
            "ubuntu-24.04 / arm64",
            "debian-stable / amd64",
            "debian-stable / arm64",
            "rocky-9 / amd64",
            "rocky-9 / arm64",
        ):
            with self.subTest(check_name=check_name):
                self.assertIn(check_name, source)

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
            'gh release upload "${RELEASE_TAG}" install.sh install.sh.sigstore.json sbom.spdx.json sbom.spdx.json.sigstore.json --clobber',
            source,
        )
        self.assertIn("gh release download", source)
        self.assertIn(
            'expected = {"install.sh", "install.sh.sigstore.json", "sbom.spdx.json", "sbom.spdx.json.sigstore.json"}',
            source,
        )
        self.assertIn("draft release has unexpected asset set", source)
        self.assertIn("cmp --silent install.sh", source)
        self.assertIn("cosign sign-blob --yes --bundle install.sh.sigstore.json install.sh", source)
        self.assertIn("generate_release_sbom.py", source)
        self.assertIn("cosign sign-blob --yes --bundle sbom.spdx.json.sigstore.json sbom.spdx.json", source)
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
        self.assertGreater(source.index(publish), source.index("Verify exact tag CI run"))
        self.assertGreater(
            source.index(publish), source.index("Verify exact tag installer platform run")
        )
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
        self.assertGreaterEqual(source.count("base_image: debian:stable@sha256:"), 2)
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
            'expected = {"install.sh", "install.sh.sigstore.json", "sbom.spdx.json", "sbom.spdx.json.sigstore.json"}',
            source,
        )
        self.assertIn("latest release has unexpected asset set", source)
        self.assertIn("cmp --silent", source)
        self.assertIn("cosign verify-blob", source)
        self.assertIn("sbom.spdx.json", source)
        self.assertIn("@refs/tags/${RELEASE_TAG}", source)
        self.assertIn("if: failure()", source)
        self.assertIn("::error title=Anonymous release distribution unavailable", source)
        self.assertNotIn("Authorization:", source)
        self.assertNotIn("GH_TOKEN", source)
        self.assertNotIn("github.token", source)
        self.assertNotIn("secrets.", source)


class ReleaseSbomTests(unittest.TestCase):
    def test_generator_inventory_is_bound_to_the_source_tree(self):
        document = generate_release_sbom.build_sbom(ROOT)
        self.assertEqual("SPDX-2.3", document["spdxVersion"])
        package = document["packages"][0]
        self.assertEqual("Hysteria2-panel", package["name"])
        installer = next(
            entry for entry in document["files"] if entry["fileName"] == "./install.sh"
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "install.sh").read_bytes()).hexdigest(),
            installer["checksums"][0]["checksumValue"],
        )
        self.assertNotIn(".git/", json.dumps(document))


class ReleaseDocumentationTests(unittest.TestCase):
    def test_support_claims_are_tiered_by_actual_evidence(self):
        readme = (ROOT / "README.md").read_text()

        self.assertIn("定期完整 E2E", readme)
        self.assertIn("Ubuntu 24.04 LTS", readme)
        self.assertIn("Rocky Linux 9", readme)
        self.assertIn("Debian stable", readme)
        self.assertNotIn("待首次绿灯", readme)
        self.assertIn("尽力支持", readme)

    def test_release_runbook_documents_draft_promotion_and_remote_ruleset_gate(self):
        deployment = (ROOT / "docs" / "DEPLOYMENT.md").read_text()

        self.assertIn("gh release create", deployment)
        self.assertIn("--draft", deployment)
        self.assertIn("gh workflow run release-signature.yml", deployment)
        self.assertIn("gh workflow run installer-nightly.yml", deployment)
        self.assertIn("--ref", deployment)
        self.assertIn("full-installer-e2e", deployment)
        self.assertIn("Protect main", deployment)
        self.assertIn("七项 required status checks", deployment)
        self.assertIn("ruleset", deployment.lower())


if __name__ == "__main__":
    unittest.main()
