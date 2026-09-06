import contextlib
import errno
import io
import socket
import unittest
from pathlib import Path
from unittest import mock

from hy2panel.operations import EgressPolicyManager


ROOT = Path(__file__).resolve().parents[1]


class IPv6EgressTests(unittest.TestCase):
    def detect(self, results):
        source = (ROOT / 'install.sh').read_text()
        section = source.split('detect_direct_outbound_mode() {', 1)[1]
        code = section.split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        connection.connect.side_effect = results
        output = io.StringIO()
        with mock.patch.object(socket, 'socket', return_value=connection), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            exec(compile(code, 'installer-egress-detection', 'exec'), {})
        return output.getvalue().strip()

    def test_only_confirmed_ipv4_route_with_missing_ipv6_selects_ipv4(self):
        missing = OSError(errno.ENETUNREACH, 'no route')
        self.assertEqual('4', self.detect([missing, missing, None]))
        self.assertEqual('auto', self.detect([None, None]))
        self.assertEqual('auto', self.detect([missing, None]))
        self.assertEqual('auto', self.detect([missing, missing, missing]))
        self.assertEqual('auto', self.detect([OSError(errno.EPERM, 'blocked'), missing]))

    def test_policy_switch_keeps_direct_mode_and_private_network_rejections(self):
        source = ('outbounds:\n  - name: direct\n    type: direct\n'
                  '    direct:\n      mode: "4"\n'
                  + EgressPolicyManager._acl_block('full', 19998)
                  + 'masquerade:\n  type: string\n')
        changed = EgressPolicyManager._replace_acl(source.encode(), 'web', 19998)
        self.assertIn(b'mode: "4"', changed)
        self.assertIn(b'reject(10.0.0.0/8)', changed)
        restored = EgressPolicyManager._replace_acl(changed, 'full', 19998)
        self.assertEqual(source.encode(), restored)

    def test_installer_reuses_detection_for_panel_and_node_and_quotes_yaml_mode(self):
        source = (ROOT / 'install.sh').read_text()
        self.assertIn('DIRECT_OUTBOUND_MODE="$(detect_direct_outbound_mode)"', source)
        self.assertIn('--outbound-mode "$(detect_direct_outbound_mode)"', source)
        self.assertIn('      mode: "${DIRECT_OUTBOUND_MODE}"', source)


if __name__ == '__main__':
    unittest.main()
