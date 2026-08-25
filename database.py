import sqlite3

DATABASE = "leakx.db"

ZONE_SLUGS = {
    "Zone A - Main Line": "zone_a",
    "Zone B - North District": "zone_b",
    "Zone C - South District": "zone_c",
}
DEFAULT_ZONE = "Zone A - Main Line"


def get_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def _wide_columns_sql():
    parts = []
    for slug in ZONE_SLUGS.values():
        parts.append(f"{slug}_flow REAL")
        parts.append(f"{slug}_pressure REAL")
        parts.append(f"{slug}_status TEXT")
    return ",\n            ".join(parts)


def _insert_wide_row(cursor, timestamp, values):
    columns = ["timestamp"] + list(values.keys())
    placeholders = ", ".join("?" for _ in columns)
    col_list = ", ".join(columns)
    params = [timestamp] + list(values.values())
    cursor.execute(
        f"INSERT INTO sensor_readings ({col_list}) VALUES ({placeholders})",
        params,
    )


def create_database():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            {_wide_columns_sql()}
        )
    """)
    connection.commit()

    cursor.execute("PRAGMA table_info(sensor_readings)")
    columns = [row[1] for row in cursor.fetchall()]

    # CREATE TABLE IF NOT EXISTS is a no-op if an older-schema table already
    # exists, so if the wide columns aren't there yet, migrate it.
    if "zone_a_flow" not in columns:
        _migrate_legacy_schema(connection, cursor, columns)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leak_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            name TEXT,
            contact TEXT,
            location TEXT NOT NULL,
            description TEXT,
            image_filename TEXT,
            status TEXT NOT NULL DEFAULT 'NEW',
            zone TEXT
        )
    """)
    connection.commit()

    # Add reporter_username to older leak_reports tables if necessary.
    cursor.execute("PRAGMA table_info(leak_reports)")
    leak_columns = [row[1] for row in cursor.fetchall()]
    if "reporter_username" not in leak_columns:
        cursor.execute("ALTER TABLE leak_reports ADD COLUMN reporter_username TEXT")
        connection.commit()
    if "zone" not in leak_columns:
        cursor.execute("ALTER TABLE leak_reports ADD COLUMN zone TEXT")
        connection.commit()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incident_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            event TEXT NOT NULL,
            actor TEXT,
            details TEXT
        )
    """)
    connection.commit()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('customer','admin'))
        )
    """)
    connection.commit()

    connection.close()


def _migrate_legacy_schema(connection, cursor, old_columns):
    cursor.execute("ALTER TABLE sensor_readings RENAME TO sensor_readings_legacy")
    cursor.execute(f"""
        CREATE TABLE sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            {_wide_columns_sql()}
        )
    """)
    connection.commit()

    cursor.execute("SELECT * FROM sensor_readings_legacy ORDER BY id ASC")
    legacy_rows = [
        dict(zip([d[0] for d in cursor.description], row))
        for row in cursor.fetchall()
    ]

    if "zone" in old_columns:
        # Previous long-format schema: one row per zone per tick.
        per_zone = {name: [] for name in ZONE_SLUGS}
        for row in legacy_rows:
            zone_name = row.get("zone") or DEFAULT_ZONE
            per_zone.setdefault(zone_name, []).append(row)

        max_len = max((len(rows) for rows in per_zone.values()), default=0)

        for i in range(max_len):
            timestamp = None
            values = {}
            for zone_name, slug in ZONE_SLUGS.items():
                rows = per_zone.get(zone_name, [])
                if i < len(rows):
                    r = rows[i]
                    values[f"{slug}_flow"] = r["flow"]
                    values[f"{slug}_pressure"] = r["pressure"]
                    values[f"{slug}_status"] = r["status"]
                    if timestamp is None:
                        timestamp = r["timestamp"]
                else:
                    values[f"{slug}_flow"] = None
                    values[f"{slug}_pressure"] = None
                    values[f"{slug}_status"] = None
            _insert_wide_row(cursor, timestamp or "", values)
    else:
        # Original single-zone schema (id, timestamp, flow, pressure, status):
        # every existing row becomes a Zone A reading.
        for r in legacy_rows:
            values = {}
            for slug in ZONE_SLUGS.values():
                values[f"{slug}_flow"] = None
                values[f"{slug}_pressure"] = None
                values[f"{slug}_status"] = None
            zone_a_slug = ZONE_SLUGS[DEFAULT_ZONE]
            values[f"{zone_a_slug}_flow"] = r["flow"]
            values[f"{zone_a_slug}_pressure"] = r["pressure"]
            values[f"{zone_a_slug}_status"] = r["status"]
            _insert_wide_row(cursor, r["timestamp"], values)

    cursor.execute("DROP TABLE sensor_readings_legacy")
    connection.commit()


def add_reading(timestamp, readings):
    """
    readings: dict mapping zone name -> (flow, pressure, status).
    Writes ONE row for this tick, with each zone's values in its own columns.
    Zones not present in `readings` are stored as NULL for this row.
    """
    connection = get_connection()
    cursor = connection.cursor()

    values = {}
    for zone_name, slug in ZONE_SLUGS.items():
        flow, pressure, status = readings.get(zone_name, (None, None, None))
        values[f"{slug}_flow"] = flow
        values[f"{slug}_pressure"] = pressure
        values[f"{slug}_status"] = status

    _insert_wide_row(cursor, timestamp, values)

    connection.commit()
    connection.close()


def get_all_readings(zone=None):
    connection = get_connection()
    cursor = connection.cursor()

    if zone:
        if zone not in ZONE_SLUGS:
            connection.close()
            return []
        slug = ZONE_SLUGS[zone]
        cursor.execute(f"""
            SELECT
                timestamp,
                {slug}_flow AS flow,
                {slug}_pressure AS pressure,
                {slug}_status AS status
            FROM sensor_readings
            WHERE {slug}_status IS NOT NULL
            ORDER BY id ASC
        """)
    else:
        cursor.execute("SELECT * FROM sensor_readings ORDER BY id ASC")

    rows = cursor.fetchall()
    connection.close()

    return [dict(row) for row in rows]


def get_latest_per_zone():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    connection.close()

    if not row:
        return []

    row = dict(row)
    result = []
    for zone_name, slug in ZONE_SLUGS.items():
        status = row.get(f"{slug}_status")
        if status is None:
            continue
        result.append({
            "zone": zone_name,
            "timestamp": row["timestamp"],
            "flow": row.get(f"{slug}_flow"),
            "pressure": row.get(f"{slug}_pressure"),
            "status": status,
        })

    return result


def add_leak_report(timestamp, name, contact, location, description, image_filename, reporter_username=None, zone=None):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO leak_reports
        (timestamp, name, contact, location, description, image_filename, status, reporter_username, zone)
        VALUES (?, ?, ?, ?, ?, ?, 'NEW', ?, ?)
        """,
        (timestamp, name, contact, location, description, image_filename, reporter_username, zone),
    )
    report_id = cursor.lastrowid
    connection.commit()
    connection.close()
    return report_id


def get_leak_reports(limit=50):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT id, timestamp, name, contact, location, description,
               image_filename, status, reporter_username, zone
        FROM leak_reports
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return rows


def update_leak_report_status(report_id, status):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("UPDATE leak_reports SET status=? WHERE id=?", (status, report_id))
    changed = cursor.rowcount
    connection.commit()
    connection.close()
    return changed


def add_incident_event(report_id, timestamp, event, actor, details=""):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO incident_events (report_id, timestamp, event, actor, details) VALUES (?, ?, ?, ?, ?)",
        (report_id, timestamp, event, actor, details),
    )
    connection.commit()
    connection.close()


def get_incident_events(report_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id, timestamp, event, actor, details FROM incident_events WHERE report_id=? ORDER BY id ASC",
        (report_id,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return rows


def get_user(username):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id, username, password_hash, role FROM users WHERE username = ?",
        (username,),
    )
    row = cursor.fetchone()
    connection.close()
    return dict(row) if row else None


def create_user(username, password_hash, role):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, password_hash, role),
    )
    connection.commit()
    connection.close()
