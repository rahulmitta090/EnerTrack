"""
EnerTrack Energy Consumption Module
Object-Oriented abstraction for smart-meter telemetry records, validation, CSV parsing, and aggregations.
"""
from datetime import datetime
from database import db_session

class ConsumptionRecord:
    """Represents a discrete energy consumption measurement recorded by a smart meter."""
    
    def __init__(self, record_id, meter_id, household_id, timestamp, energy_kwh, 
                 voltage=230.0, current=None, data_source="simulated", created_at=None,
                 household_name=None, meter_number=None):
        self.record_id = record_id
        self.meter_id = meter_id
        self.household_id = household_id
        self.timestamp = timestamp
        self.energy_kwh = float(energy_kwh)
        self.voltage = float(voltage) if voltage is not None else 230.0
        # Calculate approximate current if not provided: I = P / V
        if current is not None:
            self.current = float(current)
        else:
            self.current = round((self.energy_kwh * 1000.0) / (self.voltage * 0.9), 2) if self.voltage > 0 else 0.0
        self.data_source = data_source  # 'simulated', 'imported_csv', 'manual_entry'
        self.created_at = created_at
        self.household_name = household_name
        self.meter_number = meter_number

    def to_dict(self):
        """Serializes consumption record to dictionary format."""
        return {
            "record_id": self.record_id,
            "meter_id": self.meter_id,
            "meter_number": self.meter_number,
            "household_id": self.household_id,
            "household_name": self.household_name,
            "timestamp": str(self.timestamp),
            "energy_kwh": round(self.energy_kwh, 4),
            "voltage": round(self.voltage, 1) if self.voltage else 230.0,
            "current": round(self.current, 2) if self.current else 0.0,
            "data_source": self.data_source,
            "created_at": str(self.created_at) if self.created_at else None
        }

    @staticmethod
    def validate_reading(energy_kwh, timestamp_str):
        """
        Validates energy consumption values and timestamp syntax.
        Raises ValueError if invalid.
        """
        try:
            val = float(energy_kwh)
        except (ValueError, TypeError):
            raise ValueError(f"Energy reading must be a valid number, received: '{energy_kwh}'")
            
        if val < 0.0:
            raise ValueError(f"Negative energy consumption ({val} kWh) is invalid. Electricity usage cannot be negative.")
            
        if val > 100.0:
            # Physical sanity check for single household hourly reading
            raise ValueError(f"Reading {val} kWh exceeds physically plausible residential hourly threshold (100 kWh).")

        # Validate timestamp syntax
        cleaned_ts = timestamp_str.strip().replace("T", " ")
        valid_formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d"
        ]
        parsed = None
        for fmt in valid_formats:
            try:
                parsed = datetime.strptime(cleaned_ts, fmt)
                break
            except ValueError:
                continue
                
        if parsed is None:
            raise ValueError(f"Timestamp '{timestamp_str}' does not match standard format (YYYY-MM-DD HH:MM:SS).")
            
        return val, parsed.strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def from_row(cls, row):
        """Instantiates ConsumptionRecord from database Row."""
        if not row:
            return None
        keys = row.keys()
        h_name = row["household_name"] if "household_name" in keys else None
        m_num = row["meter_number"] if "meter_number" in keys else None
        return cls(
            record_id=row["record_id"],
            meter_id=row["meter_id"],
            household_id=row["household_id"],
            timestamp=row["timestamp"],
            energy_kwh=row["energy_kwh"],
            voltage=row["voltage"],
            current=row["current"],
            data_source=row["data_source"],
            created_at=row["created_at"],
            household_name=h_name,
            meter_number=m_num
        )

    @classmethod
    def add_record(cls, meter_id, household_id, timestamp, energy_kwh, 
                   voltage=230.0, current=None, data_source="manual_entry"):
        """Validates and persists a single energy consumption record."""
        validated_kwh, validated_ts = cls.validate_reading(energy_kwh, str(timestamp))
        
        v = float(voltage) if voltage is not None else 230.0
        c = float(current) if current is not None else round((validated_kwh * 1000.0) / (v * 0.9), 2)
        
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO consumption_records (meter_id, household_id, timestamp, energy_kwh, voltage, current, data_source)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (meter_id, household_id, validated_ts, validated_kwh, v, c, data_source))
            new_id = cursor.lastrowid
            
            cursor.execute("""
                SELECT c.*, h.household_name, m.meter_number
                FROM consumption_records c
                JOIN households h ON c.household_id = h.household_id
                JOIN smart_meters m ON c.meter_id = m.meter_id
                WHERE c.record_id = ?;
            """, (new_id,))
            return cls.from_row(cursor.fetchone())

    @classmethod
    def add_batch(cls, records_data):
        """
        Inserts a batch of records inside a single transaction for high performance.
        records_data: list of tuples (meter_id, household_id, timestamp, energy_kwh, voltage, current, data_source)
        """
        inserted_count = 0
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT INTO consumption_records (meter_id, household_id, timestamp, energy_kwh, voltage, current, data_source)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, records_data)
            inserted_count = cursor.rowcount
        return inserted_count

    @classmethod
    def get_records(cls, household_id=None, meter_id=None, start_date=None, 
                    end_date=None, data_source=None, limit=500, offset=0):
        """Queries consumption records with flexible filtering and pagination."""
        query = """
            SELECT c.*, h.household_name, m.meter_number
            FROM consumption_records c
            JOIN households h ON c.household_id = h.household_id
            JOIN smart_meters m ON c.meter_id = m.meter_id
            WHERE 1=1
        """
        params = []
        
        if household_id:
            query += " AND c.household_id = ?"
            params.append(household_id)
            
        if meter_id:
            query += " AND c.meter_id = ?"
            params.append(meter_id)
            
        if start_date:
            query += " AND c.timestamp >= ?"
            params.append(f"{start_date} 00:00:00")
            
        if end_date:
            query += " AND c.timestamp <= ?"
            params.append(f"{end_date} 23:59:59")
            
        if data_source:
            query += " AND c.data_source = ?"
            params.append(data_source)
            
        query += " ORDER BY c.timestamp DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])
        
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [cls.from_row(r) for r in cursor.fetchall()]

    @classmethod
    def get_daily_summary(cls, household_id=None, meter_id=None, days=30):
        """Returns daily aggregated consumption (date, total_kwh, avg_kwh, count) for charting."""
        query = """
            SELECT 
                SUBSTR(timestamp, 1, 10) as date_day,
                ROUND(SUM(energy_kwh), 2) as daily_kwh,
                ROUND(AVG(energy_kwh), 3) as avg_kwh,
                ROUND(MAX(energy_kwh), 2) as max_kwh,
                COUNT(*) as count
            FROM consumption_records
            WHERE 1=1
        """
        params = []
        if household_id:
            query += " AND household_id = ?"
            params.append(household_id)
        if meter_id:
            query += " AND meter_id = ?"
            params.append(meter_id)
            
        query += """
            GROUP BY SUBSTR(timestamp, 1, 10)
            ORDER BY date_day DESC
            LIMIT ?;
        """
        params.append(days)
        
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(r) for r in reversed(rows)] # chronological order

    @classmethod
    def get_hourly_summary(cls, household_id=None):
        """Returns average kWh consumption across the 24 hours of the day."""
        query = """
            SELECT 
                CAST(SUBSTR(timestamp, 12, 2) AS INTEGER) as hour_of_day,
                ROUND(AVG(energy_kwh), 3) as avg_kwh,
                ROUND(MAX(energy_kwh), 3) as max_kwh,
                COUNT(*) as readings_count
            FROM consumption_records
            WHERE 1=1
        """
        params = []
        if household_id:
            query += " AND household_id = ?"
            params.append(household_id)
            
        query += """
            GROUP BY hour_of_day
            ORDER BY hour_of_day ASC;
        """
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]
