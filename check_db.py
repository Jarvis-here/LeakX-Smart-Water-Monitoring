import sqlite3

connection = sqlite3.connect("leakx.db")
cursor = connection.cursor()

cursor.execute("""
    SELECT
        id, timestamp,
        zone_a_flow, zone_a_pressure, zone_a_status,
        zone_b_flow, zone_b_pressure, zone_b_status,
        zone_c_flow, zone_c_pressure, zone_c_status
    FROM sensor_readings
    ORDER BY id DESC
    LIMIT 50
""")

rows = cursor.fetchall()

print("\n===== LAST 50 TICKS (Zone A / Zone B / Zone C) =====\n")

for row in rows:
    print(row)

print("\n=====================================================\n")

cursor.execute("""
    SELECT COUNT(*)
    FROM sensor_readings
""")

count = cursor.fetchone()[0]

print("Total ticks stored:", count)

connection.close()
