"""Formal release discovery and keyless Sigstore update verification."""

import json
import re
import subprocess  # nosec B404 - fixed executables and argv only
import tempfile
import urllib.request
from pathlib import Path

from .version import PANEL_VERSION


class UpdateChecker:
    URL = "https://api.github.com/repos/Elegying/Hysteria2-panel/releases/latest"

    def __init__(self, current_version=PANEL_VERSION, opener=urllib.request.urlopen):
        self.current_version = current_version
        self.opener = opener

    @staticmethod
    def _version_tuple(value):
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
        if not match:
            raise ValueError("release version is invalid")
        return tuple(int(part) for part in match.groups())

    def check(self):
        request = urllib.request.Request(
            self.URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Hysteria2-panel"},
        )
        with self.opener(request, timeout=3) as response:
            raw_body = response.read(16385)
        if len(raw_body) > 16384:
            raise ValueError("release response is too large")
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("release response is invalid")
        if (
            payload.get("draft", False) is not False
            or payload.get("prerelease", False) is not False
        ):
            raise ValueError("release is not a formal release")
        latest = payload.get("tag_name")
        if not isinstance(latest, str):
            raise ValueError("release response is invalid")
        latest_tuple = self._version_tuple(latest)
        return {
            "current": "v{}".format(self.current_version.lstrip("v")),
            "latest": "v{}.{}.{}".format(*latest_tuple),
            "update_available": latest_tuple > self._version_tuple(self.current_version),
            "url": "https://github.com/Elegying/Hysteria2-panel/releases/latest",
        }


class UpdateInstaller:
    INSTALLER_URL = (
        "https://raw.githubusercontent.com/Elegying/Hysteria2-panel/{tag}/install.sh"
    )
    BUNDLE_URL = (
        "https://github.com/Elegying/Hysteria2-panel/releases/download/"
        "{tag}/install.sh.sigstore.json"
    )
    MAX_INSTALLER_BYTES = 512 * 1024
    MAX_BUNDLE_BYTES = 512 * 1024
    SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    COSIGN_PATH = Path("/opt/hysteria2-panel/bin/cosign")
    CERTIFICATE_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
    CERTIFICATE_IDENTITY = (
        "https://github.com/Elegying/Hysteria2-panel/"
        ".github/workflows/release-signature.yml@refs/tags/{tag}"
    )

    def __init__(
        self,
        current_version=PANEL_VERSION,
        opener=urllib.request.urlopen,
        runner=subprocess.run,
        cosign_path=COSIGN_PATH,
    ):
        self.current_version = current_version
        self.opener = opener
        self.runner = runner
        self.cosign_path = Path(cosign_path)

    def _download(self, url, maximum, label):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Hysteria2-panel"},
        )
        with self.opener(request, timeout=10) as response:
            body = response.read(maximum + 1)
        if not body:
            raise ValueError("release {} is empty".format(label))
        if len(body) > maximum:
            raise ValueError("release {} is too large".format(label))
        return body

    def _download_installer(self, tag):
        body = self._download(
            self.INSTALLER_URL.format(tag=tag),
            self.MAX_INSTALLER_BYTES,
            "installer",
        )
        try:
            source = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("release installer is not UTF-8") from exc
        if not source.startswith(("#!/usr/bin/env bash\n", "#!/bin/bash\n")):
            raise ValueError("release installer header is invalid")
        latest = re.search(r'^PANEL_VERSION="(\d+\.\d+\.\d+)"$', source, re.MULTILINE)
        if not latest:
            raise ValueError("release installer version is invalid")
        return body, latest.group(1)

    def _download_bundle(self, tag):
        return self._download(
            self.BUNDLE_URL.format(tag=tag),
            self.MAX_BUNDLE_BYTES,
            "signature bundle",
        )

    def _verify_signature(self, tag, installer_path, bundle_path):
        result = self.runner(
            [
                str(self.cosign_path),
                "verify-blob",
                str(installer_path),
                "--bundle",
                str(bundle_path),
                "--certificate-identity",
                self.CERTIFICATE_IDENTITY.format(tag=tag),
                "--certificate-oidc-issuer",
                self.CERTIFICATE_OIDC_ISSUER,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError("release installer signature is invalid")

    def apply(self):
        release = UpdateChecker(self.current_version, opener=self.opener).check()
        if not release["update_available"]:
            return {
                "current": release["current"],
                "latest": release["latest"],
                "updated": False,
            }
        tag = release["latest"]
        installer, embedded_version = self._download_installer(tag)
        if "v{}".format(embedded_version) != tag:
            raise ValueError("release installer version does not match release tag")
        bundle = self._download_bundle(tag)
        with tempfile.TemporaryDirectory(prefix="hysteria2-panel-update.") as directory:
            installer_path = Path(directory) / "install.sh"
            bundle_path = Path(directory) / "install.sh.sigstore.json"
            installer_path.write_bytes(installer)
            bundle_path.write_bytes(bundle)
            installer_path.chmod(0o700)
            bundle_path.chmod(0o600)
            self._verify_signature(tag, installer_path, bundle_path)
            syntax = self.runner(
                ["/bin/bash", "-n", str(installer_path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if syntax.returncode != 0:
                raise ValueError("release installer syntax is invalid")
            environment = {
                "PATH": self.SAFE_PATH,
                "LANG": "C.UTF-8",
                "HY2PANEL_AUTO_UPDATE": "1",
                "PANEL_REF": tag,
            }
            result = self.runner(
                ["/bin/bash", str(installer_path)],
                env=environment,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError("online update installer failed")
        return {
            "current": release["current"],
            "latest": release["latest"],
            "updated": True,
        }
