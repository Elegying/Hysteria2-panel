import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/android-release.yml").read_text(
    encoding="utf-8"
)
GRADLE = (ROOT / "mobile/android/app/build.gradle.kts").read_text(encoding="utf-8")


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
        self.assertIn("keytool -exportcert", WORKFLOW)
        self.assertIn('test "${keystore_cert}" = "${EXPECTED_CERT_SHA256}"', WORKFLOW)
        self.assertIn('"${apksigner}" verify --verbose', WORKFLOW)
        self.assertIn('/certificate SHA-256 digest:/', WORKFLOW)
        self.assertIn('^[0-9a-f]{64}$', WORKFLOW)
        self.assertIn('test "${actual_cert}" = "${EXPECTED_CERT_SHA256}"', WORKFLOW)
        self.assertIn("versionCode='${build_number}'", WORKFLOW)
        self.assertIn("versionName='${app_version}'", WORKFLOW)
        self.assertIn("APK contains a denied production identifier", WORKFLOW)

    def test_release_apk_targets_modern_arm64_android_only(self):
        self.assertIn(
            "flutter build apk --release --target-platform android-arm64",
            WORKFLOW,
        )
        self.assertIn('native_abis != {"arm64-v8a"}', WORKFLOW)
        self.assertIn("APK native ABI set is not arm64-only", WORKFLOW)
        self.assertIn('abiFilters += listOf("arm64-v8a")', GRADLE)
        for unsupported in ("armeabi-v7a", "x86", "x86_64"):
            self.assertIn('"lib/{}/**"'.format(unsupported), GRADLE)

    def test_apk_is_uploaded_only_to_an_existing_draft_release(self):
        self.assertIn(
            'test "$(gh release view "${RELEASE_TAG}" --json isDraft --jq .isDraft)" = true',
            WORKFLOW,
        )
        self.assertIn('gh release upload "${RELEASE_TAG}" "${APK}" --clobber', WORKFLOW)
        self.assertIn("retention-days: 30", WORKFLOW)

    def test_release_actions_use_current_node_24_compatible_majors(self):
        self.assertIn(
            "actions/setup-java@dd06d9cba3e5552c54d9f8ea23572deb30010f7c # v6.0.0",
            WORKFLOW,
        )
        self.assertIn(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1",
            WORKFLOW,
        )


if __name__ == "__main__":
    unittest.main()
