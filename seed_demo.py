"""
EnerTrack Demo Database Seeder
Populates realistic simulated smart-meter telemetry and executes the ML detection pipeline
for instant evaluation.
"""
from database import init_db
from smart_meter import SmartMeter
from data_generator import SmartMeterSimulator
from anomaly_detector import AnomalyDetector

def seed_full_demo():
    print("Initializing EnerTrack database schema...")
    init_db(seed_sample_data=True)

    meters = SmartMeter.get_all()
    print(f"Found {len(meters)} smart meters.")

    for m in meters:
        totals = m.get_total_consumption()
        if totals["reading_count"] < 100:
            print(f"Generating 14-day telemetry series for meter {m.meter_number} ({m.household_name})...")
            SmartMeterSimulator.populate_household_simulation(
                household_id=m.household_id,
                meter_id=m.meter_id,
                days=14,
                anomaly_count=4
            )

    print("Running initial Machine Learning Anomaly Detection pipeline...")
    detector = AnomalyDetector()
    results = detector.run_detection()
    print(f"ML Pipeline Results: {results}")
    print("Database seeding completed successfully.")

if __name__ == "__main__":
    seed_full_demo()
