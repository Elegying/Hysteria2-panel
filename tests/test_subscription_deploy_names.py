import os
from pathlib import Path
import subprocess
import unittest
from hysteria2_panel import Settings

ROOT = Path(__file__).resolve().parents[1]


class SubscriptionDeploymentNamesTests(unittest.TestCase):
    def test_settings_separate_and_validate_subscription_name(self):
        base = {
            "HY2PANEL_HMAC_KEY": "ab" * 32,
            "HY2PANEL_PUBLIC_HOST": "vpn.example.com",
            "HY2PANEL_STATS_SECRET": "stats-secret",
            "HY2PANEL_CERT_PIN": "ab" * 32,
            "HY2PANEL_NODE_NAME": "自定义节点",
        }
        self.assertEqual("私家车", Settings.from_mapping(base).subscription_name)
        settings = Settings.from_mapping(
            {**base, "HY2PANEL_SUBSCRIPTION_NAME": "自定义订阅"}
        )
        self.assertEqual("自定义订阅", settings.subscription_name)
        self.assertEqual("自定义节点", settings.node_name)
        for invalid in ("", "x" * 65, "bad\nname"):
            with self.assertRaises(ValueError):
                Settings.from_mapping({**base, "HY2PANEL_SUBSCRIPTION_NAME": invalid})

    def test_install_prompts_accept_independent_names_and_defaults(self):
        source = (ROOT / "install.sh").read_text()
        start = source.index('SUBSCRIPTION_NAME="${SUBSCRIPTION_NAME:-}"')
        end = source.index('PUBLIC_HOST="${PUBLIC_HOST:-}"', start)
        prompt = source[start:end].replace("</dev/tty", "</dev/null")
        script = (
            """fail() { exit 97; }
read() { local variable="${!#}"; if [[ "$variable" == SUBSCRIPTION_NAME ]]; then printf -v "$variable" '%s' "$SUB_INPUT"; else printf -v "$variable" '%s' "$NODE_INPUT"; fi; }
"""
            + prompt
            + '\nprintf "%s|%s" "$SUBSCRIPTION_NAME" "$NODE_NAME"\n'
        )
        for sub, node, expected in [
            ("家庭订阅", "香港节点", "家庭订阅|香港节点"),
            ("", "", "私家车|原节点"),
        ]:
            result = subprocess.run(
                ["bash", "-eu", "-c", script],
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "SUBSCRIPTION_NAME": "",
                    "NODE_NAME": "",
                    "EXISTING_SUBSCRIPTION_NAME": "私家车",
                    "EXISTING_NODE_NAME": "原节点",
                    "SUB_INPUT": sub,
                    "NODE_INPUT": node,
                },
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(expected, result.stdout)
