import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RADIO = ROOT / "ui" / "web_dashboard" / "static" / "media-radio.js"
APP = ROOT / "ui" / "web_dashboard" / "static" / "app.js"
DOCS = ROOT / "docs" / "media-sources.md"


class RadioPrivacyConsentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = APP.read_text(encoding="utf-8")
        cls.radio = RADIO.read_text(encoding="utf-8")
        cls.docs = DOCS.read_text(encoding="utf-8")

    def test_consent_gate_installs_before_radio_adapter(self):
        privacy = self.app.index("openMmiRadioMediaClient.installPrivacy")
        adapter = self.app.index("openMmiRadioMediaClient.installController")
        self.assertLess(privacy, adapter)

    def test_radio_enable_is_intercepted_in_capture_phase(self):
        self.assertIn('document.addEventListener("click", interceptRadioEnable, true)', self.radio)
        self.assertIn("event.stopImmediatePropagation()", self.radio)
        self.assertIn('data-openmmi-media-source-enable="radio"', self.radio)

    def test_consent_is_versioned_and_fail_closed(self):
        self.assertIn('const CONSENT_KEY = "openmmi.media.radio.privacy-consent.v1"', self.radio)
        self.assertIn('const NOTICE_VERSION = "2026-07-11-v1"', self.radio)
        self.assertIn("!hasCurrentConsent() && disableRadioPreference()", self.radio)
        self.assertIn("if (!saveConsent() || !hasCurrentConsent())", self.radio)
        self.assertIn("sourceId !== \"radio\" || hasCurrentConsent()", self.radio)

    def test_notice_names_material_external_disclosures(self):
        for phrase in [
            "public IP address",
            "search text and country/language filters",
            "station-click notification",
            "connection duration and data transferred",
            "does not request GPS location",
            "local storage",
        ]:
            self.assertIn(phrase, self.radio)

    def test_docs_do_not_overpromise_external_privacy(self):
        self.assertIn("does not control the privacy", self.docs)
        self.assertIn("retention", self.docs)
        self.assertIn("openmmi.media.radio.privacy-consent.v1", self.docs)


if __name__ == "__main__":
    unittest.main()
