import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/android-release.yml").read_text(
    encoding="utf-8"
)


class AndroidReleaseWorkflowTests(unittest.TestCase):
    def test_online_build_is_bound_to_tag_main_and_exact_flutter_revision(self):
        self.assertIn('test "${GITHUB_REF}" = "refs/tags/${RELEASE_TAG}"', WORKFLOW)
        self.assertIn('test "${tag_commit}" = "${main_commit}"', WORKFLOW)
        self.assertIn(
            "FLUTTER_VERSION: 3.47.2",
            WORKFLOW,
        )
        self.assertIn(
            "FLUTTER_REVISION: d3b14c876900e553bc736ca19295fc09e3853e8e",
            WORKFLOW,
        )
        self.assertIn(
            '"refs/tags/${FLUTTER_VERSION}:refs/tags/${FLUTTER_VERSION}"',
            WORKFLOW,
        )
        self.assertIn('test "$(git -C "${flutter_dir}" rev-parse HEAD)"', WORKFLOW)
        self.assertIn('metadata.get("frameworkVersion")', WORKFLOW)
        self.assertIn('metadata.get("frameworkRevision")', WORKFLOW)
        bootstrap = '"${flutter_dir}/bin/flutter" --version >/dev/null'
        machine = '"${flutter_dir}/bin/flutter" --version --machine >"${version_json}"'
        self.assertIn(bootstrap, WORKFLOW)
        self.assertIn(machine, WORKFLOW)
        self.assertLess(WORKFLOW.index(bootstrap), WORKFLOW.index(machine))

    def test_online_build_requires_fixed_signing_identity_and_checks_the_apk(self):
        for secret in (
            "ANDROID_SIGNING_KEYSTORE_BASE64",
            "ANDROID_SIGNING_STORE_PASSWORD",
            "ANDROID_SIGNING_KEY_ALIAS",
            "ANDROID_SIGNING_KEY_PASSWORD",
        ):
            self.assertIn("secrets.{}".format(secret), WORKFLOW)
        self.assertIn("EXPECTED_CERT_SHA256:", WORKFLOW)
        self.assertIn('"${apksigner}" verify --verbose', WORKFLOW)
        self.assertIn("versionCode='${build_number}'", WORKFLOW)
        self.assertIn("versionName='${app_version}'", WORKFLOW)
        self.assertIn("APK contains a denied production identifier", WORKFLOW)

    def test_apk_is_uploaded_only_to_an_existing_draft_release(self):
        self.assertIn(
            'test "$(gh release view "${RELEASE_TAG}" --json isDraft --jq .isDraft)" = true',
            WORKFLOW,
        )
        self.assertIn('gh release upload "${RELEASE_TAG}" "${APK}" --clobber', WORKFLOW)
        self.assertIn("retention-days: 30", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
