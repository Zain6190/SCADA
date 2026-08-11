# tests/unit/test_water_alert.py
import unittest
from datetime import date

from domain.entities import DomainValidationError, WaterAlert


def make_alert(status="New"):
    return WaterAlert(
        id=1,
        region_id=5,
        week_start_date=date(2026, 7, 20),
        alert_type="WAI_CRITICAL",
        severity="Critical",
        status=status,
    )


class TestWaterAlertStateMachine(unittest.TestCase):
    def test_acknowledge_transition(self):
        alert = make_alert()
        alert.acknowledge()
        self.assertEqual(alert.status, "Acknowledged")
        self.assertIsNotNone(alert.acknowledged_at)

    def test_acknowledge_rejects_resolved(self):
        alert = make_alert(status="Resolved")
        with self.assertRaises(DomainValidationError):
            alert.acknowledge()

    def test_resolve_from_acknowledged(self):
        alert = make_alert(status="Acknowledged")
        alert.resolve()
        self.assertEqual(alert.status, "Resolved")
        self.assertIsNotNone(alert.resolved_at)

    def test_resolve_from_new_sets_ack_and_resolved(self):
        alert = make_alert()
        alert.resolve()
        self.assertEqual(alert.status, "Resolved")
        self.assertIsNotNone(alert.acknowledged_at)
        self.assertIsNotNone(alert.resolved_at)

    def test_resolve_rejects_resolved(self):
        alert = make_alert(status="Resolved")
        with self.assertRaises(DomainValidationError):
            alert.resolve()


if __name__ == "__main__":
    unittest.main()
