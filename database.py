"""
EnerTrack Database Module
Handles SQLite connection pooling, schema initialization, constraints, and data integrity.
"""
import sqlite3
import os
from contextlib import contextmanager
from werkzeug.security import generate_password_hash
from config import Config, INSTANCE_DIR, DATABASE_PATH

os.makedirs(INSTANCE_DIR, exist_ok=True)

def get_db_connection():
    """Returns a SQLite connection configured with Row factory and foreign keys."""
    conn = sqlite3.connect(DATABASE_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

@contextmanager
def db_session():
    """Context manager for safe database transactions with auto-commit and rollback."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db(seed_sample_data=True):
    """
    Initializes the database schema if tables do not exist.
    Preserves existing data and seeds essential defaults.
    """
    with db_session() as conn:
        cursor = conn.cursor()
        
        # 1. Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. Households Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS households (
                household_id INTEGER PRIMARY KEY AUTOINCREMENT,
                household_name TEXT NOT NULL,
                address TEXT NOT NULL,
                city TEXT NOT NULL,
                household_type TEXT NOT NULL,
                number_of_members INTEGER NOT NULL DEFAULT 1 CHECK(number_of_members > 0),
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
        """)
        
        # 3. Smart Meters Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS smart_meters (
                meter_id INTEGER PRIMARY KEY AUTOINCREMENT,
                household_id INTEGER NOT NULL,
                meter_number TEXT UNIQUE NOT NULL,
                meter_type TEXT NOT NULL DEFAULT 'Smart Digital',
                installation_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active', 'Inactive', 'Maintenance')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (household_id) REFERENCES households(household_id) ON DELETE CASCADE
            );
        """)
        
        # 4. Consumption Records Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS consumption_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                meter_id INTEGER NOT NULL,
                household_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                energy_kwh REAL NOT NULL CHECK(energy_kwh >= 0),
                voltage REAL,
                current REAL,
                data_source TEXT NOT NULL DEFAULT 'simulated' CHECK(data_source IN ('simulated', 'imported_csv', 'manual_entry')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (meter_id) REFERENCES smart_meters(meter_id) ON DELETE CASCADE,
                FOREIGN KEY (household_id) REFERENCES households(household_id) ON DELETE CASCADE
            );
        """)
        
        # 5. Anomaly Records Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS anomaly_records (
                anomaly_id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                meter_id INTEGER NOT NULL,
                household_id INTEGER NOT NULL,
                detection_timestamp TEXT NOT NULL,
                energy_kwh REAL NOT NULL,
                expected_kwh REAL NOT NULL,
                diff_kwh REAL NOT NULL,
                pct_increase REAL,
                anomaly_score REAL NOT NULL,
                method TEXT NOT NULL,
                severity TEXT NOT NULL CHECK(severity IN ('Normal', 'Unusual', 'High Priority')),
                status TEXT NOT NULL DEFAULT 'New' CHECK(status IN ('New', 'Under Investigation', 'Resolved', 'False Positive')),
                notes TEXT,
                possible_causes TEXT,
                recommendations TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (record_id) REFERENCES consumption_records(record_id) ON DELETE CASCADE,
                FOREIGN KEY (meter_id) REFERENCES smart_meters(meter_id) ON DELETE CASCADE,
                FOREIGN KEY (household_id) REFERENCES households(household_id) ON DELETE CASCADE
            );
        """)
        
        # 6. Application Configuration Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Indexes for query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_consumption_time ON consumption_records(household_id, timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_consumption_meter ON consumption_records(meter_id, timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_status ON anomaly_records(household_id, status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_severity ON anomaly_records(severity);")
        
        # Initialize default config keys if missing
        default_configs = [
            ("tariff_per_kwh", str(Config.DEFAULT_TARIFF_PER_KWH)),
            ("currency_symbol", Config.DEFAULT_CURRENCY_SYMBOL),
            ("iforest_contamination", str(Config.DEFAULT_IFOREST_CONTAMINATION)),
            ("kmeans_clusters", str(Config.DEFAULT_KMEANS_CLUSTERS)),
            ("zscore_threshold", str(Config.DEFAULT_ZSCORE_THRESHOLD))
        ]
        for key, val in default_configs:
            cursor.execute("INSERT OR IGNORE INTO app_config (key, value) VALUES (?, ?);", (key, val))
            
        # Seed default Admin and User if not already present
        cursor.execute("SELECT user_id FROM users WHERE username = 'admin';")
        admin_row = cursor.fetchone()
        if not admin_row:
            admin_pwd = generate_password_hash("Admin@123")
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, role, full_name)
                VALUES ('admin', 'admin@enertrack.io', ?, 'admin', 'System Administrator');
            """, (admin_pwd,))
            
        cursor.execute("SELECT user_id FROM users WHERE username = 'sarah_home';")
        user_row = cursor.fetchone()
        if not user_row:
            user_pwd = generate_password_hash("User@123")
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, role, full_name)
                VALUES ('sarah_home', 'sarah.miller@example.com', ?, 'user', 'Sarah Miller');
            """, (user_pwd,))
            
    # Optionally seed initial households and smart meters if the database is brand new
    if seed_sample_data:
        _seed_initial_data()

def _seed_initial_data():
    """Seeds initial demonstration households and meters if table is empty."""
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM households;")
        if cursor.fetchone()["count"] == 0:
            cursor.execute("SELECT user_id FROM users WHERE username = 'sarah_home';")
            sarah = cursor.fetchone()
            sarah_id = sarah["user_id"] if sarah else 2
            
            cursor.execute("SELECT user_id FROM users WHERE username = 'admin';")
            admin = cursor.fetchone()
            admin_id = admin["user_id"] if admin else 1

            # Seed households
            households_data = [
                ("Oakwood Residence", "742 Evergreen Terrace", "Springfield", "Detached House", 4, sarah_id),
                ("Skyline Heights 12B", "100 Grand Avenue, Apt 12B", "Metropolis", "Apartment", 2, sarah_id),
                ("Meadowbrook Villa", "15 Meadowbrook Way", "Riverdale", "Villa", 5, admin_id)
            ]
            
            for name, addr, city, htype, members, uid in households_data:
                cursor.execute("""
                    INSERT INTO households (household_name, address, city, household_type, number_of_members, user_id)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (name, addr, city, htype, members, uid))
                
            # Seed smart meters
            cursor.execute("SELECT household_id, household_name FROM households;")
            h_rows = cursor.fetchall()
            
            meter_data = [
                (h_rows[0]["household_id"], "SM-2026-OAK01", "Smart Digital Bi-Directional", "2026-01-15", "Active"),
                (h_rows[1]["household_id"], "SM-2026-SKY02", "Single-Phase Precision Meter", "2026-02-01", "Active"),
                (h_rows[2]["household_id"], "SM-2026-MDW03", "Three-Phase Smart Meter", "2026-01-20", "Active")
            ]
            
            for hid, mnum, mtype, inst_date, status in meter_data:
                cursor.execute("""
                    INSERT INTO smart_meters (household_id, meter_number, meter_type, installation_date, status)
                    VALUES (?, ?, ?, ?, ?);
                """, (hid, mnum, mtype, inst_date, status))

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
