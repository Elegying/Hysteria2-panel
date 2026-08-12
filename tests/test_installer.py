import hashlib
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
TCP_PROBE = ROOT / "tcp_probe.py"


class InstallerContractTests(unittest.TestCase):
    def test_installer_has_valid_shell_syntax_and_help_is_safe(self):
        syntax = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
        self.assertEqual(0, syntax.returncode, syntax.stderr)

        help_result = subprocess.run(
            ["bash", str(INSTALLER), "--help"], capture_output=True, text=True
        )
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        self.assertIn("19999", help_result.stdout)

    def test_installer_pins_upstream_release_and_checksums(self):
        source = INSTALLER.read_text()

        self.assertIn('PANEL_VERSION="0.15.2"', source)
        self.assertIn('HYSTERIA_VERSION="2.12.1"', source)
        self.assertIn(
            'HYSTERIA_SHA_AMD64="ffc032c7ca6b78676d337097ca7f61bebc3a90a4f3a656693adf368f304cdbc7"',
            source,
        )
        self.assertIn(
            'HYSTERIA_SHA_ARM64="c9cd1af6395eee13a937f429ea71b290e3cc571eea2b4d7f8bc7c49c1d23a792"',
            source,
        )
        self.assertIn(
            'PANEL_SHA256="f41b1740cb585775fd3d15fe6ae4d751b09df64c196927bf1228911691757295"',
            source,
        )
        self.assertIn(
            'TCP_PROBE_SHA256="b63da9cc1e58ae3459e188a507d9e71bd205b5f3320448bc319d1f80a21885a2"',
            source,
        )
        self.assertIn('面板源码 SHA-256 校验失败', source)
        self.assertIn('TCP 探测源码 SHA-256 校验失败', source)
        self.assertIn("sha256sum", source)
        panel_sha = source.split('PANEL_SHA256="', 1)[1].split('"', 1)[0]
        probe_sha = source.split('TCP_PROBE_SHA256="', 1)[1].split('"', 1)[0]
        self.assertEqual(
            hashlib.sha256((ROOT / "hysteria2_panel.py").read_bytes()).hexdigest(),
            panel_sha,
        )
        self.assertEqual(hashlib.sha256(TCP_PROBE.read_bytes()).hexdigest(), probe_sha)

    def test_installer_prompts_without_embedding_an_admin_password(self):
        source = INSTALLER.read_text()

        self.assertIn("read -r -s", source)
        self.assertNotRegex(source, r'ADMIN_PASSWORD="[^"$]{8,}"')
        self.assertIn("NODE_NAME", source)
        self.assertIn("PUBLIC_HOST", source)
        self.assertIn("HYSTERIA_PORT", source)
        self.assertIn("PANEL_SCHEME", source)
        self.assertNotIn("--if-missing", source)

    def test_upgrade_preserves_existing_administrator_unless_reset_is_requested(self):
        source = INSTALLER.read_text()

        self.assertIn('RESET_ADMIN="${RESET_ADMIN:-0}"', source)
        self.assertIn('UPDATE_ADMIN=0', source)
        self.assertIn('保留当前管理员账号和密码', source)
        self.assertIn('if (( UPDATE_ADMIN == 1 )); then', source)

    def test_online_update_mode_requires_an_existing_managed_install_and_keeps_settings(self):
        source = INSTALLER.read_text()

        self.assertIn('AUTO_UPDATE="${HY2PANEL_AUTO_UPDATE:-0}"', source)
        self.assertIn('在线更新只允许用于现有的受管安装', source)
        self.assertIn(
            """detected_host="$(ip -4 -o addr show scope global 2>/dev/null | awk '{split($4,a,"/"); print a[1]; exit}')" || true""",
            source,
        )
        self.assertIn('NODE_NAME="${EXISTING_NODE_NAME}"', source)
        self.assertIn('PUBLIC_HOST="${EXISTING_PUBLIC_HOST}"', source)
        self.assertIn('HYSTERIA_PORT="${EXISTING_HYSTERIA_PORT}"', source)
        self.assertIn('PANEL_PORT="${EXISTING_PANEL_PORT}"', source)
        self.assertIn('PANEL_SCHEME="${EXISTING_PANEL_SCHEME}"', source)
        self.assertIn('EGRESS_POLICY="${EXISTING_EGRESS_POLICY}"', source)
        self.assertIn('RESET_ADMIN="0"', source)

    def test_upgrade_uses_existing_node_settings_as_prompt_defaults(self):
        source = INSTALLER.read_text()

        self.assertIn('EXISTING_INSTALL=1', source)
        self.assertIn('EXISTING_NODE_NAME="${HY2PANEL_NODE_NAME:-Hysteria 2}"', source)
        self.assertIn('EXISTING_PUBLIC_HOST="${HY2PANEL_PUBLIC_HOST:-${detected_host}}"', source)
        self.assertIn('EXISTING_HYSTERIA_PORT="${HY2PANEL_HYSTERIA_PORT:-${DEFAULT_HYSTERIA_PORT}}"', source)
        self.assertIn('EXISTING_PANEL_PORT="${HY2PANEL_PANEL_PORT:-${DEFAULT_PANEL_PORT}}"', source)
        self.assertIn('EXISTING_PANEL_SCHEME="${HY2PANEL_PANEL_SCHEME:-http}"', source)
        self.assertIn('EXISTING_AUTH_PORT="${HY2PANEL_AUTH_PORT:-${DEFAULT_AUTH_PORT}}"', source)
        self.assertIn('EXISTING_STATS_PORT="${HY2PANEL_STATS_PORT:-${DEFAULT_STATS_PORT}}"', source)

    def test_installer_defaults_panel_to_http(self):
        source = INSTALLER.read_text()

        self.assertIn('EXISTING_PANEL_SCHEME="http"', source)
        self.assertIn('PANEL_SCHEME="${PANEL_SCHEME:-${EXISTING_PANEL_SCHEME}}"', source)
        self.assertIn('管理面板:   HTTP TCP 19998（可选 HTTPS）', source)
        self.assertIn('域名的明文 HTTP 被网络重置', source)
        self.assertIn('${PANEL_SCHEME}://${detected_host}:${PANEL_PORT}/', source)

    def test_installer_supports_debian_and_rhel_package_managers(self):
        source = INSTALLER.read_text()

        self.assertIn("install_system_dependencies", source)
        self.assertIn("apt-get install", source)
        self.assertIn("dnf install", source)
        self.assertIn("yum install", source)
        self.assertIn("/etc/os-release", source)
        self.assertIn("Python 3.8", source)
        self.assertIn("systemd", source)
        self.assertIn("PYTHON_BIN", source)
        required_commands = source.split("required_commands=(", 1)[1].split(")", 1)[0]
        for command in (
            "awk",
            "cat",
            "chmod",
            "chown",
            "cp",
            "date",
            "find",
            "grep",
            "id",
            "ip",
            "rm",
            "uname",
        ):
            self.assertIn(command, required_commands.split())

    def test_installer_is_namespaced_and_separates_service_identities(self):
        source = INSTALLER.read_text()

        self.assertIn("/opt/hysteria2-panel/bin/hysteria", source)
        self.assertIn("hysteria2-panel-server.service", source)
        self.assertNotIn("/etc/systemd/system/hysteria2.service", source)
        self.assertIn("User=hy2panel", source)
        self.assertIn("User=hy2server", source)
        self.assertIn("Group=hy2tls", source)

    def test_installer_adds_a_per_user_udp_443_entrypoint(self):
        source = INSTALLER.read_text()

        self.assertIn('DEFAULT_STATS_443_PORT=19995', source)
        self.assertIn('HY2PANEL_STATS_443_PORT=${STATS_443_PORT}', source)
        self.assertIn('/etc/hysteria2-panel/hysteria-443.yaml', source)
        self.assertIn('url: http://127.0.0.1:${AUTH_PORT}/auth/udp-443', source)
        self.assertIn('hysteria2-panel-server-443.service', source)
        self.assertIn('PartOf=hysteria2-panel-server.service', source)
        self.assertIn('Wants=hysteria2-panel-server-443.service', source)
        secondary_unit = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-server-443.service <<'EOF'",
            1,
        )[1].split("\nEOF", 1)[0]
        self.assertIn('AmbientCapabilities=CAP_NET_BIND_SERVICE', secondary_unit)
        self.assertIn('CapabilityBoundingSet=CAP_NET_BIND_SERVICE', secondary_unit)
        self.assertEqual(2, source.count('AmbientCapabilities=CAP_NET_BIND_SERVICE'))
        self.assertEqual(2, source.count('CapabilityBoundingSet=CAP_NET_BIND_SERVICE'))
        self.assertIn('ss -H -lun "sport = :443"', source)
        self.assertIn('请同时放行 TCP/UDP 443', source)

    def test_installer_restarts_upgrades_and_does_not_mutate_firewall(self):
        source = INSTALLER.read_text()

        self.assertIn("systemctl restart hysteria2-panel.service", source)
        self.assertIn("systemctl restart hysteria2-panel-server.service", source)
        self.assertNotIn("ufw allow", source)
        self.assertIn(".managed-by-installer", source)

    def test_failed_upgrade_automatically_rolls_back_node_identity_and_runtime(self):
        source = INSTALLER.read_text()

        self.assertIn("rollback_existing_install()", source)
        self.assertIn('ROLLBACK_REQUIRED=1', source)
        self.assertIn('rollback_existing_install "${status}"', source)
        self.assertIn('cp -a "${BACKUP_DIR}/opt" /opt/hysteria2-panel', source)
        self.assertIn('cp -a "${BACKUP_DIR}/etc" /etc/hysteria2-panel', source)
        self.assertIn('cp -a "${BACKUP_DIR}/panel.db" /var/lib/hysteria2-panel/panel.db', source)
        self.assertIn('ROLLBACK_REQUIRED=0\n\necho', source)
        self.assertLess(source.index('ROLLBACK_REQUIRED=1'), source.rindex('\noptimize_network_stack\n'))
        self.assertLess(source.index('面板端口未监听'), source.rindex('ROLLBACK_REQUIRED=0'))

    def test_installer_adds_tcp_probe_on_the_hysteria_port(self):
        source = INSTALLER.read_text()

        self.assertIn("TCP_PROBE_SOURCE_URL", source)
        self.assertIn("tcp_probe.py", source)
        self.assertIn("hysteria2-panel-tcp-probe.service", source)
        self.assertIn("BindsTo=hysteria2-panel-server.service", source)
        self.assertIn("PartOf=hysteria2-panel-server.service", source)
        self.assertIn("Wants=hysteria2-panel-tcp-probe.service", source)
        self.assertIn("DynamicUser=true", source)
        self.assertIn(
            "ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/tcp_probe.py ${HYSTERIA_PORT}",
            source,
        )
        self.assertIn('ss -H -ltn "sport = :${HYSTERIA_PORT}"', source)
        self.assertIn('TCP/UDP ${HYSTERIA_PORT}', source)

    def test_installer_mirrors_the_tcp_probe_on_the_udp_443_entrypoint(self):
        source = INSTALLER.read_text()

        self.assertIn("hysteria2-panel-tcp-probe-443.service", source)
        self.assertIn("Wants=hysteria2-panel-tcp-probe-443.service", source)
        secondary_probe_unit = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-tcp-probe-443.service <<EOF",
            1,
        )[1].split("\nEOF", 1)[0]
        self.assertIn("BindsTo=hysteria2-panel-server-443.service", secondary_probe_unit)
        self.assertIn("PartOf=hysteria2-panel-server-443.service", secondary_probe_unit)
        self.assertIn("DynamicUser=true", secondary_probe_unit)
        self.assertIn(
            "ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/tcp_probe.py 443",
            secondary_probe_unit,
        )
        self.assertIn(
            "CapabilityBoundingSet=CAP_NET_BIND_SERVICE", secondary_probe_unit
        )
        self.assertIn("AmbientCapabilities=CAP_NET_BIND_SERVICE", secondary_probe_unit)
        self.assertIn(
            'if (( UDP_443_ENABLED == 1 )) && ss -H -ltn "sport = :443" | grep -q . && ! systemctl is-active --quiet hysteria2-panel-tcp-probe-443.service; then',
            source,
        )
        self.assertIn(
            "systemctl stop hysteria2-panel-tcp-probe-443.service",
            source,
        )
        self.assertIn(
            "hysteria2-panel-tcp-probe.service hysteria2-panel-tcp-probe-443.service hysteria2-panel-restore.service",
            source,
        )
        self.assertIn(
            "hysteria2-panel-tcp-probe.service hysteria2-panel-tcp-probe-443.service\nBefore=",
            source,
        )
        self.assertIn(
            'systemctl is-active --quiet hysteria2-panel-tcp-probe-443.service || fail "TCP 443 连通性探测服务启动失败"',
            source,
        )
        self.assertIn(
            'ss -H -ltn "sport = :443" | grep -q . || fail "Hysteria TCP 443 探测端口未监听"',
            source,
        )
        self.assertIn("请同时放行 TCP/UDP 443", source)

    def test_installer_waits_for_service_readiness(self):
        source = INSTALLER.read_text()

        self.assertIn("wait_for_health", source)
        self.assertIn("for _attempt in {1..30}", source)
        self.assertIn('wait_for_health "${PANEL_SCHEME}://127.0.0.1:${PANEL_PORT}/healthz"', source)

    def test_installer_persists_quic_udp_buffer_optimization(self):
        source = INSTALLER.read_text()

        self.assertIn("/etc/sysctl.d/99-hysteria2-panel.conf", source)
        self.assertIn("net.core.rmem_max", source)
        self.assertIn("net.core.wmem_max", source)
        self.assertIn("16777216", source)
        self.assertIn("net.core.default_qdisc", source)
        self.assertIn("net.ipv4.tcp_congestion_control", source)
        self.assertIn("LimitNOFILE=1048576", source)

    def test_installer_explicitly_enables_hysteria_quic_bbr(self):
        source = INSTALLER.read_text()

        self.assertIn("congestion:", source)
        self.assertIn("type: bbr", source)
        self.assertIn("bbrProfile: standard", source)
        self.assertIn("ignoreClientBandwidth: true", source)
        self.assertIn("Nice=-5", source)

    def test_installer_defaults_to_a_persisted_web_egress_policy(self):
        source = INSTALLER.read_text()

        self.assertIn('EXISTING_EGRESS_POLICY="${HY2PANEL_EGRESS_POLICY:-web}"', source)
        self.assertIn('EXISTING_EGRESS_POLICY="web"', source)
        self.assertIn('EGRESS_POLICY="${EGRESS_POLICY:-${EXISTING_EGRESS_POLICY}}"', source)
        self.assertIn('HY2PANEL_EGRESS_POLICY=${EGRESS_POLICY}', source)
        self.assertIn('EGRESS_POLICY 只能是 web 或 full', source)

    def test_web_egress_policy_blocks_private_networks_and_allows_public_ssh(self):
        source = INSTALLER.read_text()

        for rule in (
            "reject(127.0.0.0/8)",
            "reject(10.0.0.0/8)",
            "reject(100.64.0.0/10)",
            "reject(169.254.0.0/16)",
            "reject(172.16.0.0/12)",
            "reject(192.168.0.0/16)",
            "reject(::1/128)",
            "reject(fc00::/7)",
            "reject(fe80::/10)",
            "direct(all, tcp/22)",
            "direct(all, tcp/53)",
            "direct(all, udp/53)",
            "direct(all, tcp/80)",
            "direct(all, tcp/443)",
            "direct(all, udp/443)",
            "direct(all, udp/123)",
            "reject(all)",
        ):
            self.assertIn(rule, source)
        self.assertLess(source.index("reject(127.0.0.0/8)"), source.index("direct(all, tcp/80)"))
        self.assertLess(source.index("reject(fe80::/10)"), source.index("direct(all, tcp/22)"))
        self.assertLess(source.index("direct(all, tcp/22)"), source.index("reject(all)"))
        self.assertIn('if [[ "${EGRESS_POLICY}" == "web" ]]; then', source)

    def test_web_egress_policy_allows_the_public_panel_port_on_future_servers(self):
        source = INSTALLER.read_text()

        self.assertIn('direct(all, tcp/${PANEL_PORT})', source)
        self.assertNotIn("PANEL_ACCESS_IPS", source)
        self.assertNotIn("HY2PANEL_PANEL_ACCESS_IPS", source)
        self.assertLess(
            source.index('direct(all, tcp/${PANEL_PORT})'),
            source.index('reject(all)'),
        )
        self.assertLess(
            source.index("reject(127.0.0.0/8)"),
            source.index('direct(all, tcp/${PANEL_PORT})'),
        )

    def test_installer_grants_only_exact_hysteria_service_controls(self):
        source = INSTALLER.read_text()

        self.assertIn("/etc/sudoers.d/hysteria2-panel", source)
        self.assertIn(
            "hy2panel ALL=(root) NOPASSWD: /bin/systemctl start hysteria2-panel-server.service",
            source,
        )
        self.assertIn(
            "/bin/systemctl stop hysteria2-panel-server.service",
            source,
        )
        self.assertIn(
            "/bin/systemctl restart hysteria2-panel-server.service",
            source,
        )
        self.assertIn(
            "/bin/systemctl --no-block reboot",
            source,
        )
        self.assertIn("visudo -cf", source)
        self.assertIn("sudo", source)
        self.assertEqual(6, source.count("NoNewPrivileges=true"))
        self.assertEqual(6, source.count("PrivateDevices=true"))
        for sandbox_option in (
            "ProtectKernelTunables=true",
            "ProtectKernelModules=true",
            "RestrictSUIDSGID=true",
            "LockPersonality=true",
            "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX",
        ):
            if sandbox_option in {"RestrictSUIDSGID=true", "LockPersonality=true"}:
                expected_count = 6
            elif sandbox_option.endswith("AF_UNIX"):
                expected_count = 4
            else:
                expected_count = 5
            self.assertEqual(expected_count, source.count(sandbox_option), sandbox_option)

    def test_installer_adds_a_root_only_one_shot_restore_service(self):
        source = INSTALLER.read_text()

        self.assertIn("hysteria2-panel-restore.service", source)
        self.assertIn(
            "/bin/systemctl --no-block start hysteria2-panel-restore.service",
            source,
        )
        self.assertIn(
            "ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py restore-pending",
            source,
        )
        self.assertIn(
            "Conflicts=hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-server-443.service hysteria2-panel-tcp-probe.service hysteria2-panel-tcp-probe-443.service",
            source,
        )
        self.assertIn(
            "ExecStopPost=/bin/systemctl --no-block start hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-tcp-probe.service",
            source,
        )
        self.assertNotIn("User=hy2panel\nEnvironmentFile=/etc/hysteria2-panel/panel.env\nExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py restore-pending", source)

    def test_installer_adds_a_fixed_root_only_online_update_service(self):
        source = INSTALLER.read_text()

        self.assertIn("hysteria2-panel-update.service", source)
        self.assertIn(
            "/bin/systemctl --no-block start hysteria2-panel-update.service",
            source,
        )
        self.assertIn(
            "ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py apply-update",
            source,
        )
        self.assertIn("TimeoutStartSec=15min", source)
        update_unit = source.split(
            'cat > /etc/systemd/system/hysteria2-panel-update.service <<EOF', 1
        )[1].split("EOF", 1)[0]
        self.assertIn(
            "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK",
            update_unit,
        )
        self.assertNotIn(
            "User=hy2panel\nEnvironmentFile=/etc/hysteria2-panel/panel.env\nExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py apply-update",
            source,
        )


class TcpProbeTests(unittest.TestCase):
    def test_probe_accepts_tcp_connections_without_sending_application_data(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]

        process = subprocess.Popen(
            [sys.executable, str(TCP_PROBE), str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 3
            while True:
                try:
                    connection = socket.create_connection(("127.0.0.1", port), timeout=0.2)
                    break
                except OSError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        stdout, stderr = process.communicate(timeout=1)
                        self.fail(f"TCP probe did not start: {stdout}{stderr}")
                    time.sleep(0.05)

            with connection:
                connection.settimeout(1)
                self.assertEqual(b"", connection.recv(1))
        finally:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            process.communicate()


if __name__ == "__main__":
    unittest.main()
