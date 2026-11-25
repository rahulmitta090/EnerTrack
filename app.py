"""
EnerTrack — Household Energy Consumption Anomaly Detector
Main Flask Application Controller
Provides routing, session security, role-based authorization, REST endpoints, and view rendering.
"""
import io
import csv
import os
import json
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, Response, g
)

from config import Config
from database import init_db, db_session
from models import User, AppConfig
from household import Household
from smart_meter import SmartMeter
from consumption import ConsumptionRecord
from data_generator import SmartMeterSimulator
from anomaly_detector import AnomalyDetector, AnomalyRecord
from recommendations import EnergyAnalytics

# Initialize Flask application
app = Flask(__name__)
app.config.from_object(Config)

# Ensure database is initialized at startup
init_db(seed_sample_data=True)

# -------------------------------------------------------------
# Authentication & Access Control Helpers
# -------------------------------------------------------------

@app.before_request
def load_current_user():
    """Loads logged-in user into Flask's global context `g.user`."""
    user_id = session.get("user_id")
    if user_id:
        g.user = User.get_by_id(user_id)
    else:
        g.user = None

def login_required(f):
    """Decorator requiring an active user session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator requiring administrative role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash("Authentication required.", "warning")
            return redirect(url_for("login"))
        if not g.user.is_admin():
            flash("Administrative access privileges required.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function

# Context processor for global template variables
@app.context_processor
def inject_global_data():
    """Makes common variables (currency, active user, notification count) available across templates."""
    currency = AppConfig.get_currency_symbol()
    active_anomalies_count = 0
    if g.user:
        with db_session() as conn:
            cursor = conn.cursor()
            if g.user.is_admin():
                cursor.execute("SELECT COUNT(*) as count FROM anomaly_records WHERE status IN ('New', 'Under Investigation');")
            else:
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM anomaly_records a
                    JOIN households h ON a.household_id = h.household_id
                    WHERE h.user_id = ? AND a.status IN ('New', 'Under Investigation');
                """, (g.user.user_id,))
            row = cursor.fetchone()
            active_anomalies_count = row["count"] if row else 0

    return {
        "current_user": g.user,
        "currency_symbol": currency,
        "active_anomalies_count": active_anomalies_count,
        "current_year": datetime.now().year
    }

# -------------------------------------------------------------
# Authentication Routes
# -------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    """Handles user and administrator authentication."""
    if g.user:
        return redirect(url_for("dashboard"))
        
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        if not username or not password:
            flash("Please enter both username and password.", "danger")
            return render_template("login.html")
            
        user = User.get_by_username(username)
        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.user_id
            session["role"] = user.role
            session.permanent = True
            flash(f"Welcome back, {user.full_name or user.username}!", "success")
            
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials. Please verify your username and password.", "danger")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Allows household owners to register a new account."""
    if g.user:
        return redirect(url_for("dashboard"))
        
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        # Validation
        if not username or not email or not password:
            flash("All fields marked with an asterisk are required.", "danger")
            return render_template("register.html")
            
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "warning")
            return render_template("register.html")
            
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")
            
        if User.get_by_username(username):
            flash("That username is already taken. Please choose another.", "warning")
            return render_template("register.html")
            
        if User.get_by_email(email):
            flash("An account with that email already exists.", "warning")
            return render_template("register.html")
            
        # Register new household user
        new_user = User.create(
            username=username,
            email=email,
            password=password,
            role="user",
            full_name=full_name or username
        )
        
        session.clear()
        session["user_id"] = new_user.user_id
        session["role"] = new_user.role
        flash("Registration successful! You may now add your household and smart meters.", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")

@app.route("/logout")
def logout():
    """Logs out current session."""
    session.clear()
    flash("You have been signed out safely.", "info")
    return redirect(url_for("login"))

# -------------------------------------------------------------
# Main Dashboard
# -------------------------------------------------------------

@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():
    """
    Renders main analytical dashboard with KPI metrics, Chart.js views,
    recent anomaly alerts, and energy saving recommendations.
    """
    selected_household_id = request.args.get("household_id", type=int)

    # Determine households accessible to current user
    if g.user.is_admin():
        accessible_households = Household.get_all()
    else:
        accessible_households = Household.get_by_user(g.user.user_id)

    # Verify household access if a specific filter was provided
    if selected_household_id:
        target_h = Household.get_by_id(selected_household_id)
        if not target_h or not target_h.can_access(g.user):
            flash("Unauthorized access to requested household.", "danger")
            selected_household_id = None

    # Calculate real KPI metrics from SQLite
    with db_session() as conn:
        cursor = conn.cursor()
        
        # 1. Total Households
        if g.user.is_admin():
            cursor.execute("SELECT COUNT(*) as count FROM households;")
        else:
            cursor.execute("SELECT COUNT(*) as count FROM households WHERE user_id = ?;", (g.user.user_id,))
        kpi_households = cursor.fetchone()["count"]

        # 2. Registered Smart Meters
        if g.user.is_admin():
            if selected_household_id:
                cursor.execute("SELECT COUNT(*) as count FROM smart_meters WHERE household_id = ?;", (selected_household_id,))
            else:
                cursor.execute("SELECT COUNT(*) as count FROM smart_meters;")
        else:
            if selected_household_id:
                cursor.execute("SELECT COUNT(*) as count FROM smart_meters WHERE household_id = ?;", (selected_household_id,))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM smart_meters m
                    JOIN households h ON m.household_id = h.household_id
                    WHERE h.user_id = ?;
                """, (g.user.user_id,))
        kpi_meters = cursor.fetchone()["count"]

        # 3. Total Energy Consumption in kWh
        c_query = "SELECT COALESCE(SUM(energy_kwh), 0.0) as total_kwh, COUNT(*) as count FROM consumption_records WHERE 1=1"
        c_params = []
        if selected_household_id:
            c_query += " AND household_id = ?"
            c_params.append(selected_household_id)
        elif not g.user.is_admin():
            c_query += " AND household_id IN (SELECT household_id FROM households WHERE user_id = ?)"
            c_params.append(g.user.user_id)
            
        cursor.execute(c_query, c_params)
        c_res = cursor.fetchone()
        kpi_total_kwh = round(c_res["total_kwh"], 1)
        kpi_readings_count = c_res["count"]

        # 4 & 5. Anomalies Detected and High-Priority Anomalies
        a_query = """
            SELECT 
                COUNT(*) as total_anomalies,
                COALESCE(SUM(CASE WHEN severity = 'High Priority' THEN 1 ELSE 0 END), 0) as high_priority,
                COALESCE(SUM(CASE WHEN severity = 'Unusual' THEN 1 ELSE 0 END), 0) as unusual_count,
                COALESCE(SUM(CASE WHEN status IN ('New', 'Under Investigation') THEN 1 ELSE 0 END), 0) as active_count
            FROM anomaly_records WHERE 1=1
        """
        a_params = []
        if selected_household_id:
            a_query += " AND household_id = ?"
            a_params.append(selected_household_id)
        elif not g.user.is_admin():
            a_query += " AND household_id IN (SELECT household_id FROM households WHERE user_id = ?)"
            a_params.append(g.user.user_id)
            
        cursor.execute(a_query, a_params)
        a_res = cursor.fetchone()
        kpi_anomalies = a_res["total_anomalies"]
        kpi_high_priority = a_res["high_priority"]
        kpi_active_anomalies = a_res["active_count"]

    # 6. Cost Analytics & Recommendations
    cost_data = EnergyAnalytics.calculate_cost_summary(household_id=selected_household_id, days=30)
    recommendations = EnergyAnalytics.generate_recommendations(household_id=selected_household_id)

    # Recent Anomalies list (limit 6)
    recent_anomalies = AnomalyRecord.get_all(
        household_id=selected_household_id if selected_household_id else (None if g.user.is_admin() else None),
        limit=6
    )
    if not g.user.is_admin() and not selected_household_id:
        user_h_ids = {h.household_id for h in accessible_households}
        recent_anomalies = [a for a in recent_anomalies if a.household_id in user_h_ids]

    # Recent Consumption telemetry feed (limit 8)
    recent_records = ConsumptionRecord.get_records(
        household_id=selected_household_id,
        limit=8
    )
    if not g.user.is_admin() and not selected_household_id:
        user_h_ids = {h.household_id for h in accessible_households}
        recent_records = [r for r in recent_records if r.household_id in user_h_ids]

    return render_template(
        "dashboard.html",
        households=accessible_households,
        selected_household_id=selected_household_id,
        kpi_households=kpi_households,
        kpi_meters=kpi_meters,
        kpi_total_kwh=kpi_total_kwh,
        kpi_readings_count=kpi_readings_count,
        kpi_anomalies=kpi_anomalies,
        kpi_high_priority=kpi_high_priority,
        kpi_active_anomalies=kpi_active_anomalies,
        cost_data=cost_data,
        recommendations=recommendations,
        recent_anomalies=recent_anomalies,
        recent_records=recent_records
    )

# -------------------------------------------------------------
# Household Management Module
# -------------------------------------------------------------

@app.route("/households")
@login_required
def households_view():
    """Displays household profiles with associated smart meters and consumption aggregates."""
    if g.user.is_admin():
        households = Household.get_all()
    else:
        households = Household.get_by_user(g.user.user_id)
        
    # Attach meters & summary statistics
    household_cards = []
    for h in households:
        meters = h.get_meters()
        summary = h.get_consumption_summary()
        household_cards.append({
            "household": h,
            "meters": meters,
            "summary": summary
        })
        
    return render_template("households.html", household_cards=household_cards)

@app.route("/households/add", methods=["POST"])
@login_required
def add_household():
    """Adds a new household."""
    name = request.form.get("household_name")
    address = request.form.get("address")
    city = request.form.get("city")
    household_type = request.form.get("household_type", "Detached House")
    members = request.form.get("number_of_members", 1)
    
    # If admin, allow specifying target user ID
    target_user_id = g.user.user_id
    if g.user.is_admin() and request.form.get("user_id"):
        try:
            target_user_id = int(request.form.get("user_id"))
        except ValueError:
            pass

    try:
        new_h = Household.create(
            household_name=name,
            address=address,
            city=city,
            household_type=household_type,
            number_of_members=members,
            user_id=target_user_id
        )
        flash(f"Household '{new_h.household_name}' added successfully.", "success")
    except Exception as e:
        flash(f"Error adding household: {str(e)}", "danger")

    return redirect(url_for("households_view"))

@app.route("/households/<int:household_id>/edit", methods=["POST"])
@login_required
def edit_household(household_id):
    """Updates household attributes."""
    household = Household.get_by_id(household_id)
    if not household or not household.can_access(g.user):
        flash("Unauthorized or household not found.", "danger")
        return redirect(url_for("households_view"))
        
    name = request.form.get("household_name")
    address = request.form.get("address")
    city = request.form.get("city")
    household_type = request.form.get("household_type")
    members = request.form.get("number_of_members")
    
    try:
        household.update(name, address, city, household_type, members)
        flash("Household information updated successfully.", "success")
    except Exception as e:
        flash(f"Failed to update household: {str(e)}", "danger")
        
    return redirect(url_for("households_view"))

@app.route("/households/<int:household_id>/delete", methods=["POST"])
@login_required
def delete_household(household_id):
    """Deletes household with cascading relations."""
    household = Household.get_by_id(household_id)
    if not household or not household.can_access(g.user):
        flash("Unauthorized or household not found.", "danger")
        return redirect(url_for("households_view"))
        
    name = household.household_name
    household.delete()
    flash(f"Household '{name}' and associated smart meters/records have been removed.", "info")
    return redirect(url_for("households_view"))

# -------------------------------------------------------------
# Smart Meter Management Module
# -------------------------------------------------------------

@app.route("/meters")
@login_required
def meters_view():
    """Lists smart meters with status indicators, telemetry totals, and quick actions."""
    if g.user.is_admin():
        meters = SmartMeter.get_all()
        user_households = Household.get_all()
    else:
        user_households = Household.get_by_user(g.user.user_id)
        user_h_ids = {h.household_id for h in user_households}
        all_meters = SmartMeter.get_all()
        meters = [m for m in all_meters if m.household_id in user_h_ids]

    meter_details = []
    for m in meters:
        totals = m.get_total_consumption()
        meter_details.append({
            "meter": m,
            "total_kwh": round(totals["total_kwh"], 2),
            "reading_count": totals["reading_count"]
        })

    return render_template("meters.html", meter_details=meter_details, households=user_households)

@app.route("/meters/add", methods=["POST"])
@login_required
def add_meter():
    """Registers a new smart meter."""
    household_id = request.form.get("household_id", type=int)
    meter_number = request.form.get("meter_number", "").strip()
    meter_type = request.form.get("meter_type", "Smart Digital")
    installation_date = request.form.get("installation_date")
    status = request.form.get("status", "Active")

    household = Household.get_by_id(household_id)
    if not household or not household.can_access(g.user):
        flash("Invalid household selected or access denied.", "danger")
        return redirect(url_for("meters_view"))

    if not meter_number:
        flash("Smart meter number is required.", "danger")
        return redirect(url_for("meters_view"))

    if SmartMeter.get_by_meter_number(meter_number):
        flash(f"A meter with serial number '{meter_number}' already exists.", "warning")
        return redirect(url_for("meters_view"))

    try:
        new_meter = SmartMeter.register(
            household_id=household_id,
            meter_number=meter_number,
            meter_type=meter_type,
            installation_date=installation_date,
            status=status
        )
        flash(f"Smart meter '{new_meter.meter_number}' registered successfully.", "success")
    except Exception as e:
        flash(f"Error registering meter: {str(e)}", "danger")

    return redirect(url_for("meters_view"))

@app.route("/meters/<int:meter_id>/toggle", methods=["POST"])
@login_required
def toggle_meter(meter_id):
    """Toggles meter between Active and Inactive status."""
    meter = SmartMeter.get_by_id(meter_id)
    if not meter:
        flash("Smart meter not found.", "danger")
        return redirect(url_for("meters_view"))

    household = Household.get_by_id(meter.household_id)
    if not household or not household.can_access(g.user):
        flash("Unauthorized access.", "danger")
        return redirect(url_for("meters_view"))

    meter.toggle_status()
    flash(f"Smart meter '{meter.meter_number}' status updated to {meter.status}.", "info")
    return redirect(url_for("meters_view"))

@app.route("/meters/<int:meter_id>/edit", methods=["POST"])
@login_required
def edit_meter(meter_id):
    """Edits smart meter configuration."""
    meter = SmartMeter.get_by_id(meter_id)
    if not meter:
        flash("Smart meter not found.", "danger")
        return redirect(url_for("meters_view"))

    household = Household.get_by_id(meter.household_id)
    if not household or not household.can_access(g.user):
        flash("Unauthorized access.", "danger")
        return redirect(url_for("meters_view"))

    meter_type = request.form.get("meter_type", meter.meter_type)
    status = request.form.get("status", meter.status)
    try:
        meter.update(meter_type, status)
        flash("Meter updated successfully.", "success")
    except Exception as e:
        flash(f"Update failed: {str(e)}", "danger")

    return redirect(url_for("meters_view"))

# -------------------------------------------------------------
# Energy Consumption Telemetry Module
# -------------------------------------------------------------

@app.route("/consumption")
@login_required
def consumption_view():
    """Lists consumption telemetry logs with filtering, manual entry, simulation generator, and CSV import."""
    page = request.args.get("page", 1, type=int)
    limit = 50
    offset = (page - 1) * limit

    h_filter = request.args.get("household_id", type=int)
    m_filter = request.args.get("meter_id", type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    source_filter = request.args.get("data_source")

    # Authorize household filter
    if g.user.is_admin():
        user_households = Household.get_all()
    else:
        user_households = Household.get_by_user(g.user.user_id)
        if h_filter:
            th = Household.get_by_id(h_filter)
            if not th or not th.can_access(g.user):
                flash("Unauthorized filter.", "danger")
                h_filter = None

    # Default to user's households if not admin and no specific filter
    target_hid = h_filter
    records = ConsumptionRecord.get_records(
        household_id=target_hid,
        meter_id=m_filter,
        start_date=start_date,
        end_date=end_date,
        data_source=source_filter,
        limit=limit,
        offset=offset
    )

    if not g.user.is_admin() and not target_hid:
        user_h_ids = {h.household_id for h in user_households}
        records = [r for r in records if r.household_id in user_h_ids]

    # Available meters for modal dropdowns
    available_meters = []
    for h in user_households:
        available_meters.extend(h.get_meters())

    return render_template(
        "consumption.html",
        records=records,
        households=user_households,
        meters=available_meters,
        selected_household_id=h_filter,
        selected_meter_id=m_filter,
        start_date=start_date,
        end_date=end_date,
        data_source=source_filter,
        page=page
    )

@app.route("/consumption/add", methods=["POST"])
@login_required
def add_manual_consumption():
    """Inserts a single manual energy measurement."""
    meter_id = request.form.get("meter_id", type=int)
    timestamp = request.form.get("timestamp")
    energy_kwh = request.form.get("energy_kwh")
    voltage = request.form.get("voltage", 230.0)

    meter = SmartMeter.get_by_id(meter_id)
    if not meter:
        flash("Invalid smart meter selected.", "danger")
        return redirect(url_for("consumption_view"))

    household = Household.get_by_id(meter.household_id)
    if not household or not household.can_access(g.user):
        flash("Access denied.", "danger")
        return redirect(url_for("consumption_view"))

    try:
        ConsumptionRecord.add_record(
            meter_id=meter_id,
            household_id=meter.household_id,
            timestamp=timestamp,
            energy_kwh=energy_kwh,
            voltage=voltage,
            data_source="manual_entry"
        )
        flash("Consumption record recorded successfully.", "success")
    except ValueError as e:
        flash(f"Validation error: {str(e)}", "danger")
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "danger")

    return redirect(url_for("consumption_view"))

@app.route("/consumption/simulate", methods=["POST"])
@login_required
def generate_simulated_consumption():
    """
    Generates realistic simulated smart-meter consumption data for the selected household/meter.
    Clearly marks records with data_source='simulated'.
    """
    meter_id = request.form.get("meter_id", type=int)
    days = request.form.get("days", 14, type=int)
    anomaly_count = request.form.get("anomaly_count", 4, type=int)

    meter = SmartMeter.get_by_id(meter_id)
    if not meter:
        flash("Smart meter not found.", "danger")
        return redirect(url_for("consumption_view"))

    household = Household.get_by_id(meter.household_id)
    if not household or not household.can_access(g.user):
        flash("Access denied.", "danger")
        return redirect(url_for("consumption_view"))

    try:
        inserted = SmartMeterSimulator.populate_household_simulation(
            household_id=meter.household_id,
            meter_id=meter_id,
            days=max(1, min(60, days)),
            anomaly_count=max(0, min(20, anomaly_count))
        )
        flash(f"Successfully generated {inserted} simulated hourly readings for meter {meter.meter_number}. All data is explicitly labeled as 'simulated'.", "success")
    except Exception as e:
        flash(f"Simulation generation failed: {str(e)}", "danger")

    return redirect(url_for("consumption_view"))

@app.route("/consumption/import-csv", methods=["POST"])
@login_required
def import_csv_consumption():
    """
    Imports and validates smart meter readings from an uploaded CSV file.
    Rejects invalid headers, invalid timestamps, or negative energy numbers.
    """
    if "csv_file" not in request.files:
        flash("No CSV file selected.", "warning")
        return redirect(url_for("consumption_view"))

    file = request.files["csv_file"]
    if file.filename == "":
        flash("Please choose a file to upload.", "warning")
        return redirect(url_for("consumption_view"))

    default_meter_id = request.form.get("meter_id", type=int)

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8"), newline=None)
        reader = csv.DictReader(stream)
        
        # Verify required headers
        required_cols = {"timestamp", "energy_kwh"}
        if not required_cols.issubset({c.strip().lower() for c in reader.fieldnames or []}):
            flash("CSV is missing required columns. It must include 'timestamp' and 'energy_kwh'.", "danger")
            return redirect(url_for("consumption_view"))

        # Normalize fieldnames
        field_map = {c.strip().lower(): c for c in reader.fieldnames}
        ts_col = field_map["timestamp"]
        kwh_col = field_map["energy_kwh"]
        meter_col = field_map.get("meter_number")
        volt_col = field_map.get("voltage")
        curr_col = field_map.get("current")

        batch = []
        errors = []
        row_num = 1

        for row in reader:
            row_num += 1
            ts_val = row.get(ts_col, "").strip()
            kwh_val = row.get(kwh_col, "").strip()

            if not ts_val or not kwh_val:
                continue

            try:
                valid_kwh, valid_ts = ConsumptionRecord.validate_reading(kwh_val, ts_val)
            except ValueError as ve:
                errors.append(f"Row {row_num}: {str(ve)}")
                if len(errors) > 5:
                    break
                continue

            # Resolve meter and household
            meter_id = default_meter_id
            household_id = None
            if meter_col and row.get(meter_col):
                meter_obj = SmartMeter.get_by_meter_number(row[meter_col])
                if meter_obj:
                    meter_id = meter_obj.meter_id
                    household_id = meter_obj.household_id
            
            if not household_id and meter_id:
                m_obj = SmartMeter.get_by_id(meter_id)
                if m_obj:
                    household_id = m_obj.household_id

            if not meter_id or not household_id:
                errors.append(f"Row {row_num}: Could not resolve target smart meter.")
                if len(errors) > 5:
                    break
                continue

            # Verify authorization
            h_obj = Household.get_by_id(household_id)
            if not h_obj or not h_obj.can_access(g.user):
                errors.append(f"Row {row_num}: Unauthorized meter {meter_id}.")
                break

            voltage = float(row.get(volt_col, 230.0)) if volt_col and row.get(volt_col) else 230.0
            current = float(row.get(curr_col, 0.0)) if curr_col and row.get(curr_col) else round((valid_kwh * 1000) / (voltage * 0.9), 2)

            batch.append((meter_id, household_id, valid_ts, valid_kwh, voltage, current, "imported_csv"))

        if errors:
            flash(f"CSV import encountered errors: {'; '.join(errors[:3])}", "danger")
            return redirect(url_for("consumption_view"))

        if batch:
            inserted = ConsumptionRecord.add_batch(batch)
            flash(f"Successfully imported {inserted} verified energy readings from CSV (tagged as 'imported_csv').", "success")
        else:
            flash("No valid rows were found in the uploaded CSV.", "warning")

    except Exception as e:
        flash(f"Failed to process CSV file: {str(e)}", "danger")

    return redirect(url_for("consumption_view"))

# -------------------------------------------------------------
# Machine Learning Anomaly Detection & Investigation Module
# -------------------------------------------------------------

@app.route("/anomalies")
@login_required
def anomalies_view():
    """Renders the Anomaly Investigation Centre with filtering, severity badges, and diagnostic notes."""
    h_filter = request.args.get("household_id", type=int)
    severity_filter = request.args.get("severity")
    status_filter = request.args.get("status")

    if g.user.is_admin():
        user_households = Household.get_all()
    else:
        user_households = Household.get_by_user(g.user.user_id)
        if h_filter:
            th = Household.get_by_id(h_filter)
            if not th or not th.can_access(g.user):
                flash("Unauthorized household filter.", "danger")
                h_filter = None

    target_hid = h_filter
    anomalies = AnomalyRecord.get_all(
        household_id=target_hid,
        severity=severity_filter,
        status=status_filter,
        limit=200
    )

    if not g.user.is_admin() and not target_hid:
        user_h_ids = {h.household_id for h in user_households}
        anomalies = [a for a in anomalies if a.household_id in user_h_ids]

    ml_settings = AppConfig.get_ml_settings()

    return render_template(
        "anomalies.html",
        anomalies=anomalies,
        households=user_households,
        selected_household_id=h_filter,
        selected_severity=severity_filter,
        selected_status=status_filter,
        ml_settings=ml_settings
    )

@app.route("/anomalies/run-detector", methods=["POST"])
@login_required
def run_anomaly_detector():
    """
    Triggers the machine learning anomaly detection pipeline (K-Means + Isolation Forest + Dynamic Baseline).
    """
    household_id = request.form.get("household_id", type=int)
    
    # Non-admin users can only run detector on their own households
    if not g.user.is_admin():
        if household_id:
            th = Household.get_by_id(household_id)
            if not th or not th.can_access(g.user):
                flash("Unauthorized access.", "danger")
                return redirect(url_for("anomalies_view"))
        else:
            user_h = Household.get_by_user(g.user.user_id)
            if not user_h:
                flash("Please register a household before running anomaly detection.", "warning")
                return redirect(url_for("households_view"))
            household_id = user_h[0].household_id

    detector = AnomalyDetector()
    results = detector.run_detection(household_id=household_id)

    if results["status"] == "insufficient_data":
        flash(results["message"], "warning")
    else:
        flash(
            f"Machine Learning pipeline completed: analyzed {results['total_records_analyzed']} records. "
            f"Identified {results['total_anomalies_detected']} anomalies "
            f"({results['high_priority_count']} High Priority, {results['unusual_count']} Unusual).",
            "success"
        )

    return redirect(url_for("anomalies_view", household_id=household_id))

@app.route("/anomalies/<int:anomaly_id>/status", methods=["POST"])
@login_required
def update_anomaly_status(anomaly_id):
    """Updates investigation status and notes for an identified anomaly."""
    anomaly = AnomalyRecord.get_by_id(anomaly_id)
    if not anomaly:
        flash("Anomaly record not found.", "danger")
        return redirect(url_for("anomalies_view"))

    household = Household.get_by_id(anomaly.household_id)
    if not household or not household.can_access(g.user):
        flash("Unauthorized access.", "danger")
        return redirect(url_for("anomalies_view"))

    new_status = request.form.get("status")
    notes = request.form.get("notes")

    try:
        AnomalyRecord.update_status(anomaly_id, new_status, notes)
        flash(f"Investigation status updated to '{new_status}'.", "success")
    except ValueError as ve:
        flash(str(ve), "danger")

    return redirect(url_for("anomalies_view"))

@app.route("/anomalies/<int:anomaly_id>/details")
@login_required
def anomaly_details_json(anomaly_id):
    """Returns JSON details of an anomaly event for modal inspection."""
    anomaly = AnomalyRecord.get_by_id(anomaly_id)
    if not anomaly:
        return jsonify({"error": "Not found"}), 404

    household = Household.get_by_id(anomaly.household_id)
    if not household or not household.can_access(g.user):
        return jsonify({"error": "Unauthorized"}), 403

    return jsonify(anomaly.to_dict())

# -------------------------------------------------------------
# Reports & CSV Export Module
# -------------------------------------------------------------

@app.route("/reports")
@login_required
def reports_view():
    """Generates analytical consumption, anomaly, cost, and investigation status reports."""
    if g.user.is_admin():
        user_households = Household.get_all()
    else:
        user_households = Household.get_by_user(g.user.user_id)

    selected_hid = request.args.get("household_id", type=int)
    if selected_hid:
        th = Household.get_by_id(selected_hid)
        if not th or not th.can_access(g.user):
            selected_hid = None

    cost_data = EnergyAnalytics.calculate_cost_summary(household_id=selected_hid, days=30)
    
    # Household summaries
    household_summaries = []
    for h in user_households:
        s = h.get_consumption_summary()
        c = EnergyAnalytics.calculate_cost_summary(household_id=h.household_id, days=30)
        household_summaries.append({
            "household": h,
            "total_kwh": round(s["total_kwh"], 2),
            "estimated_cost": c["estimated_cost"],
            "total_anomalies": s["total_anomalies"],
            "high_priority": s["high_priority_count"],
            "active_anomalies": s["active_anomalies"]
        })

    return render_template(
        "reports.html",
        households=user_households,
        selected_household_id=selected_hid,
        cost_data=cost_data,
        household_summaries=household_summaries
    )

@app.route("/reports/export-csv/consumption")
@login_required
def export_consumption_csv():
    """Exports consumption records to CSV with authorized scope filtering."""
    household_id = request.args.get("household_id", type=int)
    if not g.user.is_admin():
        if household_id:
            th = Household.get_by_id(household_id)
            if not th or not th.can_access(g.user):
                return "Unauthorized", 403
        else:
            user_h = Household.get_by_user(g.user.user_id)
            if user_h:
                household_id = user_h[0].household_id

    records = ConsumptionRecord.get_records(household_id=household_id, limit=5000)

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["Record_ID", "Household_Name", "Meter_Number", "Timestamp", "Energy_kWh", "Voltage_V", "Current_A", "Data_Source"])
    
    for r in records:
        cw.writerow([
            r.record_id,
            r.household_name or "",
            r.meter_number or "",
            r.timestamp,
            r.energy_kwh,
            r.voltage,
            r.current,
            r.data_source
        ])

    filename = f"enertrack_consumption_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

@app.route("/reports/export-csv/anomalies")
@login_required
def export_anomalies_csv():
    """Exports detected anomalies to CSV."""
    household_id = request.args.get("household_id", type=int)
    if not g.user.is_admin():
        if household_id:
            th = Household.get_by_id(household_id)
            if not th or not th.can_access(g.user):
                return "Unauthorized", 403

    anomalies = AnomalyRecord.get_all(household_id=household_id, limit=1000)
    if not g.user.is_admin() and not household_id:
        user_h_ids = {h.household_id for h in Household.get_by_user(g.user.user_id)}
        anomalies = [a for a in anomalies if a.household_id in user_h_ids]

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow([
        "Anomaly_ID", "Household_Name", "Meter_Number", "Detection_Timestamp",
        "Observed_kWh", "Baseline_kWh", "Difference_kWh", "Percentage_Increase",
        "Anomaly_Score", "Detection_Method", "Severity", "Investigation_Status", "Notes"
    ])

    for a in anomalies:
        cw.writerow([
            a.anomaly_id,
            a.household_name or "",
            a.meter_number or "",
            a.detection_timestamp,
            a.energy_kwh,
            a.expected_kwh,
            a.diff_kwh,
            f"{a.pct_increase}%",
            a.anomaly_score,
            a.method,
            a.severity,
            a.status,
            a.notes.replace("\n", " ") if a.notes else ""
        ])

    filename = f"enertrack_anomalies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

# -------------------------------------------------------------
# System Settings (Admin Only)
# -------------------------------------------------------------

@app.route("/settings", methods=["GET", "POST"])
@admin_required
def settings_view():
    """Allows administrators to configure energy tariffs, currency symbols, and ML parameters."""
    if request.method == "POST":
        tariff = request.form.get("tariff_per_kwh")
        currency = request.form.get("currency_symbol")
        contamination = request.form.get("iforest_contamination")
        clusters = request.form.get("kmeans_clusters")
        zscore = request.form.get("zscore_threshold")

        try:
            if tariff:
                t_val = float(tariff)
                if t_val < 0:
                    raise ValueError("Tariff cannot be negative.")
                AppConfig.set("tariff_per_kwh", t_val)
                
            if currency:
                AppConfig.set("currency_symbol", currency.strip()[:4])
                
            if contamination:
                c_val = float(contamination)
                if not (0.005 <= c_val <= 0.30):
                    raise ValueError("Contamination must be between 0.005 and 0.30.")
                AppConfig.set("iforest_contamination", c_val)
                
            if clusters:
                k_val = int(clusters)
                if not (2 <= k_val <= 10):
                    raise ValueError("K-Means clusters must be between 2 and 10.")
                AppConfig.set("kmeans_clusters", k_val)
                
            if zscore:
                z_val = float(zscore)
                if not (1.0 <= z_val <= 6.0):
                    raise ValueError("Z-score threshold must be between 1.0 and 6.0.")
                AppConfig.set("zscore_threshold", z_val)

            flash("System configuration updated successfully.", "success")
        except ValueError as ve:
            flash(f"Configuration error: {str(ve)}", "danger")

        return redirect(url_for("settings_view"))

    configs = AppConfig.get_all()
    return render_template("settings.html", configs=configs)

# -------------------------------------------------------------
# REST API Endpoints for Chart.js Visualizations
# -------------------------------------------------------------

@app.route("/api/charts/consumption-trend")
@login_required
def api_consumption_trend():
    """Provides daily consumption aggregates formatted for Chart.js line/bar chart."""
    household_id = request.args.get("household_id", type=int)
    days = request.args.get("days", 30, type=int)
    
    if not g.user.is_admin():
        if household_id:
            th = Household.get_by_id(household_id)
            if not th or not th.can_access(g.user):
                return jsonify({"error": "Unauthorized"}), 403
        else:
            user_h = Household.get_by_user(g.user.user_id)
            household_id = user_h[0].household_id if user_h else None

    daily_data = ConsumptionRecord.get_daily_summary(household_id=household_id, days=days)
    
    labels = [r["date_day"] for r in daily_data]
    kwh_values = [r["daily_kwh"] for r in daily_data]
    avg_values = [r["avg_kwh"] for r in daily_data]

    return jsonify({
        "labels": labels,
        "datasets": [
            {
                "label": "Daily Energy Consumption (kWh)",
                "data": kwh_values,
                "borderColor": "#38BDF8",
                "backgroundColor": "rgba(56, 189, 248, 0.15)",
                "tension": 0.35,
                "fill": True
            },
            {
                "label": "Average Hourly Rate (kWh/h)",
                "data": avg_values,
                "borderColor": "#10B981",
                "backgroundColor": "rgba(16, 185, 129, 0.1)",
                "borderDash": [5, 5],
                "tension": 0.3,
                "fill": False
            }
        ]
    })

@app.route("/api/charts/hourly-pattern")
@login_required
def api_hourly_pattern():
    """Provides average 24-hour diurnal consumption curve."""
    household_id = request.args.get("household_id", type=int)
    
    if not g.user.is_admin() and household_id:
        th = Household.get_by_id(household_id)
        if not th or not th.can_access(g.user):
            return jsonify({"error": "Unauthorized"}), 403

    hourly_data = ConsumptionRecord.get_hourly_summary(household_id=household_id)
    
    labels = [f"{str(h['hour_of_day']).zfill(2)}:00" for h in hourly_data]
    avg_kwh = [h["avg_kwh"] for h in hourly_data]
    peak_kwh = [h["max_kwh"] for h in hourly_data]

    return jsonify({
        "labels": labels,
        "datasets": [
            {
                "label": "Average Hourly Load (kWh)",
                "data": avg_kwh,
                "backgroundColor": "rgba(6, 182, 212, 0.65)",
                "borderColor": "#06B6D4",
                "borderRadius": 6
            },
            {
                "label": "Observed Peak Load (kWh)",
                "data": peak_kwh,
                "backgroundColor": "rgba(139, 92, 246, 0.4)",
                "borderColor": "#8B5CF6",
                "borderRadius": 6
            }
        ]
    })

@app.route("/api/charts/anomaly-distribution")
@login_required
def api_anomaly_distribution():
    """Provides anomaly breakdown by severity (Normal vs Unusual vs High Priority)."""
    household_id = request.args.get("household_id", type=int)
    
    where = "WHERE 1=1"
    params = []
    if household_id:
        where += " AND household_id = ?"
        params.append(household_id)
    elif not g.user.is_admin():
        where += " AND household_id IN (SELECT household_id FROM households WHERE user_id = ?)"
        params.append(g.user.user_id)

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT 
                COALESCE(SUM(CASE WHEN severity = 'High Priority' THEN 1 ELSE 0 END), 0) as high_p,
                COALESCE(SUM(CASE WHEN severity = 'Unusual' THEN 1 ELSE 0 END), 0) as unusual
            FROM anomaly_records {where};
        """, params)
        anom_res = cursor.fetchone()
        
        # Total consumption count to calculate normal readings
        cursor.execute(f"SELECT COUNT(*) as total FROM consumption_records {where};", params)
        total_records = cursor.fetchone()["total"]

    high_p = anom_res["high_p"]
    unusual = anom_res["unusual"]
    normal = max(0, total_records - (high_p + unusual))

    return jsonify({
        "labels": ["Normal Consumption", "Unusual Usage", "High Priority Spikes"],
        "datasets": [{
            "data": [normal, unusual, high_p],
            "backgroundColor": ["#10B981", "#F59E0B", "#EF4444"],
            "borderColor": ["#064e3b", "#78350f", "#7f1d1d"],
            "borderWidth": 2
        }]
    })

@app.route("/api/charts/household-comparison")
@login_required
def api_household_comparison():
    """Provides comparative total kWh usage across registered households."""
    if g.user.is_admin():
        households = Household.get_all()
    else:
        households = Household.get_by_user(g.user.user_id)

    names = []
    kwh_totals = []

    for h in households:
        summary = h.get_consumption_summary()
        names.append(h.household_name)
        kwh_totals.append(round(summary["total_kwh"], 1))

    return jsonify({
        "labels": names,
        "datasets": [{
            "label": "Total Energy Consumption (kWh)",
            "data": kwh_totals,
            "backgroundColor": [
                "rgba(56, 189, 248, 0.7)",
                "rgba(139, 92, 246, 0.7)",
                "rgba(16, 185, 129, 0.7)",
                "rgba(245, 158, 11, 0.7)",
                "rgba(239, 68, 68, 0.7)"
            ],
            "borderColor": "#0B1120",
            "borderWidth": 1.5,
            "borderRadius": 8
        }]
    })

# -------------------------------------------------------------
# Error Handlers
# -------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    """Graceful 404 error page maintaining dark theme."""
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    """Graceful 500 error page with user-friendly message."""
    return render_template("500.html"), 500

if __name__ == "__main__":
    # Run development server
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=True)
