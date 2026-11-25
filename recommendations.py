"""
EnerTrack Energy Analytics & Recommendation Engine
Calculates transparent estimated electricity costs, period comparisons, excess consumption impacts,
and generates actionable, quantified energy conservation recommendations.
"""
from database import db_session
from models import AppConfig

class EnergyAnalytics:
    """Calculates billing estimates, period-over-period trends, and cost of excess consumption."""

    @classmethod
    def calculate_cost_summary(cls, household_id=None, days=30):
        """
        Calculates energy cost estimates, excess kWh, and period comparisons.
        Clearly labels all monetary values as estimates.
        """
        tariff = AppConfig.get_tariff()
        currency = AppConfig.get_currency_symbol()
        
        with db_session() as conn:
            cursor = conn.cursor()
            
            # Current period consumption
            where_clause = "WHERE timestamp >= datetime('now', ?)"
            params = [f"-{days} days"]
            if household_id:
                where_clause += " AND household_id = ?"
                params.append(household_id)
                
            cursor.execute(f"""
                SELECT 
                    COALESCE(SUM(energy_kwh), 0.0) as total_kwh,
                    COALESCE(AVG(energy_kwh), 0.0) as avg_hourly_kwh,
                    COUNT(*) as total_readings
                FROM consumption_records
                {where_clause};
            """, params)
            current_row = cursor.fetchone()
            current_kwh = current_row["total_kwh"]
            
            # Previous period consumption (for period-over-period comparison)
            prev_where = "WHERE timestamp >= datetime('now', ?) AND timestamp < datetime('now', ?)"
            prev_params = [f"-{days * 2} days", f"-{days} days"]
            if household_id:
                prev_where += " AND household_id = ?"
                prev_params.append(household_id)
                
            cursor.execute(f"""
                SELECT COALESCE(SUM(energy_kwh), 0.0) as prev_kwh
                FROM consumption_records
                {prev_where};
            """, prev_params)
            prev_kwh = cursor.fetchone()["prev_kwh"]
            
            # Excess kWh attributable to detected anomalies in this period
            anom_where = "WHERE detection_timestamp >= datetime('now', ?)"
            anom_params = [f"-{days} days"]
            if household_id:
                anom_where += " AND household_id = ?"
                anom_params.append(household_id)
                
            cursor.execute(f"""
                SELECT 
                    COALESCE(SUM(diff_kwh), 0.0) as total_excess_kwh,
                    COUNT(*) as anomaly_count
                FROM anomaly_records
                {anom_where};
            """, anom_params)
            anom_row = cursor.fetchone()
            excess_kwh = max(0.0, anom_row["total_excess_kwh"])
            anomaly_count = anom_row["anomaly_count"]

        # Calculations
        current_cost = current_kwh * tariff
        prev_cost = prev_kwh * tariff
        excess_cost = excess_kwh * tariff
        
        # Period comparison percentage
        if prev_kwh > 0:
            kwh_change_pct = ((current_kwh - prev_kwh) / prev_kwh) * 100.0
        else:
            kwh_change_pct = 0.0

        return {
            "period_days": days,
            "tariff_per_kwh": tariff,
            "currency": currency,
            "total_kwh": round(current_kwh, 2),
            "estimated_cost": round(current_cost, 2),
            "prev_period_kwh": round(prev_kwh, 2),
            "prev_period_cost": round(prev_cost, 2),
            "kwh_change_pct": round(kwh_change_pct, 1),
            "excess_kwh": round(excess_kwh, 2),
            "estimated_excess_cost": round(excess_cost, 2),
            "anomaly_count": anomaly_count,
            "disclaimer": "Cost calculation is an estimate based on a configured flat tariff per kWh. Official utility bills may include progressive tiered tariff slabs, standing charges, demand surcharges, and local taxes."
        }

    @classmethod
    def generate_recommendations(cls, household_id=None):
        """
        Synthesizes rule-based conservation recommendations based on consumption data and anomalies.
        Distinguishes measured excess consumption from estimated avoidable wastage.
        """
        tariff = AppConfig.get_tariff()
        currency = AppConfig.get_currency_symbol()
        cost_summary = cls.calculate_cost_summary(household_id=household_id, days=30)
        
        recs = []

        # 1. High overnight consumption check
        with db_session() as conn:
            cursor = conn.cursor()
            query = """
                SELECT AVG(energy_kwh) as night_avg
                FROM consumption_records
                WHERE CAST(SUBSTR(timestamp, 12, 2) AS INTEGER) BETWEEN 1 AND 4
            """
            params = []
            if household_id:
                query += " AND household_id = ?"
                params.append(household_id)
            cursor.execute(query, params)
            night_res = cursor.fetchone()
            night_avg = night_res["night_avg"] if night_res and night_res["night_avg"] else 0.0

        if night_avg > 0.8:
            potential_monthly_savings_kwh = round((night_avg - 0.35) * 4 * 30, 1)
            potential_monthly_savings_val = round(potential_monthly_savings_kwh * tariff, 2)
            recs.append({
                "category": "Overnight Baseload",
                "title": "Investigate Persistent Overnight Baseload",
                "priority": "High",
                "icon": "moon",
                "finding": f"Overnight standby consumption averages {round(night_avg, 2)} kWh/hour between 01:00 and 04:00, which is elevated compared to standard standby benchmarks (~0.35 kWh/h).",
                "recommendation": "Check for unattended water heaters, secondary refrigerators, HVAC running continuously at night, or entertainment electronics left in active mode.",
                "quantified_impact": f"Estimated avoidable consumption: ~{potential_monthly_savings_kwh} kWh/month (~{currency}{potential_monthly_savings_val}/month at current tariff).",
                "note": "Savings are projected approximations assuming reduction to typical benchmark baseload."
            })

        # 2. Frequent Peak Spikes
        if cost_summary["excess_kwh"] > 10.0:
            recs.append({
                "category": "Demand Spikes",
                "title": "Stagger High-Wattage Appliance Operation",
                "priority": "Medium",
                "icon": "zap",
                "finding": f"Detected anomalies contributed approximately {cost_summary['excess_kwh']} kWh in spikes above baseline this month.",
                "recommendation": "Avoid running heavy draw appliances (dryers, dishwashers, electric vehicle chargers, heat pumps) concurrently. Consider timer plugs to spread consumption across off-peak periods.",
                "quantified_impact": f"Associated excess energy cost: ~{currency}{cost_summary['estimated_excess_cost']}.",
                "note": "Represents measured excess over historical baseline, some of which may be legitimate high-need usage."
            })

        # 3. Period-over-period trend
        if cost_summary["kwh_change_pct"] > 15.0:
            recs.append({
                "category": "Usage Trend",
                "title": "Inspect Recent Appliance Additions or Heating/Cooling Changes",
                "priority": "Medium",
                "icon": "trending-up",
                "finding": f"Consumption rose by {cost_summary['kwh_change_pct']}% compared to the previous 30-day period.",
                "recommendation": "Review any newly installed electrical devices or seasonal thermostat adjustments. Verify appliance energy star ratings and clean air conditioner filters.",
                "quantified_impact": f"Net increase: +{round(cost_summary['total_kwh'] - cost_summary['prev_period_kwh'], 1)} kWh (~{currency}{round(cost_summary['estimated_cost'] - cost_summary['prev_period_cost'], 2)}).",
                "note": "Seasonal temperature swings frequently cause legitimate usage variance."
            })

        # 4. Standard Preventive Energy Tip
        recs.append({
            "category": "Preventive Maintenance",
            "title": "Schedule Periodic Appliance & Sensor Audits",
            "priority": "Low",
            "icon": "check-circle",
            "finding": "Regular maintenance prevents slow efficiency degradation in major appliances.",
            "recommendation": "Inspect refrigerator door gaskets for tight seal, clean heat pump coils annually, and ensure smart meter display matches physical breaker box readings.",
            "quantified_impact": "Typical efficiency improvements range between 5% to 12% for serviced refrigeration and cooling systems.",
            "note": "General industry energy efficiency benchmark."
        })

        return recs
