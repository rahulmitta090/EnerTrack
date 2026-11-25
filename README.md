# EnerTrack — Household Energy Consumption Anomaly Detector

> **Problem Statement No. 82: Energy Consumption Anomaly Detector**  
> A machine learning and energy analytics platform using clustering (K-Means), outlier detection (Isolation Forest), and dynamic statistical baselines on smart-meter consumption telemetry to identify abnormal usage spikes indicative of faulty appliances, electricity leakage, or unmonitored high-draw equipment.

---

## 1. Project Overview & Architecture

EnerTrack models households, smart meters, and consumption records using **Object-Oriented Programming (OOP)**. The system provides real-time monitoring, billing estimation, multi-dimensional ML anomaly detection, and energy conservation recommendations for households and utility managers.

### System Architecture
```
                         +-----------------------------+
                         |      EnerTrack Web UI       |
                         |  (HTML5 / CSS3 / Chart.js)  |
                         +--------------+--------------+
                                        | HTTP / REST
                         +--------------v--------------+
                         |       Flask Controller      |
                         |   (app.py / decorators)     |
                         +------+-------+-------+------+
                                |       |       |
            +-------------------+       |       +--------------------+
            |                           |                            |
+-----------v-----------+   +-----------v-----------+    +-----------v-----------+
|      OOP Domain       |   |   Dual-Engine ML      |    |    Billing & Energy   |
|   Household Model     |   |   K-Means Clustering  |    |    Recommendations    |
|   SmartMeter Model    |   |   Isolation Forest    |    |    Tariff Calculator  |
|   Consumption Record  |   |   Dynamic Baseline    |    |    Excess kWh Impact  |
+-----------+-----------+   +-----------+-----------+    +-----------+-----------+
            |                           |                            |
            +-------------------+-------+----------------------------+
                                |
                     +----------v----------+
                     |   SQLite Database   |
                     | (instance/enertrack)|
                     +---------------------+
```

---

## 2. Technology Stack

- **Backend Framework:** Python 3.10+ / Flask 3.x
- **Data Science & ML Stack:** Pandas 2.2+, NumPy 1.26+, Scikit-learn 1.4+, SciPy 1.12+
  - Dual-engine architecture: Scikit-learn + Native NumPy fallback for enterprise systems with restricted C-extension policies.
- **Frontend Presentation:** HTML5, Modern CSS3 with CSS Custom Properties, Vanilla JavaScript (ES6+)
- **Visualization:** Chart.js 4.x
- **Data Persistence:** SQLite 3 with Row Factory, foreign key cascades, and transactional integrity
- **Security:** Werkzeug password hashing (PBKDF2-SHA256), session cookies (HttpOnly, SameSite=Lax), role-based route decorators (`@login_required`, `@admin_required`)

---

## 3. Directory Structure

```
C:\Users\RAM\OneDrive\Desktop\ENERTRACK\
├── app.py                      # Flask application controller & route handlers
├── config.py                   # Centralized configuration & environment constants
├── database.py                 # SQLite connection manager, schema initialization & seed logic
├── models.py                   # OOP User & AppConfig abstractions
├── household.py                # OOP Household domain model & business logic
├── smart_meter.py              # OOP SmartMeter domain model & telemetry status
├── consumption.py              # OOP ConsumptionRecord model & data validation
├── data_generator.py           # Physics-based smart meter telemetry simulator
├── anomaly_detector.py         # K-Means, Isolation Forest & Dynamic Baseline ML pipeline
├── recommendations.py          # Actionable energy recommendations & billing projections
├── seed_demo.py                # Instant demonstration database seeder
├── requirements.txt            # Python dependencies
├── README.md                   # Documentation, testing & deployment guide
├── instance/
│   └── enertrack.db            # SQLite database file
├── sample_data/
│   └── sample_smart_meter_readings.csv  # Sample CSV ready for import testing
├── static/
│   ├── css/
│   │   └── style.css           # Dark navy, cyan, neon blue design system
│   └── js/
│       ├── main.js             # Modals, mobile drawer, toasts
│       ├── charts.js           # Chart.js initialization & dynamic API loading
│       └── dashboard.js        # Real-time anomaly investigation viewer
├── templates/
│   ├── base.html               # Base layout, sidebar & navigation
│   ├── login.html              # Secure login interface
│   ├── register.html           # Household owner registration
│   ├── dashboard.html          # Main monitoring dashboard (6 KPI cards, 4 charts)
│   ├── households.html         # Household management & property cards
│   ├── meters.html             # Smart meter management & status toggling
│   ├── consumption.html        # Telemetry stream, manual entry, CSV import, simulator
│   ├── anomalies.html          # ML anomaly investigation center
│   ├── reports.html            # Analytics breakdown & CSV exports
│   ├── settings.html           # Utility tariff & ML hyperparameters
│   ├── 404.html                # Friendly 404 handler
│   └── 500.html                # Graceful 500 handler
└── tests/
    └── test_enertrack.py       # 12 automated unit and integration tests
```

---

## 4. Default Demo Accounts

The database comes pre-seeded with two accounts for instant testing:

| Role | Username | Password | Access Scope |
| :--- | :--- | :--- | :--- |
| **System Administrator** | `admin` | `Admin@123` | View all households, manage meters, configure tariffs & ML settings, run system-wide detection, download global reports. |
| **Household Owner** | `sarah_home` | `User@123` | View own households (*Oakwood Residence*, *Skyline Heights*), manage meters, view private consumption, investigate household anomalies, download personal reports. |

---

## 5. Machine Learning Detection Methodology

EnerTrack implements a multi-stage anomaly detection pipeline:

### A. Clustering with K-Means
- Group consumption records into normal usage-pattern clusters ($k=4$: overnight baseload, morning routine, daytime occupancy, evening peak).
- Uses temporal cyclic encodings ($\sin(2\pi \cdot \text{hour}/24)$, $\cos(2\pi \cdot \text{hour}/24)$) and historical rolling averages.
- Scales features using `StandardScaler`.
- Computes Euclidean distance $d_i = \|\mathbf{x}_i - \mathbf{c}_{k(i)}\|$ from assigned cluster centroid.
- Points exceeding the 95th percentile distance are flagged as cluster deviations.

### B. Outlier Detection with Isolation Forest
- Fits an ensemble of 100 Isolation Trees to partition features and measure isolation path length $h(x)$.
- Calculates decision function score $s(x, n) = 2^{-\frac{E(h(x))}{c(n)}}$.
- Utilizes a configurable contamination parameter (default: 0.05 = 5%).

### C. Dynamic Per-Household Statistical Baseline
- Computes time-of-day expected mean $\mu_{h, \text{hour}}$ and standard deviation $\sigma_{h, \text{hour}}$ for the specific household.
- Calculates standardized score:
  $$Z = \frac{x - \mu_{h, \text{hour}}}{\sigma_{h, \text{hour}}}$$

### D. Transparent Ensemble Classification
- **High Priority:** (Isolation Forest flags outlier) AND ($Z \ge 2.5$ OR K-Means outlier) AND ($\Delta \text{kWh} \ge 1.5$ OR spike $\ge 250\%$ of expected baseline).
- **Unusual:** (Isolation Forest outlier) OR ($Z \ge 2.0$) OR (K-Means outlier) AND observed consumption exceeds expected baseline.
- **Normal:** Readings within standard variance.

### E. Diagnostic Hypotheses
Anomalies trigger automated diagnostic possibilities (e.g., unexpected overnight load, compressor stuck in continuous run, high-draw simultaneous equipment). All findings are strictly formulated as *possibilities* requiring technical review, preventing wrongful accusations.

---

## 6. Installation & Quick Start

### Step 1: Open Terminal / Shell
Navigate to the project root:
```bash
cd "C:\Users\RAM\OneDrive\Desktop\ENERTRACK"
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Seed Demo Data (Optional but Recommended)
Populates realistic simulated smart-meter telemetry and executes the ML anomaly detection pipeline:
```bash
python seed_demo.py
```

### Step 4: Run the Application
```bash
python app.py
```
When `SECRET_KEY` is not set, the app generates a random key at startup. Set
`SECRET_KEY` in the environment to keep sessions valid across restarts.
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 7. Running the Automated Test Suite

EnerTrack includes 12 comprehensive unit and integration tests covering all critical paths:
```bash
python tests/test_enertrack.py
```
Expected output:
```
............
----------------------------------------------------------------------
Ran 12 tests in 2.053s

OK
```

### Test Coverage Highlights:
1. `test_01_admin_authentication`: Admin authentication & session termination.
2. `test_02_user_registration_and_login`: Household owner account creation, password hashing, and login.
3. `test_03_household_oop_lifecycle`: Household OOP CRUD operations.
4. `test_04_smart_meter_oop_lifecycle`: Smart meter registration & status toggle.
5. `test_05_consumption_validation_rules`: Timestamp syntax validation and rejection of negative kWh values.
6. `test_06_realistic_data_simulation`: Physics-based diurnal telemetry generation with explicit `simulated` data source tag.
7. `test_07_machine_learning_pipeline`: K-Means clustering, Isolation Forest outlier detection, and dynamic baseline scoring.
8. `test_08_investigation_status_update`: Updating investigation status to "Resolved" and logging technician audit notes.
9. `test_09_cost_estimation_and_recommendations`: Electricity cost calculator and rule-based energy conservation recommendations.
10. `test_10_chart_api_endpoints`: Chart.js REST endpoints for trends, 24-hour diurnal profiles, and anomaly distributions.
11. `test_11_csv_export`: Secure CSV generation for consumption and anomalies.
12. `test_12_tenant_authorization_isolation`: Tenant boundary access control preventing unauthorized cross-household data access.

---

## 8. Free-Tier Deployment Guide

### Option A: Render (Recommended Free-Tier)
1. Push your repository to GitHub.
2. Sign in to [Render](https://render.com) and click **New + > Web Service**.
3. Connect your GitHub repository.
4. Configure service settings:
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app` (add `gunicorn` to `requirements.txt` if deploying on Linux)
   - **Environment Variables:**
     - `SECRET_KEY`: `<generate-a-random-32-byte-hex-key>`
     - `TARIFF_PER_KWH`: `0.15`

### Option B: PythonAnywhere (Free-Tier)
1. Sign up for a free beginner account at [PythonAnywhere](https://www.pythonanywhere.com).
2. Open a Bash console and clone your repository or upload files.
3. Create a virtual environment and install dependencies:
   ```bash
   mkvirtualenv --python=/usr/bin/python3.10 enertrack-venv
   pip install -r requirements.txt
   ```
4. In the **Web** tab:
   - Set source code directory to `/home/<username>/ENERTRACK`.
   - Set virtualenv path to `/home/<username>/.virtualenvs/enertrack-venv`.
   - In the WSGI configuration file, point to `from app import app as application`.
5. Reload the web app.

---

## 9. Completed Features & Standards Compliance

- [x] **Full OOP Modeling:** `Household`, `SmartMeter`, `ConsumptionRecord`, `AnomalyRecord`, `AnomalyDetector`, and `EnergyAnalytics`.
- [x] **Role-Based Authorization:** Separate views, permissions, and navigation for Admins vs. Household Owners.
- [x] **Realistic Telemetry Simulation:** Physics-informed diurnal cycles with morning/evening peaks, weekend profiles, and labeled anomalies.
- [x] **CSV Ingestion & Validation:** Validates timestamps, rejects negative readings, checks upper physical bounds, and tags data source.
- [x] **Dual-Engine ML Pipeline:** Combines K-Means clustering and Isolation Forest with dynamic Z-score baselines and native NumPy resilience.
- [x] **Anomaly Investigation Center:** Full workflow with status transitions (*New*, *Under Investigation*, *Resolved*, *False Positive*) and technician notes.
- [x] **Electricity Cost Calculator:** Configurable flat tariff, period-over-period comparisons, and estimated cost of excess consumption.
- [x] **Actionable Recommendations:** Quantified energy-saving advice distinguishing measured excess from estimated avoidable wastage.
- [x] **Professional UI/UX:** Responsive Dark Navy theme (`#0A0F1D`) with neon cyan, blue, green, and purple highlights, smooth animations, and glassmorphic cards.
- [x] **Automated Test Suite:** 12 passing tests verifying all core workflows.
