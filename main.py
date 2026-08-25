import json
import threading
import time
import os
import hashlib
import hmac
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Query, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from database import (
    create_database,
    add_reading,
    get_all_readings,
    get_latest_per_zone,
    ZONE_SLUGS,
    add_leak_report,
    get_leak_reports,
    update_leak_report_status,
    add_incident_event,
    get_incident_events,
    get_user,
    create_user,
)
from simulator import (
    ZONE_NAMES,
    DEFAULT_ZONE,
    valves,
    generate_zone_values,
    force_leak,
    clear_forced_leak,
    zone_or_default,
    classify,
    EXPECTED_FLOW,
)

# Demo coordinates for the consumer map. Replace these with your real deployment coordinates.
ZONE_LOCATIONS = {
    "Zone A - Main Line": {"lat": 28.6139, "lng": 77.2090},
    "Zone B - North District": {"lat": 28.6260, "lng": 77.2150},
    "Zone C - South District": {"lat": 28.6010, "lng": 77.2050},
}

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="LeakX API", version="10.1")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
SESSION_SECRET = os.getenv("LEAKX_SESSION_SECRET", "leakx-demo-change-this-secret")
SESSION_HTTPS_ONLY = os.getenv("LEAKX_SESSION_HTTPS_ONLY", "false").lower() == "true"
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="leakx_session",
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db_lock = threading.Lock()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"pbkdf2_sha256$120000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt_hex, digest_hex = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def current_user(request: Request):
    username = request.session.get("username")
    if not username:
        return None
    return get_user(username)


def require_role(request: Request, role: str):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    if user["role"] != role:
        raise HTTPException(status_code=403, detail="Access denied")
    return user


def seed_users():
    # Demo accounts for the hackathon prototype. Change these before real deployment.
    create_user("admin", hash_password("admin123"), "admin")
    create_user("customer", hash_password("customer123"), "customer")


def load_dashboard_html() -> str:
    """Read the dashboard template and inject the current zone list."""
    raw = (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")
    zone_options = "\n".join(f'<option value="{z}">{z}</option>' for z in ZONE_NAMES)
    return raw.replace("__ZONE_OPTIONS__", zone_options).replace(
        "__ZONE_NAMES_JSON__", json.dumps(ZONE_NAMES)
    )


DASHBOARD_HTML = load_dashboard_html()
LANDING_HTML = (STATIC_DIR / "landing.html").read_text(encoding="utf-8")
REPORT_HTML = (STATIC_DIR / "report.html").read_text(encoding="utf-8")



def append_tick(timestamp, readings):
    """readings: dict of zone name -> (flow, pressure, status). One DB row per tick."""
    try:
        with db_lock:
            add_reading(timestamp, readings)
    except Exception as e:
        print("Database write error:", e)


def simulator_thread():
    while True:
        time.sleep(2)
        timestamp = datetime.now().strftime("%H:%M:%S")
        readings = {zone: generate_zone_values(zone) for zone in ZONE_NAMES}
        append_tick(timestamp, readings)


def read_sensor_data(zone=None):
    try:
        with db_lock:
            return get_all_readings(zone)
    except Exception:
        return []


def read_latest_per_zone():
    try:
        with db_lock:
            return get_latest_per_zone()
    except Exception:
        return []


@app.get("/", response_class=HTMLResponse)
def landing():
    return LANDING_HTML


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return LANDING_HTML


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = get_user(username.strip())
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    request.session.clear()
    request.session["username"] = user["username"]
    request.session["role"] = user["role"]
    return {"ok": True, "role": user["role"], "redirect": "/dashboard" if user["role"] == "admin" else "/report-leak"}


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True, "redirect": "/"}


@app.get("/me")
def me(request: Request):
    user = current_user(request)
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "username": user["username"], "role": user["role"]}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    require_role(request, "admin")
    return DASHBOARD_HTML


@app.get("/report-leak", response_class=HTMLResponse)
def report_leak_page(request: Request):
    require_role(request, "customer")
    return REPORT_HTML


@app.on_event("startup")
def startup():
    create_database()
    seed_users()

    for _ in range(20):
        timestamp = datetime.now().strftime("%H:%M:%S")
        readings = {zone: generate_zone_values(zone) for zone in ZONE_NAMES}
        append_tick(timestamp, readings)

    threading.Thread(target=simulator_thread, daemon=True).start()


@app.get("/valve")
def valve_status(request: Request, zone: str = Query(default=DEFAULT_ZONE)):
    require_role(request, "admin")
    zone = zone_or_default(zone)
    return {"zone": zone, "valve_closed": valves[zone]["closed"]}


@app.post("/valve/close")
def valve_close(request: Request, zone: str = Query(default=DEFAULT_ZONE)):
    require_role(request, "admin")
    zone = zone_or_default(zone)
    valves[zone]["closed"] = True
    return {
        "zone": zone,
        "valve_closed": True,
        "message": f"Valve closed - flow isolated ({zone})",
    }


@app.post("/valve/open")
def valve_open(request: Request, zone: str = Query(default=DEFAULT_ZONE)):
    require_role(request, "admin")
    zone = zone_or_default(zone)
    valves[zone]["closed"] = False
    return {
        "zone": zone,
        "valve_closed": False,
        "message": f"Valve reopened ({zone})",
    }


@app.get("/report")
def report(request: Request, zone: str = Query(default=DEFAULT_ZONE)):
    require_role(request, "admin")
    zone = zone_or_default(zone)
    data = read_sensor_data(zone)

    lines = ["zone,timestamp,flow_lpm,pressure_psi,status,estimated_loss_lpm"]

    for r in data:
        loss = round(max(0, r["flow"] - EXPECTED_FLOW), 2) if r["status"] == "LEAK" else 0
        lines.append(
            f"{zone},{r['timestamp']},{r['flow']},{r['pressure']},"
            f"{r['status']},{loss}"
        )

    safe_zone = "".join(c if c.isalnum() else "_" for c in zone).strip("_")

    return Response(
        content="\n".join(lines),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=LeakX_report_{safe_zone}.csv"
        },
    )


@app.post("/api/leak-reports")
async def create_leak_report(
    request: Request,
    location: str = Form(...),
    name: str = Form(default=""),
    contact: str = Form(default=""),
    description: str = Form(default=""),
    zone: str = Form(default=""),
    photo: UploadFile | None = File(default=None),
):
    user = current_user(request)
    if not user or user["role"] not in {"customer", "admin"}:
        raise HTTPException(status_code=401, detail="Login required")

    location = location.strip()
    if not location:
        raise HTTPException(status_code=400, detail="Location is required.")

    image_filename = None
    if photo and photo.filename:
        allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if photo.content_type not in allowed:
            raise HTTPException(status_code=400, detail="Please upload a JPG, PNG, WEBP, or GIF image.")

        suffix = Path(photo.filename).suffix.lower()
        safe_name = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{suffix}"
        target = UPLOAD_DIR / safe_name
        content = await photo.read()
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Photo must be 8 MB or smaller.")
        target.write_bytes(content)
        image_filename = safe_name

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_id = add_leak_report(
        timestamp=timestamp,
        name=name.strip(),
        contact=contact.strip(),
        location=location,
        description=description.strip(),
        image_filename=image_filename,
        reporter_username=user["username"],
        zone=zone_or_default(zone) if zone.strip() else None,
    )
    add_incident_event(report_id, timestamp, "REPORT_SUBMITTED", user["username"], "Citizen leak report received")
    return {
        "ok": True,
        "id": report_id,
        "message": "Leak report submitted.",
    }


@app.get("/api/leak-reports")
def leak_reports(request: Request):
    require_role(request, "admin")
    reports = get_leak_reports(50)
    for report in reports:
        report["image_url"] = (f"/report-image/{report['image_filename']}" if report.get("image_filename") else None)
        report["events"] = get_incident_events(report["id"])
    return {"count": len(reports), "reports": reports}


@app.post("/api/leak-reports/{report_id}/status")
def set_report_status(request: Request, report_id: int, status: str = Form(...)):
    user = require_role(request, "admin")
    allowed = {"NEW", "INVESTIGATING", "RESOLVED"}
    status = status.upper().strip()
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid incident status")
    changed = update_leak_report_status(report_id, status)
    if not changed:
        raise HTTPException(status_code=404, detail="Incident not found")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    add_incident_event(report_id, now, "STATUS_CHANGED", user["username"], f"Incident status changed to {status}")
    return {"ok": True, "status": status}


@app.post("/api/leak-reports/{report_id}/valve")
def report_valve_action(request: Request, report_id: int, action: str = Form(...), zone: str = Form(default=DEFAULT_ZONE)):
    user = require_role(request, "admin")
    zone = zone_or_default(zone)
    action = action.lower().strip()
    if action not in {"close", "open"}:
        raise HTTPException(status_code=400, detail="Invalid valve action")
    valves[zone]["closed"] = action == "close"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    event = "VALVE_CLOSED" if action == "close" else "VALVE_OPENED"
    add_incident_event(report_id, now, event, user["username"], f"Valve {'closed' if action == 'close' else 'reopened'} for {zone}")
    return {"ok": True, "valve_closed": valves[zone]["closed"], "zone": zone}


@app.post("/api/demo/leak")
def demo_leak(request: Request, zone: str = Form(default=DEFAULT_ZONE)):
    require_role(request, "admin")
    zone = zone_or_default(zone)
    force_leak(zone)
    return {"ok": True, "zone": zone, "message": "Demo leak triggered"}


@app.post("/api/demo/reset")
def demo_reset(request: Request, zone: str = Form(default=DEFAULT_ZONE)):
    require_role(request, "admin")
    zone = zone_or_default(zone)
    clear_forced_leak(zone)
    return {"ok": True, "zone": zone, "message": "Demo leak reset"}


@app.get("/report-image/{filename}")
def report_image(request: Request, filename: str):
    require_role(request, "admin")
    safe = Path(filename).name
    target = UPLOAD_DIR / safe
    if not target.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=target.read_bytes(), media_type="image/*")


@app.get("/status")
def system_status(request: Request):
    require_role(request, "admin")
    return {
        "system": "LeakX",
        "status": "online",
        "database": "SQLite",
        "version": "10.1",
    }


@app.get("/latest")
def latest_reading(request: Request, zone: str = Query(default=DEFAULT_ZONE)):
    require_role(request, "admin")
    zone = zone_or_default(zone)
    data = read_sensor_data(zone)

    if not data:
        return {"message": "No sensor data available"}

    return data[-1]


@app.get("/readings")
def all_readings(request: Request, zone: str = Query(default=DEFAULT_ZONE)):
    require_role(request, "admin")
    zone = zone_or_default(zone)
    data = read_sensor_data(zone)

    return {
        "count": len(data),
        "readings": data,
    }


@app.get("/alerts")
def alerts(request: Request, zone: str = Query(default=DEFAULT_ZONE)):
    require_role(request, "admin")
    zone = zone_or_default(zone)
    data = read_sensor_data(zone)

    leak_readings = []

    for reading in data:
        if reading["status"] == "LEAK":
            excess_flow = max(0, reading["flow"] - EXPECTED_FLOW)
            leak_readings.append(
                {
                    "timestamp": reading["timestamp"],
                    "flow": reading["flow"],
                    "pressure": reading["pressure"],
                    "estimated_loss_lpm": round(excess_flow, 2),
                    "severity": "HIGH",
                }
            )

    return {
        "total_alerts": len(leak_readings),
        "alerts": leak_readings,
    }


@app.get("/water-loss")
def water_loss(request: Request, zone: str = Query(default=DEFAULT_ZONE)):
    require_role(request, "admin")
    zone = zone_or_default(zone)
    data = read_sensor_data(zone)

    total_loss = 0
    leak_readings = 0

    for reading in data:
        if reading["status"] == "LEAK":
            excess_flow = max(0, reading["flow"] - EXPECTED_FLOW)
            total_loss += excess_flow / 30
            leak_readings += 1

    return {
        "estimated_water_loss_liters": round(total_loss, 2),
        "leak_readings": leak_readings,
        "unit": "liters",
    }


@app.get("/public/zones")
def public_zones():
    latest_rows = {row["zone"]: row for row in read_latest_per_zone()}
    result = []
    for name in ZONE_NAMES:
        row = latest_rows.get(name)
        if not row:
            continue
        zone_status, priority = classify(row["flow"], row["status"])
        location = ZONE_LOCATIONS.get(name, {"lat": 0, "lng": 0})
        result.append({
            "zone": name,
            "status": zone_status,
            "flow": row["flow"],
            "pressure": row["pressure"],
            "priority": priority,
            "lat": location["lat"],
            "lng": location["lng"],
            "demo_coordinates": True,
        })
    return {"zones": result, "map_note": "Demo coordinates — replace ZONE_LOCATIONS with your real zone coordinates."}


@app.get("/zones")
def zones(request: Request):
    require_role(request, "admin")
    latest_rows = {row["zone"]: row for row in read_latest_per_zone()}
    result = []

    for name in ZONE_NAMES:
        row = latest_rows.get(name)
        if not row:
            continue
        zone_status, priority = classify(row["flow"], row["status"])
        result.append(
            {
                "zone": name,
                "status": zone_status,
                "flow": row["flow"],
                "pressure": row["pressure"],
                "priority": priority,
            }
        )

    return {"zones": result}


if __name__ == "__main__":
    import uvicorn

    print("LeakX V10.1 SQLite → http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
