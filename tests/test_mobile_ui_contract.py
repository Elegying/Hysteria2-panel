import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile" / "lib"
SCREENS = MOBILE / "screens"


class MobileUiContractTests(unittest.TestCase):
    # Navigation geometry and interaction are exercised by Flutter widget
    # tests in mobile/test/home_shell_test.dart, not source spelling.

    def test_primary_headers_scroll_without_an_opaque_mask(self) -> None:
        source = "\n".join(path.read_text() for path in SCREENS.glob("*_screen.dart"))
        self.assertNotIn("pinned: true", source)
        self.assertEqual(source.count("pinned: false"), 5)
        app = (MOBILE / "core" / "app_theme.dart").read_text()
        self.assertIn("backgroundColor: Colors.transparent", app)

    def test_dialogs_sheets_and_dropdowns_use_shared_glass_styling(self) -> None:
        source = "\n".join(path.read_text() for path in SCREENS.glob("*_screen.dart"))
        self.assertNotIn("AlertDialog(", source)
        self.assertNotIn("showModalBottomSheet", source)
        self.assertGreaterEqual(source.count("GlassDialog("), 10)
        self.assertEqual(source.count("showGlassModalBottomSheet"), 2)
        self.assertNotIn("DropdownButtonFormField", source)
        # Selection/cancel behavior lives in mobile/test/glass_test.dart.

    def test_system_resource_cells_have_distinct_surfaces_and_scalable_height(self) -> None:
        source = (SCREENS / "home_screen.dart").read_text()
        resource_start = source.index("class _ResourcesCard")
        resource_source = source[resource_start:]
        self.assertIn("GlassSurface(", resource_source)
        self.assertIn("mainAxisExtent:", resource_source)
        self.assertIn("MediaQuery.textScalerOf(context)", resource_source)


if __name__ == "__main__":
    unittest.main()
