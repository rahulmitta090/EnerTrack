"""
EnerTrack User and Configuration Models
Defines object-oriented abstractions for user management, role authorization, and application settings.
"""
from werkzeug.security import generate_password_hash, check_password_hash
from database import db_session

class User:
    """Represents a system user (Admin or Household Owner)."""
    
    def __init__(self, user_id, username, email, password_hash, role, full_name=None, created_at=None):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.role = role  # 'admin' or 'user'
        self.full_name = full_name or username
        self.created_at = created_at

    def check_password(self, password):
        """Verifies candidate plaintext password against stored hash."""
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """Returns True if the user has administrative privileges."""
        return self.role == 'admin'

    def to_dict(self):
        """Serializes user attributes to dictionary (excluding sensitive password hash)."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "full_name": self.full_name,
            "created_at": str(self.created_at)
        }

    @classmethod
    def from_row(cls, row):
        """Instantiates User object from database Row."""
        if not row:
            return None
        return cls(
            user_id=row["user_id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            role=row["role"],
            full_name=row["full_name"],
            created_at=row["created_at"]
        )

    @classmethod
    def get_by_id(cls, user_id):
        """Fetches user by primary key."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?;", (user_id,))
            return cls.from_row(cursor.fetchone())

    @classmethod
    def get_by_username(cls, username):
        """Fetches user by unique username."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?);", (username.strip(),))
            return cls.from_row(cursor.fetchone())

    @classmethod
    def get_by_email(cls, email):
        """Fetches user by email address."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?);", (email.strip(),))
            return cls.from_row(cursor.fetchone())

    @classmethod
    def create(cls, username, email, password, role="user", full_name=None):
        """Registers a new user with securely hashed credentials."""
        password_hash = generate_password_hash(password)
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, role, full_name)
                VALUES (?, ?, ?, ?, ?);
            """, (username.strip(), email.strip().lower(), password_hash, role, full_name or username))
            new_id = cursor.lastrowid
        return cls.get_by_id(new_id)

    @classmethod
    def get_all(cls):
        """Returns all registered users."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY created_at DESC;")
            return [cls.from_row(r) for r in cursor.fetchall()]


class AppConfig:
    """Manages application-wide persistent configuration (tariffs, ML thresholds)."""
    
    @staticmethod
    def get(key, default=None):
        """Retrieves config value by key string."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_config WHERE key = ?;", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    @staticmethod
    def set(key, value):
        """Sets or updates a config key-value pair."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO app_config (key, value, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
            """, (key, str(value)))

    @staticmethod
    def get_all():
        """Returns all configuration key-values as a dictionary."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM app_config;")
            return {r["key"]: r["value"] for r in cursor.fetchall()}

    @classmethod
    def get_tariff(cls):
        """Returns the configured tariff per kWh as a float."""
        try:
            return float(cls.get("tariff_per_kwh", 0.15))
        except (ValueError, TypeError):
            return 0.15

    @classmethod
    def get_currency_symbol(cls):
        """Returns the configured currency symbol."""
        return cls.get("currency_symbol", "$")

    @classmethod
    def get_ml_settings(cls):
        """Returns dictionary of ML parameters."""
        try:
            contamination = float(cls.get("iforest_contamination", 0.05))
        except ValueError:
            contamination = 0.05
            
        try:
            k_clusters = int(cls.get("kmeans_clusters", 4))
        except ValueError:
            k_clusters = 4
            
        try:
            z_threshold = float(cls.get("zscore_threshold", 2.5))
        except ValueError:
            z_threshold = 2.5

        return {
            "iforest_contamination": contamination,
            "kmeans_clusters": k_clusters,
            "zscore_threshold": z_threshold
        }
