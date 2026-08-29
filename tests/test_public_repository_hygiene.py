import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".html", ".js", ".json", ".md", ".py", ".sh", ".yaml", ".yml"}
SCANNER_PATH = ROOT / ".github" / "scripts" / "check_history_privacy.py"
SCANNER_SPEC = importlib.util.spec_from_file_location("check_history_privacy", SCANNER_PATH)
scanner = importlib.util.module_from_spec(SCANNER_SPEC)
SCANNER_SPEC.loader.exec_module(scanner)


class PublicRepositoryHygieneTests(unittest.TestCase):
    def test_retired_production_identifiers_are_not_in_public_sources(self):
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
            if any(label == "retired-identifier" for _line, label in scanner.scan_text(source)):
                findings.append(str(path.relative_to(ROOT)))
        self.assertEqual([], findings)

    def test_history_scanner_rejects_high_confidence_secrets_without_echoing_them(self):
        private_material = (
            "-----BEGIN PRIVATE KEY-----\n"
            + "A" * 160
            + "\n-----END PRIVATE KEY-----\n"
        )
        findings = scanner.scan_text(private_material)
        self.assertIn((1, "private-key"), findings)
        self.assertEqual([], scanner.scan_text("dummy token and TEST private key fixtures"))


if __name__ == "__main__":
    unittest.main()
