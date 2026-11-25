"""
EnerTrack Machine Learning Anomaly Detection Module
Combines K-Means Clustering, Isolation Forest, and Dynamic Statistical Baselines
to identify, score, classify, and explain abnormal household electricity consumption.

Features a dual-engine architecture:
- Scikit-learn (KMeans, IsolationForest, StandardScaler) when native C extensions are permitted.
- High-Performance Native NumPy/SciPy Isolation Forest & K-Means Engine when operating in
  restricted enterprise environments where Windows Defender Application Control (WDAC) blocks .pyd DLLs.
"""
import json
import math
import numpy as np
import pandas as pd
from datetime import datetime
from database import db_session
from models import AppConfig

# Attempt to load Scikit-learn, falling back to Native Engine if DLL load is blocked by OS policy
SKLEARN_ENABLED = False
try:
    from sklearn.cluster import KMeans as SklearnKMeans
    from sklearn.ensemble import IsolationForest as SklearnIsolationForest
    from sklearn.preprocessing import StandardScaler as SklearnStandardScaler
    
    # Quick probe to confirm OS hasn't blocked C extension DLLs
    _probe_km = SklearnKMeans(n_clusters=2, n_init='auto', random_state=42)
    _probe_km.fit([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    _probe_if = SklearnIsolationForest(n_estimators=10, random_state=42)
    _probe_if.fit([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    SKLEARN_ENABLED = True
except Exception:
    SKLEARN_ENABLED = False


# =====================================================================
# Native NumPy Machine Learning Implementations (Resilient Fallback)
# =====================================================================

class NativeStandardScaler:
    """Standardizes features by removing the mean and scaling to unit variance."""
    def __init__(self):
        self.mean_ = None
        self.scale_ = None

    def fit(self, X):
        X = np.asarray(X, dtype=float)
        self.mean_ = np.mean(X, axis=0)
        self.scale_ = np.std(X, axis=0)
        self.scale_[self.scale_ == 0.0] = 1.0
        return self

    def transform(self, X):
        X = np.asarray(X, dtype=float)
        return (X - self.mean_) / self.scale_

    def fit_transform(self, X):
        return self.fit(X).transform(X)


class NativeKMeans:
    """K-Means clustering algorithm implemented in vectorized NumPy."""
    def __init__(self, n_clusters=4, max_iter=100, random_state=42):
        self.n_clusters = n_clusters
        self.max_iter = max_iter
        self.random_state = random_state
        self.cluster_centers_ = None

    def fit_predict(self, X):
        X = np.asarray(X, dtype=float)
        n_samples, n_features = X.shape
        k = min(self.n_clusters, n_samples)
        
        np.random.seed(self.random_state)
        # K-Means++ style initial centroid selection
        centroids = [X[np.random.randint(n_samples)]]
        for _ in range(1, k):
            dists = np.min([np.sum((X - c) ** 2, axis=1) for c in centroids], axis=0)
            probs = dists / (np.sum(dists) + 1e-9)
            next_idx = np.random.choice(n_samples, p=probs)
            centroids.append(X[next_idx])
            
        centroids = np.array(centroids)
        labels = np.zeros(n_samples, dtype=int)

        for _ in range(self.max_iter):
            # Compute distance to each centroid
            # dists: shape (n_samples, k)
            dists = np.linalg.norm(X[:, np.newaxis] - centroids, axis=2)
            new_labels = np.argmin(dists, axis=1)

            if np.array_equal(labels, new_labels):
                break
            labels = new_labels

            # Update centroids
            for j in range(k):
                pts = X[labels == j]
                if len(pts) > 0:
                    centroids[j] = np.mean(pts, axis=0)

        self.cluster_centers_ = centroids
        return labels


class _IsolationTreeNode:
    """Node in an Isolation Tree."""
    def __init__(self, depth=0, max_depth=10):
        self.depth = depth
        self.max_depth = max_depth
        self.left = None
        self.right = None
        self.split_feature = None
        self.split_value = None
        self.size = 0

    def fit(self, X):
        self.size = len(X)
        if self.depth >= self.max_depth or self.size <= 1:
            return self

        n_features = X.shape[1]
        self.split_feature = np.random.randint(0, n_features)
        col = X[:, self.split_feature]
        min_v, max_v = np.min(col), np.max(col)

        if min_v == max_v:
            return self

        self.split_value = np.random.uniform(min_v, max_v)
        left_mask = col < self.split_value
        right_mask = ~left_mask

        if np.sum(left_mask) == 0 or np.sum(right_mask) == 0:
            return self

        self.left = _IsolationTreeNode(self.depth + 1, self.max_depth).fit(X[left_mask])
        self.right = _IsolationTreeNode(self.depth + 1, self.max_depth).fit(X[right_mask])
        return self

    def path_length(self, x):
        """Recursively computes isolation path length for a single instance."""
        if self.left is None or self.right is None:
            # Average path length adjustment for terminal node of size n
            if self.size <= 1:
                return self.depth
            return self.depth + (2.0 * (np.log(self.size - 1) + 0.5772156649) - (2.0 * (self.size - 1) / self.size))

        if x[self.split_feature] < self.split_value:
            return self.left.path_length(x)
        else:
            return self.right.path_length(x)


class NativeIsolationForest:
    """
    Isolation Forest implementation based on Liu, Ting & Zhou (2008).
    Isolates anomalies by randomly sub-sampling and partitioning features.
    """
    def __init__(self, n_estimators=100, contamination=0.05, max_samples=256, random_state=42):
        self.n_estimators = n_estimators
        self.contamination = contamination
        self.max_samples = max_samples
        self.random_state = random_state
        self.trees = []
        self.threshold_ = 0.5

    @staticmethod
    def _c(n):
        """Average path length of unsuccessful search in BST."""
        if n <= 1:
            return 1.0
        return 2.0 * (np.log(n - 1) + 0.5772156649) - (2.0 * (n - 1) / n)

    def fit(self, X):
        X = np.asarray(X, dtype=float)
        n_samples = len(X)
        np.random.seed(self.random_state)

        sub_sample_size = min(self.max_samples, n_samples)
        max_depth = int(np.ceil(np.log2(max(2, sub_sample_size))))

        self.trees = []
        for _ in range(self.n_estimators):
            sample_indices = np.random.choice(n_samples, sub_sample_size, replace=False)
            tree = _IsolationTreeNode(depth=0, max_depth=max_depth)
            tree.fit(X[sample_indices])
            self.trees.append(tree)

        scores = self.decision_function(X)
        self.threshold_ = np.percentile(scores, 100.0 * self.contamination)
        return self

    def decision_function(self, X):
        """Returns anomaly score: lower values indicate higher likelihood of anomaly."""
        X = np.asarray(X, dtype=float)
        n_samples = len(X)
        sub_sample_size = min(self.max_samples, n_samples)
        c_factor = self._c(sub_sample_size)

        # Average path length across all isolation trees
        path_lengths = np.zeros(n_samples)
        for tree in self.trees:
            for i in range(n_samples):
                path_lengths[i] += tree.path_length(X[i])
        path_lengths /= len(self.trees)

        # Score s = 2^(-E(h)/c)
        scores = 2.0 ** (-path_lengths / c_factor)
        # Decision function: 0.5 - score, so lower = more anomalous
        return 0.5 - scores

    def fit_predict(self, X):
        """Predicts -1 for outliers and 1 for inliers."""
        self.fit(X)
        scores = self.decision_function(X)
        preds = np.where(scores <= self.threshold_, -1, 1)
        return preds


# =====================================================================
# Domain OOP Classes: AnomalyRecord & AnomalyDetector
# =====================================================================

class AnomalyRecord:
    """Object-Oriented representation of an identified energy anomaly event."""
    
    def __init__(self, anomaly_id, record_id, meter_id, household_id, detection_timestamp,
                 energy_kwh, expected_kwh, diff_kwh, pct_increase, anomaly_score,
                 method, severity, status="New", notes=None, possible_causes=None, 
                 recommendations=None, created_at=None, household_name=None, meter_number=None):
        self.anomaly_id = anomaly_id
        self.record_id = record_id
        self.meter_id = meter_id
        self.household_id = household_id
        self.detection_timestamp = detection_timestamp
        self.energy_kwh = float(energy_kwh)
        self.expected_kwh = float(expected_kwh)
        self.diff_kwh = float(diff_kwh)
        self.pct_increase = float(pct_increase) if pct_increase is not None else 0.0
        self.anomaly_score = float(anomaly_score)
        self.method = method
        self.severity = severity  # 'Normal', 'Unusual', 'High Priority'
        self.status = status      # 'New', 'Under Investigation', 'Resolved', 'False Positive'
        self.notes = notes or ""
        
        # Parse JSON lists if stored as string
        if isinstance(possible_causes, str):
            try:
                self.possible_causes = json.loads(possible_causes)
            except Exception:
                self.possible_causes = [possible_causes]
        else:
            self.possible_causes = possible_causes or []
            
        if isinstance(recommendations, str):
            try:
                self.recommendations = json.loads(recommendations)
            except Exception:
                self.recommendations = [recommendations]
        else:
            self.recommendations = recommendations or []
            
        self.created_at = created_at
        self.household_name = household_name
        self.meter_number = meter_number

    def to_dict(self):
        """Serializes anomaly record to dictionary."""
        return {
            "anomaly_id": self.anomaly_id,
            "record_id": self.record_id,
            "meter_id": self.meter_id,
            "meter_number": self.meter_number,
            "household_id": self.household_id,
            "household_name": self.household_name,
            "detection_timestamp": str(self.detection_timestamp),
            "energy_kwh": round(self.energy_kwh, 3),
            "expected_kwh": round(self.expected_kwh, 3),
            "diff_kwh": round(self.diff_kwh, 3),
            "pct_increase": round(self.pct_increase, 1),
            "anomaly_score": round(self.anomaly_score, 3),
            "method": self.method,
            "severity": self.severity,
            "status": self.status,
            "notes": self.notes,
            "possible_causes": self.possible_causes,
            "recommendations": self.recommendations,
            "created_at": str(self.created_at) if self.created_at else None
        }

    @classmethod
    def from_row(cls, row):
        """Builds AnomalyRecord from database Row."""
        if not row:
            return None
        keys = row.keys()
        h_name = row["household_name"] if "household_name" in keys else None
        m_num = row["meter_number"] if "meter_number" in keys else None
        return cls(
            anomaly_id=row["anomaly_id"],
            record_id=row["record_id"],
            meter_id=row["meter_id"],
            household_id=row["household_id"],
            detection_timestamp=row["detection_timestamp"],
            energy_kwh=row["energy_kwh"],
            expected_kwh=row["expected_kwh"],
            diff_kwh=row["diff_kwh"],
            pct_increase=row["pct_increase"],
            anomaly_score=row["anomaly_score"],
            method=row["method"],
            severity=row["severity"],
            status=row["status"],
            notes=row["notes"],
            possible_causes=row["possible_causes"],
            recommendations=row["recommendations"],
            created_at=row["created_at"],
            household_name=h_name,
            meter_number=m_num
        )

    @classmethod
    def get_by_id(cls, anomaly_id):
        """Fetches anomaly by ID with joins."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.*, h.household_name, m.meter_number
                FROM anomaly_records a
                JOIN households h ON a.household_id = h.household_id
                JOIN smart_meters m ON a.meter_id = m.meter_id
                WHERE a.anomaly_id = ?;
            """, (anomaly_id,))
            return cls.from_row(cursor.fetchone())

    @classmethod
    def update_status(cls, anomaly_id, status, notes=None):
        """Updates the investigation state and logs notes."""
        valid_statuses = ('New', 'Under Investigation', 'Resolved', 'False Positive')
        if status not in valid_statuses:
            raise ValueError(f"Invalid status '{status}'. Must be one of {valid_statuses}")
            
        with db_session() as conn:
            cursor = conn.cursor()
            if notes is not None:
                cursor.execute("""
                    UPDATE anomaly_records
                    SET status = ?, notes = ?
                    WHERE anomaly_id = ?;
                """, (status, notes.strip(), anomaly_id))
            else:
                cursor.execute("""
                    UPDATE anomaly_records
                    SET status = ?
                    WHERE anomaly_id = ?;
                """, (status, anomaly_id))
            return True

    @classmethod
    def get_all(cls, household_id=None, severity=None, status=None, limit=200):
        """Retrieves filtered anomalies."""
        query = """
            SELECT a.*, h.household_name, m.meter_number
            FROM anomaly_records a
            JOIN households h ON a.household_id = h.household_id
            JOIN smart_meters m ON a.meter_id = m.meter_id
            WHERE 1=1
        """
        params = []
        if household_id:
            query += " AND a.household_id = ?"
            params.append(household_id)
        if severity:
            query += " AND a.severity = ?"
            params.append(severity)
        if status:
            query += " AND a.status = ?"
            params.append(status)
            
        query += " ORDER BY a.detection_timestamp DESC LIMIT ?;"
        params.append(limit)
        
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [cls.from_row(r) for r in cursor.fetchall()]


class AnomalyDetector:
    """
    Orchestrates the machine learning anomaly detection pipeline.
    Uses KMeans Clustering, Isolation Forest, and Dynamic Statistical Baselines.
    """

    def __init__(self, contamination=None, n_clusters=None, zscore_threshold=None):
        ml_settings = AppConfig.get_ml_settings()
        self.contamination = contamination or ml_settings["iforest_contamination"]
        self.n_clusters = n_clusters or ml_settings["kmeans_clusters"]
        self.zscore_threshold = zscore_threshold or ml_settings["zscore_threshold"]

    def _extract_features(self, df):
        """
        Engineers temporal and numerical features from consumption records.
        Features: energy_kwh, hour, day_of_week, sin/cos cyclics, rolling mean.
        """
        df = df.copy()
        df["dt"] = pd.to_datetime(df["timestamp"])
        df["hour"] = df["dt"].dt.hour
        df["day_of_week"] = df["dt"].dt.day_of_week
        df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
        
        # Cyclical temporal encoding for 24-hour cycle
        df["sin_hour"] = np.sin(2 * np.pi * df["hour"] / 24.0)
        df["cos_hour"] = np.cos(2 * np.pi * df["hour"] / 24.0)
        
        # Rolling historical mean (12 periods) per meter
        df = df.sort_values("dt")
        df["rolling_mean_24h"] = df.groupby("meter_id")["energy_kwh"].transform(
            lambda s: s.rolling(window=12, min_periods=1).mean()
        )
        
        # Hourly expected baseline for each household & hour of day
        hourly_means = df.groupby(["household_id", "hour"])["energy_kwh"].transform("mean")
        hourly_stds = df.groupby(["household_id", "hour"])["energy_kwh"].transform("std").fillna(0.2)
        
        df["expected_kwh"] = hourly_means
        df["diff_kwh"] = df["energy_kwh"] - df["expected_kwh"]
        df["z_score"] = (df["energy_kwh"] - hourly_means) / (hourly_stds + 1e-4)
        
        return df

    def _generate_explanations(self, row):
        """
        Produces context-aware possible explanations and energy-saving tips.
        Formulated strictly as possibilities, not accusations.
        """
        causes = []
        recommendations = []
        hour = row["hour"]
        kwh = row["energy_kwh"]
        expected = row["expected_kwh"]
        pct = row["pct_increase"]
        diff = row["diff_kwh"]
        voltage = row.get("voltage", 230.0)

        # 1. Overnight spike hypothesis
        if 0 <= hour <= 5:
            causes.append("Unexpected overnight consumption: Potential continuous load, unmonitored heavy appliance (HVAC, water heater, pump), or standby leakage.")
            recommendations.append("Inspect overnight appliances; verify refrigerator door seals and thermostat setpoints.")
            
        # 2. Extreme spike hypothesis
        if pct >= 150.0 or diff >= 3.0:
            causes.append("Unusually high appliance usage: High-draw equipment operated simultaneously (e.g., electric heaters, EV charger, ovens).")
            recommendations.append("Stagger the operation of high-wattage equipment to avoid peak demand surges.")
            
        # 3. Persistent elevated load
        if diff >= 2.0 and row.get("rolling_mean_24h", 0) > expected * 1.5:
            causes.append("Possible faulty appliance: Prolonged elevated draw suggests a compressor cycling failure or stuck thermostat.")
            recommendations.append("Have high-draw appliances serviced; inspect heating and cooling compressors.")

        # 4. Sensor or voltage fluctuation
        if voltage and (voltage < 215.0 or voltage > 245.0):
            causes.append("Grid voltage or smart meter sensor anomaly: Abnormal voltage levels recorded alongside load change.")
            recommendations.append("Check with local utility provider regarding distribution voltage stability.")

        # Default fallback explanation
        if not causes:
            causes.append("An unexplained usage pattern requiring investigation: Consumption deviated significantly from the household's normal cluster profile.")
            recommendations.append("Review household activity at the recorded timestamp to identify active equipment.")

        return causes, recommendations

    def run_detection(self, household_id=None):
        """
        Executes the full ML anomaly detection pipeline across records.
        Saves identified anomalies into the anomaly_records table.
        Returns a summary dictionary of detection results.
        """
        query = """
            SELECT record_id, meter_id, household_id, timestamp, energy_kwh, voltage, current, data_source
            FROM consumption_records
            WHERE 1=1
        """
        params = []
        if household_id:
            query += " AND household_id = ?"
            params.append(household_id)
            
        query += " ORDER BY timestamp ASC;"
        
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            raw_records = cursor.fetchall()
            
        if not raw_records or len(raw_records) < 5:
            return {
                "status": "insufficient_data",
                "message": "At least 5 consumption records are required to perform clustering and anomaly detection.",
                "total_records_analyzed": len(raw_records) if raw_records else 0,
                "anomalies_flagged": 0
            }

        df = pd.DataFrame([dict(r) for r in raw_records])
        df = self._extract_features(df)
        n_records = len(df)

        # -------------------------------------------------------------
        # Technique A: Clustering with K-Means
        # -------------------------------------------------------------
        kmeans_features = ["energy_kwh", "sin_hour", "cos_hour", "is_weekend"]
        n_clusters = min(self.n_clusters, max(2, n_records // 10))

        if SKLEARN_ENABLED:
            scaler_km = SklearnStandardScaler()
            X_km = scaler_km.fit_transform(df[kmeans_features])
            kmeans = SklearnKMeans(n_clusters=n_clusters, random_state=42, n_init='auto')
            cluster_labels = kmeans.fit_predict(X_km)
            cluster_centers = kmeans.cluster_centers_
            engine_name = "Scikit-Learn"
        else:
            scaler_km = NativeStandardScaler()
            X_km = scaler_km.fit_transform(df[kmeans_features].to_numpy())
            kmeans = NativeKMeans(n_clusters=n_clusters, random_state=42)
            cluster_labels = kmeans.fit_predict(X_km)
            cluster_centers = kmeans.cluster_centers_
            engine_name = "Native ML"

        df["cluster"] = cluster_labels
        
        # Euclidean distance to assigned cluster centroid
        distances = np.linalg.norm(X_km - cluster_centers[cluster_labels], axis=1)
        df["kmeans_distance"] = distances
        
        dist_threshold = np.percentile(distances, 95) if len(distances) >= 20 else np.mean(distances) + 2.0 * np.std(distances)
        df["kmeans_outlier"] = (distances > dist_threshold).astype(int)

        # -------------------------------------------------------------
        # Technique B: Outlier Detection with Isolation Forest
        # -------------------------------------------------------------
        if_features = ["energy_kwh", "sin_hour", "cos_hour", "rolling_mean_24h", "diff_kwh"]
        contamination = max(0.01, min(0.20, float(self.contamination)))

        if SKLEARN_ENABLED:
            scaler_if = SklearnStandardScaler()
            X_if = scaler_if.fit_transform(df[if_features])
            iso_forest = SklearnIsolationForest(
                contamination=contamination,
                random_state=42,
                n_estimators=100
            )
            if_predictions = iso_forest.fit_predict(X_if)
            raw_scores = iso_forest.decision_function(X_if)
        else:
            scaler_if = NativeStandardScaler()
            X_if = scaler_if.fit_transform(df[if_features].to_numpy())
            iso_forest = NativeIsolationForest(
                contamination=contamination,
                random_state=42,
                n_estimators=100
            )
            if_predictions = iso_forest.fit_predict(X_if)
            raw_scores = iso_forest.decision_function(X_if)

        # Normalize score between 0.0 (normal) and 1.0 (highly abnormal)
        min_score = np.min(raw_scores)
        max_score = np.max(raw_scores)
        if max_score > min_score:
            norm_scores = 1.0 - ((raw_scores - min_score) / (max_score - min_score))
        else:
            norm_scores = np.zeros(len(raw_scores))
            
        df["if_prediction"] = if_predictions
        df["anomaly_score"] = norm_scores

        # -------------------------------------------------------------
        # Technique C: Statistical Baseline & Ensemble Combination
        # -------------------------------------------------------------
        df["pct_increase"] = np.where(
            df["expected_kwh"] > 0.05,
            ((df["energy_kwh"] - df["expected_kwh"]) / df["expected_kwh"]) * 100.0,
            0.0
        )
        df["pct_increase"] = df["pct_increase"].clip(lower=0.0)

        high_priority_mask = (
            ((df["if_prediction"] == -1) & ((df["z_score"] >= self.zscore_threshold) | (df["kmeans_outlier"] == 1)) & (df["diff_kwh"] >= 1.5)) |
            (df["z_score"] >= 3.8) |
            ((df["pct_increase"] >= 250.0) & (df["diff_kwh"] >= 2.0))
        )
        
        unusual_mask = (
            (~high_priority_mask) & 
            (
                (df["if_prediction"] == -1) | 
                (df["z_score"] >= 2.0) | 
                (df["kmeans_outlier"] == 1)
            ) & 
            (df["diff_kwh"] > 0.4)
        )

        df["severity"] = "Normal"
        df.loc[unusual_mask, "severity"] = "Unusual"
        df.loc[high_priority_mask, "severity"] = "High Priority"

        # Determine method tag
        df["method"] = f"Statistical Baseline ({engine_name})"
        df.loc[(df["if_prediction"] == -1) & (df["kmeans_outlier"] == 1), "method"] = f"Ensemble (IForest + KMeans - {engine_name})"
        df.loc[(df["if_prediction"] == -1) & (df["kmeans_outlier"] == 0), "method"] = f"Isolation Forest ({engine_name})"
        df.loc[(df["if_prediction"] == 1) & (df["kmeans_outlier"] == 1), "method"] = f"K-Means Clustering ({engine_name})"

        anomalies_df = df[df["severity"].isin(["Unusual", "High Priority"])].copy()

        new_anomalies_count = 0
        with db_session() as conn:
            cursor = conn.cursor()
            
            for _, row in anomalies_df.iterrows():
                cursor.execute("SELECT anomaly_id FROM anomaly_records WHERE record_id = ?;", (int(row["record_id"]),))
                existing = cursor.fetchone()
                
                causes, recs = self._generate_explanations(row)
                causes_json = json.dumps(causes)
                recs_json = json.dumps(recs)
                
                if existing:
                    cursor.execute("""
                        UPDATE anomaly_records 
                        SET expected_kwh = ?, diff_kwh = ?, pct_increase = ?, 
                            anomaly_score = ?, method = ?, severity = ?,
                            possible_causes = ?, recommendations = ?
                        WHERE record_id = ?;
                    """, (
                        float(row["expected_kwh"]), float(row["diff_kwh"]), float(row["pct_increase"]),
                        float(row["anomaly_score"]), row["method"], row["severity"],
                        causes_json, recs_json, int(row["record_id"])
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO anomaly_records (
                            record_id, meter_id, household_id, detection_timestamp,
                            energy_kwh, expected_kwh, diff_kwh, pct_increase,
                            anomaly_score, method, severity, status, notes,
                            possible_causes, recommendations
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New', '', ?, ?);
                    """, (
                        int(row["record_id"]), int(row["meter_id"]), int(row["household_id"]),
                        str(row["timestamp"]), float(row["energy_kwh"]), float(row["expected_kwh"]),
                        float(row["diff_kwh"]), float(row["pct_increase"]), float(row["anomaly_score"]),
                        row["method"], row["severity"], causes_json, recs_json
                    ))
                    new_anomalies_count += 1

        return {
            "status": "success",
            "total_records_analyzed": len(df),
            "total_anomalies_detected": len(anomalies_df),
            "new_anomalies_flagged": new_anomalies_count,
            "high_priority_count": int((anomalies_df["severity"] == "High Priority").sum()),
            "unusual_count": int((anomalies_df["severity"] == "Unusual").sum()),
            "clusters_used": n_clusters,
            "contamination_parameter": self.contamination,
            "engine": engine_name
        }
