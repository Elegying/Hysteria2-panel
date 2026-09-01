import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile" / "lib"
SCREENS = MOBILE / "screens"


class MobileUiContractTests(unittest.TestCase):
    def test_bottom_navigation_respects_rounded_screen_safe_area(self) -> None:
        source = (SCREENS / "home_shell.dart").read_text()
        self.assertIn("extendBody: true", source)
        self.assertIn("EdgeInsets.fromLTRB(12, 0, 12, 18)", source)

    def test_primary_headers_scroll_without_an_opaque_mask(self) -> None:
        source = "\n".join(path.read_text() for path in SCREENS.glob("*_screen.dart"))
        self.assertNotIn("pinned: true", source)
        self.assertEqual(source.count("pinned: false"), 4)
        app = (MOBILE / "app.dart").read_text()
        self.assertIn("backgroundColor: Colors.transparent", app)

    def test_dialogs_sheets_and_dropdowns_use_shared_glass_styling(self) -> None:
        source = "\n".join(path.read_text() for path in SCREENS.glob("*_screen.dart"))
        self.assertNotIn("AlertDialog(", source)
        self.assertNotIn("showModalBottomSheet", source)
        self.assertGreaterEqual(source.count("GlassDialog("), 10)
        self.assertEqual(source.count("showGlassModalBottomSheet"), 2)
        self.assertEqual(source.count("dropdownColor: glassMenuColor(context)"), 3)

    def test_system_resource_cells_have_visible_edges_and_depth(self) -> None:
        source = (SCREENS / "home_screen.dart").read_text()
        resource_start = source.index("class _ResourcesCard")
        resource_source = source[resource_start:]
        self.assertIn("border: Border.all(", resource_source)
        self.assertIn("boxShadow: [", resource_source)


if __name__ == "__main__":
    unittest.main()
