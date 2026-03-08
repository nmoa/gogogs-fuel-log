#!/usr/bin/env python3
"""Lightweight API server that serves fuel_log.csv as JSON for Grafana."""

import csv
import os
from flask import Flask, jsonify

app = Flask(__name__)

CSV_PATH = os.environ.get("CSV_PATH", "/data/fuel_log.csv")


def load_csv():
    """Load fuel_log.csv and return parsed records."""
    records = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip empty rows
            if not row.get("給油日"):
                continue

            date_str = row["給油日"].strip()
            if not date_str:
                continue

            # Parse fuel efficiency — skip non-numeric values
            raw_efficiency = row.get("燃費", "").strip()
            if raw_efficiency in ("-", "追加給油", ""):
                efficiency = None
            else:
                try:
                    efficiency = float(raw_efficiency)
                except ValueError:
                    efficiency = None

            # Parse refuel amount
            try:
                amount = float(row.get("給油量", "0"))
            except ValueError:
                amount = None

            # Parse distance
            raw_distance = row.get("走行距離", "").strip()
            if raw_distance in ("前回未入力", ""):
                distance = None
            else:
                try:
                    distance = float(raw_distance)
                except ValueError:
                    distance = None

            # Parse total mileage
            try:
                total_mileage = int(row.get("総走行距離", "0"))
            except ValueError:
                total_mileage = None

            # Convert date format: 2019/03/24 -> 2019-03-24T00:00:00Z
            iso_date = date_str.replace("/", "-") + "T00:00:00Z"

            records.append({
                "date": iso_date,
                "fuel_efficiency": efficiency,
                "refuel_amount": amount,
                "distance": distance,
                "total_mileage": total_mileage,
                "is_additional": raw_efficiency == "追加給油",
            })
    return records


@app.route("/api/data")
def get_data():
    """Return all fuel log data as JSON array."""
    records = load_csv()
    return jsonify(records)


@app.route("/api/data/efficiency")
def get_efficiency():
    """Return only records with valid fuel efficiency (for cleaner charts)."""
    records = load_csv()
    filtered = [r for r in records if r["fuel_efficiency"] is not None and not r["is_additional"]]
    return jsonify(filtered)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
