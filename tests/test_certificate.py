import datetime
import locale
import unittest

from hy2panel.certificate import (
    certificate_expiry_timestamp,
    certificate_validity_timestamps,
)


class CertificateExpiryTests(unittest.TestCase):
    def test_parses_openssl_not_after_in_utc(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": (
                        "notBefore=Aug 22 12:34:56 2026 GMT\n"
                        "notAfter=Aug 22 12:34:56 2027 GMT\n"
                    ),
                    "stderr": "",
                },
            )()

        timestamp = certificate_expiry_timestamp("/etc/panel/server.crt", runner)

        self.assertEqual(
            datetime.datetime(
                2027, 8, 22, 12, 34, 56, tzinfo=datetime.timezone.utc
            ).timestamp(),
            timestamp,
        )
        self.assertEqual(
            [
                "/usr/bin/openssl",
                "x509",
                "-in",
                "/etc/panel/server.crt",
                "-startdate",
                "-enddate",
                "-noout",
            ],
            calls[0][0],
        )
        self.assertEqual(10, calls[0][1]["timeout"])

    def test_rejects_failed_or_malformed_openssl_output(self):
        for returncode, stdout in ((1, ""), (0, "invalid")):
            with self.subTest(returncode=returncode, stdout=stdout):
                def runner(*_args, **_kwargs):
                    return type(
                        "Result",
                        (),
                        {
                            "returncode": returncode,
                            "stdout": stdout,
                            "stderr": "",
                        },
                    )()

                with self.assertRaises(ValueError):
                    certificate_expiry_timestamp("server.crt", runner)

    def test_parses_and_validates_both_validity_bounds(self):
        def runner(*_args, **_kwargs):
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": (
                        "notBefore=Aug 22 12:34:56 2026 GMT\n"
                        "notAfter=Aug 22 12:34:56 2027 GMT\n"
                    ),
                    "stderr": "",
                },
            )()

        not_before, not_after = certificate_validity_timestamps(
            "server.crt", runner
        )

        self.assertLess(not_before, not_after)

        def reversed_runner(*_args, **_kwargs):
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": (
                        "notBefore=Aug 22 12:34:56 2028 GMT\n"
                        "notAfter=Aug 22 12:34:56 2027 GMT\n"
                    ),
                    "stderr": "",
                },
            )()

        with self.assertRaises(ValueError):
            certificate_validity_timestamps("server.crt", reversed_runner)

    def test_english_openssl_dates_do_not_depend_on_process_locale(self):
        original_locale = locale.setlocale(locale.LC_TIME)
        selected = None
        for candidate in ("fr_FR.UTF-8", "de_DE.UTF-8", "zh_CN.UTF-8"):
            try:
                locale.setlocale(locale.LC_TIME, candidate)
            except locale.Error:
                continue
            selected = candidate
            break
        if selected is None:
            self.skipTest("non-English locale is not installed")
        try:
            def runner(*_args, **_kwargs):
                return type(
                    "Result",
                    (),
                    {
                        "returncode": 0,
                        "stdout": (
                            "notBefore=Aug  2 12:34:56 2026 GMT\n"
                            "notAfter=Aug 22 12:34:56 2027 GMT\n"
                        ),
                        "stderr": "",
                    },
                )()

            not_before, not_after = certificate_validity_timestamps(
                "server.crt", runner
            )

            self.assertLess(not_before, not_after)
        finally:
            locale.setlocale(locale.LC_TIME, original_locale)


if __name__ == "__main__":
    unittest.main()
