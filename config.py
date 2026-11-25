"""
EnerTrack Configuration Module
Provides centralized configuration for application settings, paths, and ML parameters.
"""
import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
DATABASE_PATH = os.path.join(INSTANCE_DIR, "enertrack.db")

class Config:
    """Application configuration defaults."""
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DATABASE = DATABASE_PATH
    
    # Default Energy Billing & Currency Settings
    DEFAULT_TARIFF_PER_KWH = float(os.environ.get("TARIFF_PER_KWH", 0.15)) # $0.15 per kWh
    DEFAULT_CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "$")
    
    # Machine Learning Anomaly Detection Settings
    DEFAULT_IFOREST_CONTAMINATION = float(os.environ.get("IFOREST_CONTAMINATION", 0.05)) # 5% expected anomaly rate
    DEFAULT_KMEANS_CLUSTERS = int(os.environ.get("KMEANS_CLUSTERS", 4)) # 4 usage clusters (baseload, morning, day, peak)
    DEFAULT_ZSCORE_THRESHOLD = float(os.environ.get("ZSCORE_THRESHOLD", 2.5)) # standard deviations
    
    # Session Configuration
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours
