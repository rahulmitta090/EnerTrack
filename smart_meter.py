"""
EnerTrack Smart Meter Management Module
Object-Oriented abstraction for smart electricity meters, hardware metadata, and telemetry status.
"""
from database import db_session

class SmartMeter:
    """Represents a physical or simulated smart electricity meter device."""
    
    def __init__(self, meter_id, household_id, meter_number, meter_type, 
                 installation_date, status="Active", created_at=None, household_name=None):
        self.meter_id = meter_id
        self.household_id = household_id
        self.meter_number = meter_number
        self.meter_type = meter_type
        self.installation_date = installation_date
        self.status = status  # 'Active', 'Inactive', 'Maintenance'
        self.created_at = created_at
        self.household_name = household_name

    def to_dict(self):
        """Serializes smart meter object to dictionary."""
        return {
            "meter_id": self.meter_id,
            "household_id": self.household_id,
            "household_name": self.household_name,
            "meter_number": self.meter_number,
            "meter_type": self.meter_type,
            "installation_date": str(self.installation_date),
            "status": self.status,
            "created_at": str(self.created_at) if self.created_at else None
        }

    @classmethod
    def from_row(cls, row):
        """Constructs a SmartMeter instance from a database row."""
        if not row:
            return None
        h_name = row["household_name"] if "household_name" in row.keys() else None
        return cls(
            meter_id=row["meter_id"],
            household_id=row["household_id"],
            meter_number=row["meter_number"],
            meter_type=row["meter_type"],
            installation_date=row["installation_date"],
            status=row["status"],
            created_at=row["created_at"],
            household_name=h_name
        )

    @classmethod
    def register(cls, household_id, meter_number, meter_type="Smart Digital", 
                 installation_date=None, status="Active"):
        """Registers a new smart meter linked to a household."""
        import datetime
        inst_date = installation_date or datetime.date.today().isoformat()
        
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO smart_meters (household_id, meter_number, meter_type, installation_date, status)
                VALUES (?, ?, ?, ?, ?);
            """, (household_id, meter_number.strip().upper(), meter_type.strip(), inst_date, status))
            new_id = cursor.lastrowid
        return cls.get_by_id(new_id)

    @classmethod
    def get_by_id(cls, meter_id):
        """Retrieves smart meter by ID with household context."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.*, h.household_name
                FROM smart_meters m
                JOIN households h ON m.household_id = h.household_id
                WHERE m.meter_id = ?;
            """, (meter_id,))
            return cls.from_row(cursor.fetchone())

    @classmethod
    def get_by_household(cls, household_id):
        """Retrieves all smart meters linked to a given household."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.*, h.household_name
                FROM smart_meters m
                JOIN households h ON m.household_id = h.household_id
                WHERE m.household_id = ?
                ORDER BY m.meter_number ASC;
            """, (household_id,))
            return [cls.from_row(r) for r in cursor.fetchall()]

    @classmethod
    def get_by_meter_number(cls, meter_number):
        """Retrieves meter by unique serial code."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.*, h.household_name
                FROM smart_meters m
                JOIN households h ON m.household_id = h.household_id
                WHERE UPPER(m.meter_number) = UPPER(?);
            """, (meter_number.strip(),))
            return cls.from_row(cursor.fetchone())

    @classmethod
    def get_all(cls):
        """Retrieves all meters across the system."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.*, h.household_name, h.user_id
                FROM smart_meters m
                JOIN households h ON m.household_id = h.household_id
                ORDER BY m.created_at DESC;
            """)
            return [cls.from_row(r) for r in cursor.fetchall()]

    def update(self, meter_type, status):
        """Updates meter configuration and active operational status."""
        if status not in ('Active', 'Inactive', 'Maintenance'):
            raise ValueError("Status must be Active, Inactive, or Maintenance.")
            
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE smart_meters
                SET meter_type = ?, status = ?
                WHERE meter_id = ?;
            """, (meter_type.strip(), status, self.meter_id))
            
        self.meter_type = meter_type
        self.status = status
        return True

    def toggle_status(self):
        """Toggles between Active and Inactive state."""
        new_status = "Inactive" if self.status == "Active" else "Active"
        return self.update(self.meter_type, new_status)

    def get_recent_readings(self, limit=50):
        """Returns the most recent readings recorded by this meter."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM consumption_records
                WHERE meter_id = ?
                ORDER BY timestamp DESC
                LIMIT ?;
            """, (self.meter_id, limit))
            return [dict(r) for r in cursor.fetchall()]

    def get_total_consumption(self):
        """Calculates total lifetime consumption recorded by this meter."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(SUM(energy_kwh), 0.0) as total_kwh, COUNT(*) as reading_count
                FROM consumption_records
                WHERE meter_id = ?;
            """, (self.meter_id,))
            return dict(cursor.fetchone())
