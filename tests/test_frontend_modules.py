from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "ui" / "web_dashboard" / "static"
INDEX = STATIC / "index.html"
APP = STATIC / "app.js"
API = STATIC / "api.js"
PREFERENCES = STATIC / "preferences.js"
STATUS = STATIC / "status.js"
NAVIGATION = STATIC / "navigation.js"
OVERLAYS = STATIC / "overlays.js"
VEHICLE = STATIC / "vehicle.js"


class FrontendModuleBoundaryTests(unittest.TestCase):
    def test_modules_load_before_application(self):
        html = INDEX.read_text(encoding="utf-8")
        api_index = html.index('<script src="/api.js"></script>')
        preferences_index = html.index('<script src="/preferences.js"></script>')
        status_index = html.index('<script src="/status.js"></script>')
        navigation_index = html.index('<script src="/navigation.js"></script>')
        overlays_index = html.index('<script src="/overlays.js"></script>')
        vehicle_index = html.index('<script src="/vehicle.js"></script>')
        app_index = html.index('<script src="/app.js"></script>')
        self.assertLess(api_index, preferences_index)
        self.assertLess(preferences_index, status_index)
        self.assertLess(status_index, navigation_index)
        self.assertLess(navigation_index, overlays_index)
        self.assertLess(overlays_index, vehicle_index)
        self.assertLess(vehicle_index, app_index)

    def test_application_uses_frontend_modules(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("window.openMmiApi", source)
        self.assertIn("window.openMmiPreferences", source)
        self.assertIn("window.openMmiStatus", source)
        self.assertIn("window.openMmiNavigation", source)
        self.assertIn("window.openMmiOverlays", source)
        self.assertIn("window.openMmiVehicle", source)
        self.assertIn("openMmiStatusClient.createStore()", source)
        self.assertIn("openMmiNavigationClient.createController()", source)
        self.assertIn("openMmiOverlaysClient.createController()", source)
        self.assertIn("openMmiVehicleClient.createRenderer({ preferences: openMmiPrefs })", source)
        self.assertIn("window.setPage = (index) => openMmiNavigationController.setPage(index);", source)
        self.assertIn("openMmiStatusClient.createPoller({", source)
        self.assertIn("openMmiApiClient.postJson(", source)
        self.assertNotIn('openMmiApiClient.getJson("/api/status"', source)
        self.assertNotIn("localStorage.", source)

    def test_modules_are_browser_and_commonjs_compatible(self):
        api = API.read_text(encoding="utf-8")
        preferences = PREFERENCES.read_text(encoding="utf-8")
        status = STATUS.read_text(encoding="utf-8")
        navigation = NAVIGATION.read_text(encoding="utf-8")
        overlays = OVERLAYS.read_text(encoding="utf-8")
        vehicle = VEHICLE.read_text(encoding="utf-8")
        for source, global_name in (
            (api, "openMmiApi"),
            (preferences, "openMmiPreferences"),
            (status, "openMmiStatus"),
            (navigation, "openMmiNavigation"),
            (overlays, "openMmiOverlays"),
            (vehicle, "openMmiVehicle"),
        ):
            self.assertIn("typeof module === \"object\"", source)
            self.assertIn(f"root.{global_name}", source)
            self.assertNotIn("document.", source)


    def test_status_module_owns_polling_and_shared_state(self):
        source = STATUS.read_text(encoding="utf-8")
        self.assertIn('const DEFAULT_STATUS_PATH = "/api/status";', source)
        self.assertIn("const DEFAULT_STATUS_INTERVAL_MS = 200;", source)
        self.assertIn("function createStore(initialPayload = null)", source)
        self.assertIn("function createPoller(options = {})", source)
        self.assertIn("scheduler.setInterval(fetchStatus, intervalMs)", source)
        self.assertNotIn("document.", source)


    def test_navigation_module_owns_page_state_and_home_menu(self):
        source = NAVIGATION.read_text(encoding="utf-8")
        app = APP.read_text(encoding="utf-8")
        self.assertIn("function createController(options = {})", source)
        self.assertIn("function showPageById(id, title, quickIndex = HOME_INDEX)", source)
        self.assertIn("function ensureHomePage()", source)
        self.assertIn('windowRef.addEventListener("keydown", keyHandler)', source)
        self.assertNotIn("function ensureHomePage()", app)
        self.assertNotIn("const QUICK_PAGES =", app)

    def test_overlay_module_owns_detection_and_visibility_lifecycle(self):
        source = OVERLAYS.read_text(encoding="utf-8")
        app = APP.read_text(encoding="utf-8")
        self.assertIn("function collectOpenDoors(payload)", source)
        self.assertIn("function reverseSelected(payload)", source)
        self.assertIn("function reduceDoorOverlay(state, openDoors)", source)
        self.assertIn("function reduceReverseOverlay(state, active)", source)
        self.assertIn('overlay.id = "openMmiVehicleOverlay"', source)
        self.assertIn('overlay.id = "openMmiReverseOverlay"', source)
        self.assertNotIn("function collectOpenDoors(payload)", app)
        self.assertNotIn("function reverseSelected(payload)", app)


    def test_vehicle_module_owns_vehicle_and_climate_rendering(self):
        source = VEHICLE.read_text(encoding="utf-8")
        app = APP.read_text(encoding="utf-8")
        self.assertIn("function buildViewModel(payload = {}, settings = DEFAULT_SETTINGS)", source)
        self.assertIn("function createRenderer(options = {})", source)
        self.assertIn("climate.recirculation_active ?? climate.front_demist_air_request", source)
        self.assertIn("function updateTach(rpm)", source)
        self.assertIn("function updateCoolantGauge(payload)", source)
        self.assertNotIn("function updateTach(rpm)", app)
        self.assertNotIn("function updateDoor(name, value)", app)
        self.assertNotIn("function openMmiFormatTempFromC", app)

    def test_api_reads_fetch_at_call_time_for_instrumentation(self):
        source = API.read_text(encoding="utf-8")
        self.assertIn("const fetchImpl = root && root.fetch", source)
        self.assertNotIn("const fetchImpl = root.fetch.bind", source)


if __name__ == "__main__":
    unittest.main()
