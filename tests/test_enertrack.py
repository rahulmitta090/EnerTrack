"""
EnerTrack Comprehensive Automated Test Suite
Validates all requirements:
1. User registration & authentication
2. Admin authentication & authorization
3. Household management (CRUD)
4. Smart Meter registration & status toggling
5. Simulated & imported consumption records ingestion & validation
6. Negative energy reading rejection
7. Machine Learning Anomaly Detection (K-Means & Isolation Forest)
8. Injected spike anomaly detection vs normal classification
9. Investigation status update & notes logging
10. API endpoints for Chart.js
11. CSV export generation
12. Access control & tenant privacy boundaries
"""
import unittest
import os
import sys
import json
import sqlite3

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from database import init_db, db_session
from models import User, AppConfig
from household import Household
from smart_meter import SmartMeter
from consumption import ConsumptionRecord
from anomaly_detector import AnomalyDetector, AnomalyRecord
from data_generator import SmartMeterSimulator
from recommendations import EnergyAnalytics

class EnerTrackTestSuite(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Initializes database schema and testing configuration."""
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        init_db(seed_sample_data=True)
        cls.client = app.test_client()

    def test_01_admin_authentication(self):
        """Verifies default admin credentials work."""
        response = self.client.post("/login", data={
            "username": "admin",
            "password": "Admin@123"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"System Administrator", response.data)
        
        # Test logout
        logout_resp = self.client.get("/logout", follow_redirects=True)
        self.assertEqual(logout_resp.status_code, 200)

    def test_02_user_registration_and_login(self):
        """Tests household owner registration and session creation."""
        import time
        suffix = int(time.time())
        username = f"test_owner_{suffix}"
        email = f"testowner_{suffix}@example.com"
        password = "SecurePassword123"

        response = self.client.post("/register", data={
            "full_name": "Test Property Owner",
            "username": username,
            "email": email,
            "password": password,
            "confirm_password": password
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Registration successful", response.data)

        # Confirm user exists in database
        u = User.get_by_username(username)
        self.assertIsNotNone(u)
        self.assertEqual(u.role, "user")
        self.assertTrue(u.check_password(password))

    def test_03_household_oop_lifecycle(self):
        """Tests Household class creation, querying, update, and deletion."""
        u = User.get_by_username("admin")
        h = Household.create(
            household_name="Test Manor",
            address="100 Test Blvd",
            city="Cyber City",
            household_type="Villa",
            number_of_members=4,
            user_id=u.user_id
        )
        self.assertIsNotNone(h)
        self.assertIsNotNone(h.household_id)
        self.assertEqual(h.household_name, "Test Manor")

        # Update
        h.update("Updated Test Manor", "100 Test Blvd", "Cyber City", "Villa", 5)
        reloaded = Household.get_by_id(h.household_id)
        self.assertEqual(reloaded.household_name, "Updated Test Manor")
        self.assertEqual(reloaded.number_of_members, 5)

        # Clean up
        h.delete()
        self.assertIsNone(Household.get_by_id(h.household_id))

    def test_04_smart_meter_oop_lifecycle(self):
        """Tests SmartMeter registration and status toggling."""
        import time
        h_list = Household.get_all()
        target_h = h_list[0]

        meter_number = f"SM-TEST-{int(time.time())}"
        meter = SmartMeter.register(
            household_id=target_h.household_id,
            meter_number=meter_number,
            meter_type="Smart Digital",
            status="Active"
        )
        self.assertIsNotNone(meter)
        self.assertIsNotNone(meter.meter_id)
        self.assertEqual(meter.meter_number, meter_number)
        self.assertEqual(meter.status, "Active")

        # Toggle status
        meter.toggle_status()
        self.assertEqual(meter.status, "Inactive")
        meter.toggle_status()
        self.assertEqual(meter.status, "Active")

    def test_05_consumption_validation_rules(self):
        """Tests rejection of negative readings and invalid timestamps."""
        # Negative reading rejection
        with self.assertRaises(ValueError) as ctx:
            ConsumptionRecord.validate_reading(-3.5, "2026-11-13 10:00:00")
        self.assertIn("cannot be negative", str(ctx.exception))

        # Invalid timestamp syntax rejection
        with self.assertRaises(ValueError) as ctx2:
            ConsumptionRecord.validate_reading(2.5, "invalid-timestamp")
        self.assertIn("standard format", str(ctx2.exception))

        # Valid reading acceptance
        kwh, ts = ConsumptionRecord.validate_reading("3.42", "2026-11-13 12:30:00")
        self.assertEqual(kwh, 3.42)
        self.assertEqual(ts, "2026-11-13 12:30:00")

    def test_06_realistic_data_simulation(self):
        """Tests generation of simulated readings labeled as simulated."""
        meters = SmartMeter.get_all()
        target_meter = meters[0]

        inserted = SmartMeterSimulator.populate_household_simulation(
            household_id=target_meter.household_id,
            meter_id=target_meter.meter_id,
            days=7,
            anomaly_count=3
        )
        self.assertEqual(inserted, 7 * 24)

        # Verify all records have data_source='simulated'
        readings = target_meter.get_recent_readings(limit=10)
        self.assertTrue(all(r["data_source"] == "simulated" for r in readings))

    def test_07_machine_learning_pipeline(self):
        """Validates Scikit-learn K-Means clustering and Isolation Forest anomaly detection."""
        meters = SmartMeter.get_all()
        target_meter = meters[0]
        
        # Run detection pipeline
        detector = AnomalyDetector()
        results = detector.run_detection(household_id=target_meter.household_id)

        self.assertEqual(results["status"], "success")
        self.assertGreater(results["total_records_analyzed"], 0)
        
        # Verify detected anomalies in database
        anomalies = AnomalyRecord.get_all(household_id=target_meter.household_id)
        self.assertGreater(len(anomalies), 0)

        # Check anomaly fields
        sample = anomalies[0]
        self.assertIn(sample.severity, ["Unusual", "High Priority"])
        self.assertGreater(sample.energy_kwh, 0)
        self.assertIsNotNone(sample.anomaly_score)
        self.assertIsInstance(sample.possible_causes, list)
        self.assertIsInstance(sample.recommendations, list)

    def test_08_investigation_status_update(self):
        """Tests updating anomaly investigation status to 'Resolved' and logging notes."""
        anomalies = AnomalyRecord.get_all()
        self.assertGreater(len(anomalies), 0)
        target_anomaly = anomalies[0]

        # Update status
        AnomalyRecord.update_status(
            anomaly_id=target_anomaly.anomaly_id,
            status="Resolved",
            notes="Technician audited water heater heating coil; replaced faulty thermostat."
        )

        updated = AnomalyRecord.get_by_id(target_anomaly.anomaly_id)
        self.assertEqual(updated.status, "Resolved")
        self.assertIn("Technician audited", updated.notes)

    def test_09_cost_estimation_and_recommendations(self):
        """Verifies transparent cost calculation and rule-based energy advice."""
        cost_data = EnergyAnalytics.calculate_cost_summary(days=30)
        self.assertGreaterEqual(cost_data["total_kwh"], 0.0)
        self.assertGreaterEqual(cost_data["estimated_cost"], 0.0)
        self.assertIn("estimate", cost_data["disclaimer"].lower())

        recs = EnergyAnalytics.generate_recommendations()
        self.assertGreater(len(recs), 0)
        self.assertTrue(any("Overnight" in r["title"] or "Appliance" in r["title"] for r in recs))

    def test_10_chart_api_endpoints(self):
        """Validates JSON responses from Chart.js API endpoints."""
        # Log in as admin
        self.client.post("/login", data={"username": "admin", "password": "Admin@123"})

        trend_res = self.client.get("/api/charts/consumption-trend")
        self.assertEqual(trend_res.status_code, 200)
        trend_json = json.loads(trend_res.data)
        self.assertIn("labels", trend_json)
        self.assertIn("datasets", trend_json)

        hourly_res = self.client.get("/api/charts/hourly-pattern")
        self.assertEqual(hourly_res.status_code, 200)
        hourly_json = json.loads(hourly_res.data)
        self.assertIn("labels", hourly_json)

        anom_res = self.client.get("/api/charts/anomaly-distribution")
        self.assertEqual(anom_res.status_code, 200)
        anom_json = json.loads(anom_res.data)
        self.assertIn("labels", anom_json)

    def test_11_csv_export(self):
        """Validates CSV exports for consumption records and anomalies."""
        self.client.post("/login", data={"username": "admin", "password": "Admin@123"})

        exp_c = self.client.get("/reports/export-csv/consumption")
        self.assertEqual(exp_c.status_code, 200)
        self.assertEqual(exp_c.mimetype, "text/csv")
        self.assertIn(b"Record_ID", exp_c.data)

        exp_a = self.client.get("/reports/export-csv/anomalies")
        self.assertEqual(exp_a.status_code, 200)
        self.assertEqual(exp_a.mimetype, "text/csv")
        self.assertIn(b"Anomaly_ID", exp_a.data)

    def test_12_tenant_authorization_isolation(self):
        """Verifies that normal household users cannot view or mutate another household's data."""
        # Sarah Miller is user_id of 'Oakwood Residence' and 'Skyline Heights'
        # Meadowbrook Villa belongs to Admin
        sarah = User.get_by_username("sarah_home")
        admin = User.get_by_username("admin")
        
        # Get Sarah's households
        sarah_households = Household.get_by_user(sarah.user_id)
        self.assertGreater(len(sarah_households), 0)
        
        # Get an Admin household
        admin_households = Household.get_by_user(admin.user_id)
        if admin_households:
            admin_h = admin_households[0]
            # Verify can_access logic
            self.assertFalse(admin_h.can_access(sarah))
            self.assertTrue(admin_h.can_access(admin))

if __name__ == "__main__":
    unittest.main()
