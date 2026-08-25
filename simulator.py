import random

from database import ZONE_SLUGS

EXPECTED_FLOW = 7.0


ZONE_NAMES = list(ZONE_SLUGS.keys())
DEFAULT_ZONE = ZONE_NAMES[0]

valves = {name: {"closed": False} for name in ZONE_NAMES}
zone_counters = {name: idx * 5 for idx, name in enumerate(ZONE_NAMES)}
forced_leaks = {name: False for name in ZONE_NAMES}


def zone_or_default(zone: str) -> str:
    return zone if zone in valves else DEFAULT_ZONE


def generate_zone_values(zone):
    """Returns (flow, pressure, status) for one zone for the current tick."""
    if valves[zone]["closed"]:
        return (
            round(random.uniform(0.3, 1.0), 1),
            round(random.uniform(48.0, 52.0), 1),
            "NORMAL",
        )

    zone_counters[zone] += 1
    phase = zone_counters[zone] % 15

    if forced_leaks[zone] or 10 <= phase < 15:
        flow = round(random.uniform(12.5, 14.5), 1)
        pressure = round(random.uniform(26.0, 29.0), 1)
        status = "LEAK"
    else:
        flow = round(random.uniform(6.5, 8.5), 1)
        pressure = round(random.uniform(38.0, 42.0), 1)
        status = "NORMAL"

    return flow, pressure, status


def classify(flow, status):
    if status == "LEAK":
        return "CRITICAL", "HIGH"
    elif flow > EXPECTED_FLOW:
        return "WARNING", "MEDIUM"
    else:
        return "NORMAL", "LOW"


def force_leak(zone):
    forced_leaks[zone] = True


def clear_forced_leak(zone):
    forced_leaks[zone] = False
