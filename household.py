"""
EnerTrack Household Management Module
Object-Oriented abstraction for household profiles, occupancy data, and meter relationships.
"""
from database import db_session

class Household:
    """Represents a residential or commercial consumer entity."""
    
    def __init__(self, household_id, household_name, address, city, household_type, 
                 number_of_members, user_id, created_at=None, owner_name=None):
        self.household_id = household_id
        self.household_name = household_name
        self.address = address
        self.city = city
        self.household_type = household_type
        self.number_of_members = int(number_of_members) if number_of_members else 1
        self.user_id = user_id
        self.created_at = created_at
        self.owner_name = owner_name

    def to_dict(self):
        """Serializes household to dictionary."""
        return {
            "household_id": self.household_id,
            "household_name": self.household_name,
            "address": self.address,
            "city": self.city,
            "household_type": self.household_type,
            "number_of_members": self.number_of_members,
            "user_id": self.user_id,
            "owner_name": self.owner_name,
            "created_at": str(self.created_at) if self.created_at else None
        }

    @classmethod
    def from_row(cls, row):
        """Constructs a Household instance from a database row."""
        if not row:
            return None
        owner = row["full_name"] if "full_name" in row.keys() else None
        return cls(
            household_id=row["household_id"],
            household_name=row["household_name"],
            address=row["address"],
            city=row["city"],
            household_type=row["household_type"],
            number_of_members=row["number_of_members"],
            user_id=row["user_id"],
            created_at=row["created_at"],
            owner_name=owner
        )

    def can_access(self, user):
        """Verifies if the given user has permission to read or modify this household."""
        if not user:
            return False
        return user.is_admin() or (self.user_id == user.user_id)

    @classmethod
    def create(cls, household_name, address, city, household_type, number_of_members, user_id):
        """Creates and saves a new household record in SQLite."""
        if not household_name or not address or not city:
            raise ValueError("Household name, address, and city are mandatory.")
        try:
            members = int(number_of_members)
            if members <= 0:
                raise ValueError("Number of members must be greater than zero.")
        except (ValueError, TypeError):
            raise ValueError("Invalid number of household members.")

        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO households (household_name, address, city, household_type, number_of_members, user_id)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (household_name.strip(), address.strip(), city.strip(), household_type.strip(), members, user_id))
            new_id = cursor.lastrowid
        return cls.get_by_id(new_id)

    @classmethod
    def get_by_id(cls, household_id):
        """Fetches household by ID with owner information."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT h.*, u.full_name, u.username 
                FROM households h
                LEFT JOIN users u ON h.user_id = u.user_id
                WHERE h.household_id = ?;
            """, (household_id,))
            return cls.from_row(cursor.fetchone())

    @classmethod
    def get_by_user(cls, user_id):
        """Retrieves all households associated with a specific user."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT h.*, u.full_name, u.username
                FROM households h
                LEFT JOIN users u ON h.user_id = u.user_id
                WHERE h.user_id = ?
                ORDER BY h.household_name ASC;
            """, (user_id,))
            return [cls.from_row(r) for r in cursor.fetchall()]

    @classmethod
    def get_all(cls):
        """Retrieves all households in the system (for admin view)."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT h.*, u.full_name, u.username
                FROM households h
                LEFT JOIN users u ON h.user_id = u.user_id
                ORDER BY h.created_at DESC;
            """, (cls,)) if False else cursor.execute("""
                SELECT h.*, u.full_name, u.username
                FROM households h
                LEFT JOIN users u ON h.user_id = u.user_id
                ORDER BY h.created_at DESC;
            """)
            return [cls.from_row(r) for r in cursor.fetchall()]

    def update(self, household_name, address, city, household_type, number_of_members):
        """Updates household attributes in the database."""
        members = int(number_of_members)
        if members <= 0:
            raise ValueError("Members count must be at least 1.")
            
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE households 
                SET household_name = ?, address = ?, city = ?, household_type = ?, number_of_members = ?
                WHERE household_id = ?;
            """, (household_name.strip(), address.strip(), city.strip(), household_type.strip(), members, self.household_id))
            
        self.household_name = household_name
        self.address = address
        self.city = city
        self.household_type = household_type
        self.number_of_members = members
        return True

    def delete(self):
        """Deletes this household and cascaded smart meters/records."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM households WHERE household_id = ?;", (self.household_id,))
            return True

    def get_meters(self):
        """Returns list of smart meter dicts attached to this household."""
        from smart_meter import SmartMeter
        return SmartMeter.get_by_household(self.household_id)

    def get_consumption_summary(self):
        """Computes aggregate energy analytics for this household."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_readings,
                    COALESCE(SUM(energy_kwh), 0.0) as total_kwh,
                    COALESCE(AVG(energy_kwh), 0.0) as avg_kwh,
                    COALESCE(MAX(energy_kwh), 0.0) as peak_kwh,
                    MIN(timestamp) as earliest_reading,
                    MAX(timestamp) as latest_reading
                FROM consumption_records 
                WHERE household_id = ?;
            """, (self.household_id,))
            summary = dict(cursor.fetchone())
            
            # Count anomalies
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_anomalies,
                    SUM(CASE WHEN severity = 'High Priority' THEN 1 ELSE 0 END) as high_priority_count,
                    SUM(CASE WHEN status IN ('New', 'Under Investigation') THEN 1 ELSE 0 END) as active_anomalies
                FROM anomaly_records
                WHERE household_id = ?;
            """, (self.household_id,))
            anom_summary = dict(cursor.fetchone())
            summary.update(anom_summary)
            
            return summary
