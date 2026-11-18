import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile" / "lib"
SCREENS = MOBILE / "screens"


class MobileUiContractTests(unittest.TestCase):
    # Navigation geometry and interaction are exercised by Flutter widget
    # tests in mobile/test/home_shell_test.dart, not source spelling.

    def test_primary_headers_scroll_without_an_opaque_mask(self) -> None:
        source = "\n".join(path.read_text() for path in SCREENS.glob("*.dart"))
        self.assertNotIn("pinned: true", source)
        for name in ('home', 'nodes', 'users', 'subscriptions', 'settings'):
            page = (SCREENS / (name + '_screen.dart')).read_text()
            self.assertIn('PanelHeading(', page)
            self.assertTrue('ListView(' in page or 'CustomScrollView(' in page)
        app = (MOBILE / "core" / "app_theme.dart").read_text()
        self.assertIn("backgroundColor: Colors.transparent", app)

    def test_dialogs_sheets_and_dropdowns_use_shared_glass_styling(self) -> None:
        source = "\n".join(path.read_text() for path in SCREENS.glob("*.dart"))
        self.assertNotIn("AlertDialog(", source)
        self.assertNotIn("showModalBottomSheet", source)
        self.assertGreaterEqual(source.count("GlassDialog("), 10)
        self.assertGreaterEqual(source.count("showGlassModalBottomSheet"), 2)
        self.assertNotIn("DropdownButtonFormField", source)
        # Selection/cancel behavior lives in mobile/test/glass_test.dart.

    def test_system_resource_cells_have_distinct_surfaces_and_scalable_height(self) -> None:
        source = (SCREENS / "admin_controls.dart").read_text()
        resource_source = source.split('Widget _resource(', 1)[1].split('Widget ', 1)[0]
        self.assertIn('GlassCard(', resource_source)
        self.assertIn('Expanded(', resource_source)
        self.assertIn('LinearProgressIndicator(', resource_source)
        # Content-driven height replaced the old overview GridView. Large-font
        # layout is also exercised by the Xiaomi Flutter interaction tests.
        self.assertNotIn('mainAxisExtent:', resource_source)



if __name__ == "__main__":
    unittest.main()
