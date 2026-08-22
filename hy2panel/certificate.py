"""Certificate validity inspection shared by health monitoring and backups."""

import datetime
import re
# The executable and every argument are fixed by the caller below.
import subprocess  # nosec B404


def _parse_openssl_time(value, label):
    months = {
        "Jan": 1,
        "Feb": 2,
        "Mar": 3,
        "Apr": 4,
        "May": 5,
        "Jun": 6,
        "Jul": 7,
        "Aug": 8,
        "Sep": 9,
        "Oct": 10,
        "Nov": 11,
        "Dec": 12,
    }
    match = re.fullmatch(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
        r"([0-9]{1,2})\s+([0-9]{2}):([0-9]{2}):([0-9]{2})\s+"
        r"([0-9]{4})\s+GMT",
        value,
    )
    if match is None:
        raise ValueError("certificate {} is invalid".format(label))
    try:
        month, day, hour, minute, second, year = match.groups()
        return datetime.datetime(
            int(year),
            months[month],
            int(day),
            int(hour),
            int(minute),
            int(second),
            tzinfo=datetime.timezone.utc,
        ).timestamp()
    except (OverflowError, ValueError) as exc:
        raise ValueError("certificate {} is invalid".format(label)) from exc


def certificate_validity_timestamps(path, runner=subprocess.run):
    try:
        result = runner(
            [
                "/usr/bin/openssl",
                "x509",
                "-in",
                str(path),
                "-startdate",
                "-enddate",
                "-noout",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("certificate validity could not be inspected") from exc
    values = {}
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if "=" in line:
                name, value = line.split("=", 1)
                if name in values:
                    raise ValueError("certificate validity is ambiguous")
                values[name] = value
    if set(values) != {"notBefore", "notAfter"}:
        raise ValueError("certificate validity could not be inspected")
    not_before = _parse_openssl_time(values["notBefore"], "notBefore")
    not_after = _parse_openssl_time(values["notAfter"], "notAfter")
    if not_before >= not_after:
        raise ValueError("certificate validity window is invalid")
    return not_before, not_after


def certificate_expiry_timestamp(path, runner=subprocess.run):
    return certificate_validity_timestamps(path, runner=runner)[1]
