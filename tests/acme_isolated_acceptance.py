#!/usr/bin/env python3
"""Run the installer's certificate flow against private Pebble/HTTP-01 services."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import ssl
import subprocess
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pebble", type=Path, required=True)
    parser.add_argument("--challtestsrv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (os.geteuid() != 0 or os.environ.get("container") != "docker"
            or os.environ.get("HY2_STABILITY_ISOLATED") != "1"):
        raise SystemExit("Requires the dedicated disposable Linux test container")
    for port in (80, 31400, 31500, 18053, 18055):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    report = {"result": "running", "checks": [], "binaries": {
        str(path.name): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (args.pebble, args.challtestsrv)}}
    children, handles = [], []
    hosts = Path("/etc/hosts")
    original_hosts = hosts.read_text()
    alias_added = False
    started = time.time()

    def run(argv, name, expected=0, env=None):
        with (args.output / (name + ".log")).open("wb") as log:
            result = subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=90)
        if expected == 0 and result.returncode != 0:
            raise RuntimeError(name + " failed; retain its log")
        if expected != 0 and result.returncode == 0:
            raise RuntimeError(name + " unexpectedly succeeded")

    def start(argv, name, env=None):
        log = (args.output / (name + ".log")).open("wb")
        handles.append(log)
        children.append(subprocess.Popen(argv, env=env, stdout=log, stderr=subprocess.STDOUT))

    try:
        certificate, key = args.output / "api.crt", args.output / "api.key"
        run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
             "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
             "-keyout", str(key), "-out", str(certificate)], "api-certificate")
        key.chmod(0o600)
        context = ssl.create_default_context(cafile=str(certificate))
        config = args.output / "pebble.json"
        config.write_text(json.dumps({"pebble": {
            "listenAddress": "127.0.0.1:31400", "managementListenAddress": "127.0.0.1:31500",
            "certificate": str(certificate), "privateKey": str(key), "httpPort": 80, "tlsPort": 5001,
            "externalAccountBindingRequired": False,
        }}))
        # This special-purpose /32 exists only on the dedicated guest loopback.
        # It exercises the existing global-address DNS gate without public DNS.
        run(["ip", "address", "add", "192.0.0.9/32", "dev", "lo"], "add-test-address")
        alias_added = True
        hosts.write_text(original_hosts + "\n192.0.0.9 panel.acme.test portblocked.acme.test\n127.0.0.1 private.acme.test\n")
        start([str(args.challtestsrv), "-dnsserver", "127.0.0.1:18053", "-management", "127.0.0.1:18055",
               "-http01", "", "-https01", "", "-tlsalpn01", "", "-defaultIPv4", "192.0.0.9",
               "-defaultIPv6", ""], "dns-service")
        start([str(args.pebble), "-config", str(config), "-strict=false", "-dnsserver", "127.0.0.1:18053"],
              "acme-service", dict(os.environ, PEBBLE_VA_NOSLEEP="1", PEBBLE_AUTHZREUSE="0",
                                   PEBBLE_WFE_NONCEREJECT="0"))
        deadline = time.monotonic() + 15
        while True:
            try:
                with urllib.request.urlopen("https://127.0.0.1:31400/dir", context=context, timeout=2) as response:
                    assert response.status == 200
                break
            except OSError:
                if time.monotonic() >= deadline or any(child.poll() is not None for child in children):
                    raise RuntimeError("isolated ACME services did not start")
                time.sleep(.1)
        source = Path("/workspace/install.sh").read_text()
        functions = source[source.index("preflight_panel_acme_dns() {"):
                           source.index("\n\nsecure_acme_runtime_directories() {")]
        # Only the CA endpoint differs in this test; retain all installer flags,
        # public-address preflight, certificate verification and failure behavior.
        functions = functions.replace("/usr/bin/certbot certonly", "/usr/bin/certbot certonly --server https://127.0.0.1:31400/dir")
        directories = {"ACME_CONFIG_DIR": args.output / "config", "ACME_WORK_DIR": args.output / "work",
                       "ACME_LOGS_DIR": args.output / "logs"}
        script = "set -euo pipefail\nfail() { printf '%s\\n' \"$*\" >&2; exit 1; }\nPYTHON_BIN=python3\n"
        script += "\n".join(key + "=" + shlex.quote(str(value)) for key, value in directories.items())
        script += "\n" + functions + "\nissue_panel_acme_certificate\n"
        env = dict(os.environ, REQUESTS_CA_BUNDLE=str(certificate), PANEL_PUBLIC_HOST="private.acme.test")
        run(["bash", "-c", script], "private-address-rejected", expected=1, env=env)
        if directories["ACME_CONFIG_DIR"].exists():
            raise RuntimeError("non-public DNS reached certificate writes")
        report["checks"].append("non-public DNS fails before certificate writes")
        env["PANEL_PUBLIC_HOST"] = "portblocked.acme.test"
        with socket.socket() as ipv4, socket.socket(socket.AF_INET6) as ipv6:
            ipv6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            ipv4.bind(("0.0.0.0", 80))
            ipv6.bind(("::", 80))
            ipv4.listen(1)
            ipv6.listen(1)
            run(["bash", "-c", script], "http01-port-unavailable", expected=1, env=env)
        assert not (directories["ACME_CONFIG_DIR"] / "live/portblocked.acme.test/fullchain.pem").exists()
        report["checks"].append("occupied TCP 80 fails without publishing a certificate")
        env["PANEL_PUBLIC_HOST"] = "panel.acme.test"
        run(["bash", "-c", script], "first-issuance", env=env)
        lineage = directories["ACME_CONFIG_DIR"] / "live/panel.acme.test"
        issued = (lineage / "fullchain.pem").read_bytes()
        run(["openssl", "x509", "-in", str(lineage / "fullchain.pem"), "-noout", "-checkhost", "panel.acme.test"],
            "certificate-hostname")
        assert "does match certificate" in (args.output / "certificate-hostname.log").read_text()
        report["checks"].append("real HTTP-01 issuance")
        run(["bash", "-c", script], "repeat-issuance", env=env)
        assert (lineage / "fullchain.pem").read_bytes() == issued
        report["checks"].append("repeat install preserves unexpired certificate")
        # Certbot's normal unattended renewal sleeps randomly for up to 8 min.
        # Disable that scheduling jitter only for this protocol/failure test.
        renew = ["/usr/bin/certbot", "renew", "--non-interactive", "--no-random-sleep-on-renew",
                 "--force-renewal", "--cert-name", "panel.acme.test"]
        for flag, key_name in (("--config-dir", "ACME_CONFIG_DIR"), ("--work-dir", "ACME_WORK_DIR"),
                               ("--logs-dir", "ACME_LOGS_DIR")):
            renew += [flag, str(directories[key_name])]
        for operation in ("set-servfail", "clear-servfail"):
            request = urllib.request.Request("http://127.0.0.1:18055/" + operation,
                                             data=b'{"host":"panel.acme.test"}',
                                             headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=2) as response:
                assert response.status == 200
            failing = operation == "set-servfail"
            run(renew, "renewal-dns-failure" if failing else "renewal-recovery", expected=int(failing), env=env)
            if failing:
                assert (lineage / "fullchain.pem").read_bytes() == issued
                report["checks"].append("DNS failure retains previous certificate")
            else:
                assert (lineage / "fullchain.pem").read_bytes() != issued
                report["checks"].append("renewal recovers after DNS restoration")
        report["result"] = "passed"
    except Exception as error:
        report.update(result="failed", error=str(error))
        raise
    finally:
        for child in children:
            child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        for handle in handles:
            handle.close()
        hosts.write_text(original_hosts)
        if alias_added:
            subprocess.run(["ip", "address", "del", "192.0.0.9/32", "dev", "lo"], check=True, timeout=10)
        report["elapsedSeconds"] = time.time() - started
        (args.output / "status.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
