"""
EnerTrack Realistic Smart-Meter Data Generator
Generates physics-based simulated household electricity consumption data with diurnal cycles,
household behavioral profiles, weekday/weekend variations, and controlled anomaly spikes.
All records are explicitly tagged with data_source='simulated'.
"""
import random
import math
from datetime import datetime, timedelta
from consumption import ConsumptionRecord
from database import db_session

class SmartMeterSimulator:
    """Simulates realistic hourly smart meter telemetry for households."""

    HOUSEHOLD_PROFILES = {
        "Apartment": {
            "base_load": (0.15, 0.35),
            "morning_multiplier": 1.8,
            "day_multiplier": 0.8,
            "evening_multiplier": 2.5,
            "noise_std": 0.08
        },
        "Detached House": {
            "base_load": (0.30, 0.65),
            "morning_multiplier": 2.4,
            "day_multiplier": 1.1,
            "evening_multiplier": 3.6,
            "noise_std": 0.15
        },
        "Villa": {
            "base_load": (0.60, 1.20),
            "morning_multiplier": 3.0,
            "day_multiplier": 1.5,
            "evening_multiplier": 4.8,
            "noise_std": 0.25
        },
        "Standard": {
            "base_load": (0.25, 0.50),
            "morning_multiplier": 2.0,
            "day_multiplier": 1.0,
            "evening_multiplier": 3.0,
            "noise_std": 0.12
        }
    }

    @classmethod
    def generate_consumption_series(cls, household_id, meter_id, days=14, 
                                    household_type="Detached House", 
                                    members=3, inject_anomalies=True, 
                                    anomaly_count=4):
        """
        Generates hourly simulated readings for a given household over specified days.
        Returns a list of tuples formatted for database bulk insertion.
        """
        profile = cls.HOUSEHOLD_PROFILES.get(household_type, cls.HOUSEHOLD_PROFILES["Standard"])
        base_min, base_max = profile["base_load"]
        member_factor = 1.0 + (max(1, members) - 1) * 0.15
        
        records = []
        end_time = datetime.now().replace(minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(days=days)
        total_hours = days * 24

        # Pre-select random hours to inject anomalies if requested
        anomaly_indices = set()
        if inject_anomalies and anomaly_count > 0:
            # Pick non-adjacent random hours between hour 24 and total_hours - 2
            available_indices = list(range(24, total_hours - 2))
            if available_indices:
                sample_k = min(anomaly_count, len(available_indices))
                anomaly_indices = set(random.sample(available_indices, sample_k))

        for hour_idx in range(total_hours):
            current_ts = start_time + timedelta(hours=hour_idx)
            hour_of_day = current_ts.hour
            is_weekend = current_ts.weekday() >= 5

            # Calculate baseline consumption based on time-of-day diurnal curve
            # 1. Overnight baseload (00:00 - 05:59): minimal standby appliances
            if 0 <= hour_of_day < 6:
                base = random.uniform(base_min, base_max) * 0.75
            # 2. Morning peak (06:00 - 09:59): showers, breakfast, lighting
            elif 6 <= hour_of_day < 10:
                peak_time = 7.5 if not is_weekend else 9.0
                bell_weight = math.exp(-((hour_of_day - peak_time) ** 2) / 2.0)
                base = random.uniform(base_min, base_max) * (1.0 + profile["morning_multiplier"] * bell_weight)
            # 3. Daytime hours (10:00 - 16:59): occupancy depends on weekend
            elif 10 <= hour_of_day < 17:
                day_occupancy = 1.4 if is_weekend else 0.75
                base = random.uniform(base_min, base_max) * profile["day_multiplier"] * day_occupancy
            # 4. Evening peak (17:00 - 22:59): cooking, HVAC, lighting, entertainment
            elif 17 <= hour_of_day < 23:
                peak_time = 19.5
                bell_weight = math.exp(-((hour_of_day - peak_time) ** 2) / 3.0)
                base = random.uniform(base_min, base_max) * (1.2 + profile["evening_multiplier"] * bell_weight)
            # 5. Late night (23:00): winding down
            else:
                base = random.uniform(base_min, base_max) * 1.1

            # Add stochastic Gaussian noise
            noise = random.gauss(0, profile["noise_std"])
            energy_kwh = max(0.08, (base + noise) * member_factor)

            # Simulated voltage with standard European/International 230V grid fluctuations
            voltage = round(random.gauss(230.5, 3.2), 1)

            # Inject controlled realistic anomaly if this index was picked
            if hour_idx in anomaly_indices:
                anomaly_type = random.choice([
                    "midnight_spike",       # high-draw equipment run in dead of night
                    "faulty_appliance",     # continuous heavy compressor draw
                    "extreme_evening_surge" # uncharacteristic peak > 3x normal
                ])
                if anomaly_type == "midnight_spike" and hour_of_day < 6:
                    energy_kwh = round(energy_kwh + random.uniform(4.5, 8.2), 3)
                elif anomaly_type == "faulty_appliance":
                    energy_kwh = round(energy_kwh + random.uniform(3.8, 6.5), 3)
                else:
                    energy_kwh = round(energy_kwh * random.uniform(3.0, 4.5), 3)

            energy_kwh = round(energy_kwh, 4)
            # Calculated power factor ~0.90 -> Current I = (kWh * 1000) / (V * PF)
            current_amps = round((energy_kwh * 1000.0) / (voltage * 0.90), 2)
            ts_str = current_ts.strftime("%Y-%m-%d %H:%M:%S")

            records.append((
                meter_id,
                household_id,
                ts_str,
                energy_kwh,
                voltage,
                current_amps,
                "simulated" # Explicitly labeled as simulated
            ))

        return records

    @classmethod
    def populate_household_simulation(cls, household_id, meter_id, days=14, anomaly_count=4):
        """Generates and writes simulated dataset directly into database."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT household_type, number_of_members FROM households WHERE household_id = ?;", (household_id,))
            h_info = cursor.fetchone()
            
        htype = h_info["household_type"] if h_info else "Standard"
        members = h_info["number_of_members"] if h_info else 3

        batch_data = cls.generate_consumption_series(
            household_id=household_id,
            meter_id=meter_id,
            days=days,
            household_type=htype,
            members=members,
            inject_anomalies=True,
            anomaly_count=anomaly_count
        )

        return ConsumptionRecord.add_batch(batch_data)
