import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".html", ".js", ".json", ".md", ".py", ".sh", ".yaml", ".yml"}


class PublicRepositoryHygieneTests(unittest.TestCase):
    def test_retired_production_identifiers_are_not_in_public_sources(self):
        forbidden = (
            "ssrvpn" + ".vip",
            "vpn." + "ssrvpn.vip",
            "panel." + "ssrvpn.vip",
            "155.103." + "116.201",
            "155.103." + "116.243",
            "154.9." + "234.210",
            "154.9." + "234.211",
        )
        findings = []
        for path in ROOT.rglob("*"):
            if (
                not path.is_file()
                or path == Path(__file__).resolve()
                or path.suffix not in TEXT_SUFFIXES
                or any(part in {".git", ".venv", "__pycache__"} for part in path.parts)
            ):
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            if any(value in source for value in forbidden):
                findings.append(str(path.relative_to(ROOT)))
        self.assertEqual([], findings)


if __name__ == "__main__":
    unittest.main()
