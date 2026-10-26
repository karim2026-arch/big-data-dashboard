#!/usr/bin/env python3
"""
Fleet Telematics Lakehouse - SAMPLE DATA GENERATOR (demo size)
================================================================
Purpose : show teammates what the data looks like (about 100 telemetry rows),
          NOT the production generator (that one streams 5,000 vehicles to Kafka/Kinesis).

What it writes (CSV per table + one Excel workbook):
  raw/     bronze + source tables exactly as they would land (dirty on purpose)
  silver/  cleaned / deduplicated / typed / enriched tables
  gold/    star schema (dimensions + facts + aggregate)
  ops/     DLQ, ingestion log, data-quality results, anomaly ground truth,
           and a detection-vs-truth reconciliation

Run:
  pip install pandas faker openpyxl
  python generate_fleet_sample.py                       # ~100 telemetry rows
  python generate_fleet_sample.py --telemetry-rows 300 --seed 7

IMPORTANT HONESTY NOTES
  * Weather is SYNTHETIC here (offline). In the real project it comes from Open-Meteo.
  * Road geometry is an APPROXIMATE polyline (a few waypoints, densified).
    In the real project it comes from OpenStreetMap (OSMnx / Overpass).
  * Sample interval is 10 minutes so ~100 rows still cover whole trips.
    The real generator uses 5-10 seconds. Harsh-braking and idling thresholds
    are therefore only illustrative at this interval.
  * Thresholds (cold chain, idling, deviation, on-time grace) are simulation
    assumptions, not regulatory values. Anomaly flags are synthetic patterns.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import random
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

try:
    from faker import Faker
except ImportError:  # the script still works without Faker
    Faker = None

# ----------------------------------------------------------------------------
# Config (assumptions: document them in your README)
# ----------------------------------------------------------------------------
SIM_DAY = datetime(2026, 11, 2)
RUN_TS = datetime(2026, 11, 2, 23, 0, 0)
SEG_KM = 10.0                 # road segment length used for the sample polyline
DEVIATION_M = 1000.0          # distance from road that counts as route deviation
IDLE_MIN_READINGS = 2         # consecutive readings (speed 0, rpm > 0) = idling event
ON_TIME_GRACE_MIN = 15        # delivery within promised time + grace = on time
PRICE_TOLERANCE = 0.05        # card price vs official price
SPEED_TOLERANCE_KMH = 5       # over the limit by more than this = speeding event
HARSH_BRAKE_DROP_KMH = 40     # speed drop between consecutive readings
FIRST_DAY = date(2026, 1, 1)

REGIONS = [  # weather regions (id, name, lat, lon, governorate, base temp C)
    ("W-CAI", "Greater Cairo", 30.04, 31.24, "Cairo", 24.0),
    ("W-ALX", "Alexandria", 31.20, 29.92, "Alexandria", 22.0),
    ("W-SUZ", "Suez / Ain Sokhna", 29.97, 32.55, "Suez", 25.0),
    ("W-AST", "Assiut", 27.18, 31.18, "Assiut", 25.0),
]

FIXED_LOCATIONS = [  # (location_id, osm_id, name, type, lat, lon, addr_state)
    ("L-010", 5581000001, "Cairo Distribution Hub", "warehouse", 30.0444, 31.2357, "Cairo"),
    ("L-011", 5581000002, "Alexandria Cold Store", "warehouse", 31.2001, 29.9187, "Alexandria"),
    ("L-012", 5581000003, "Ain Sokhna Port Gate", "port", 29.6000, 32.3500, None),
    ("L-013", 5581000004, "Assiut Distribution Center", "warehouse", 27.1809, 31.1837, "Assiut"),
]

CORRIDOR_CFG = {  # APPROXIMATE waypoints - replace with OSM geometry in the real project
    "R-01": dict(name="Cairo - Alexandria (Desert Road)", road="Cairo-Alexandria Desert Road",
                 origin="L-010", dest="L-011", highway="motorway", expected_min=170,
                 waypoints=[(30.0444, 31.2357), (30.15, 30.90), (30.40, 30.30),
                            (30.85, 30.10), (31.2001, 29.9187)]),
    "R-02": dict(name="Cairo - Ain Sokhna Port", road="Cairo-Ain Sokhna Road",
                 origin="L-010", dest="L-012", highway="trunk", expected_min=100,
                 waypoints=[(30.0444, 31.2357), (29.98, 31.70), (29.80, 32.15), (29.6000, 32.3500)]),
    "R-03": dict(name="Cairo - Assiut", road="Cairo-Assiut Western Road",
                 origin="L-010", dest="L-013", highway="trunk", expected_min=330,
                 waypoints=[(30.0444, 31.2357), (29.07, 31.10), (28.11, 30.75), (27.1809, 31.1837)]),
}
ROUTE_WEIGHTS = {"R-01": 0.45, "R-02": 0.40, "R-03": 0.15}
HIGHWAY_DEFAULT_LIMIT = {"motorway": 100, "trunk": 90}

PRODUCTS = [  # (product_id, name, category, temp_min_c, temp_max_c)
    ("P-0001", "Insulin Vials", "Pharma", 2.0, 8.0),
    ("P-0002", "Vaccines", "Pharma", 2.0, 8.0),
    ("P-0003", "Fresh Dairy", "Food", 1.0, 6.0),
    ("P-0004", "Chilled Meat", "Food", 0.0, 5.0),
    ("P-0005", "Fresh Produce", "Food", 2.0, 8.0),
    ("P-0006", "Frozen Chicken", "Frozen Food", -22.0, -18.0),
    ("P-0007", "Frozen Seafood", "Frozen Food", -25.0, -18.0),
    ("P-0008", "Ice Cream", "Frozen Food", -25.0, -18.0),
    ("P-0009", "Packaged Dry Goods", "Ambient", None, None),
    ("P-0010", "Electronics", "Ambient", None, None),
    ("P-0011", "Bottled Water", "Ambient", None, None),
]
ZONE_WEIGHTS = {"AMBIENT": 0.35, "CHILLED": 0.25, "FROZEN": 0.20, "PHARMA_COLD": 0.20}


def zone_of(category, tmin, tmax):
    if tmax is None or (isinstance(tmax, float) and math.isnan(tmax)):
        return "AMBIENT"
    if tmax < 0:
        return "FROZEN"
    if category == "Pharma":
        return "PHARMA_COLD"
    return "CHILLED"


# ----------------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def point_segment_m(lat, lon, a, b):
    """Distance in meters from a point to segment a-b (local equirectangular plane)."""
    kx = math.cos(math.radians(lat)) * 111320.0
    ky = 110540.0
    ax, ay = (a[1] - lon) * kx, (a[0] - lat) * ky
    bx, by = (b[1] - lon) * kx, (b[0] - lat) * ky
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
    return math.hypot(ax + t * dx, ay + t * dy)


class Corridor:
    def __init__(self, route_id, cfg):
        self.route_id, self.cfg = route_id, cfg
        wp, pts = cfg["waypoints"], []
        for a, b in zip(wp[:-1], wp[1:]):
            n = max(1, math.ceil(haversine_km(*a, *b) / SEG_KM))
            for i in range(n):
                f = i / n
                pts.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
        pts.append(wp[-1])
        self.points = pts
        self.cum = [0.0]
        for p, q in zip(pts[:-1], pts[1:]):
            self.cum.append(self.cum[-1] + haversine_km(*p, *q))
        self.length_km = self.cum[-1]

    def _seg(self, d):
        d = max(0.0, min(self.length_km, d))
        i = min(bisect.bisect_right(self.cum, d) - 1, len(self.points) - 2)
        return d, i

    def pos_at(self, d):
        d, i = self._seg(d)
        span = self.cum[i + 1] - self.cum[i]
        f = 0 if span == 0 else (d - self.cum[i]) / span
        p, q = self.points[i], self.points[i + 1]
        return p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f

    def bearing_at(self, d):
        _, i = self._seg(d)
        p, q = self.points[i], self.points[i + 1]
        return math.atan2((q[1] - p[1]) * math.cos(math.radians(p[0])), q[0] - p[0])

    def segments(self):
        for i in range(len(self.points) - 1):
            yield i + 1, self.points[i], self.points[i + 1], (self.cum[i + 1] - self.cum[i]) * 1000


def iso(ts):
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def dkey(d):
    return int(pd.Timestamp(d).strftime("%Y%m%d"))


def pit(left, id_col, ts_col, dim, dim_id_col, key_col):
    """Point-in-time SCD2 lookup: the dimension version valid at the event time."""
    d = dim[[dim_id_col, "valid_from", key_col]].rename(columns={dim_id_col: id_col}).copy()
    d["valid_from"] = d["valid_from"].astype("datetime64[ns]")
    l = left[[id_col, ts_col]].copy()
    l[ts_col] = pd.to_datetime(l[ts_col]).astype("datetime64[ns]")
    l["_pos"] = np.arange(len(l))
    m = pd.merge_asof(l.sort_values(ts_col), d.sort_values("valid_from"),
                      left_on=ts_col, right_on="valid_from", by=id_col, direction="backward")
    return m.sort_values("_pos")[key_col].to_numpy()


# ----------------------------------------------------------------------------
# Generator
# ----------------------------------------------------------------------------
class FleetSample:
    def __init__(self, args):
        self.a = args
        random.seed(args.seed)
        np.random.seed(args.seed)
        self.fake = Faker("en_US") if Faker else None
        if self.fake:
            Faker.seed(args.seed)
        self.interval = args.interval_sec
        self.corr = {rid: Corridor(rid, cfg) for rid, cfg in CORRIDOR_CFG.items()}
        self.labels, self.raw, self.silver, self.gold, self.ops = [], {}, {}, {}, {}
        self.cnt = {"evt": 0, "rf": 0}

    # ---- small utils --------------------------------------------------------
    def name(self):
        if self.fake:
            return self.fake.name()
        return random.choice(["Karim Fouad", "Omar Hassan", "Youssef Adel", "Ahmed Samir", "Mostafa Nabil"])

    def company(self):
        return self.fake.company() if self.fake else f"Company {random.randint(100, 999)}"

    # ---- 1. reference/source tables ---------------------------------------
    def build_reference(self):
        # weather (SYNTHETIC; real: Open-Meteo)
        rows = []
        for rid, _, lat, lon, _, base in REGIONS:
            for h in range(24):
                temp = base + 5 * math.cos(2 * math.pi * (h - 14) / 24) + random.gauss(0, 0.4)
                rows.append(dict(request_region=rid, latitude=lat, longitude=lon,
                                 time=(SIM_DAY + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M"),
                                 temperature_2m=round(temp, 1),
                                 relative_humidity_2m=int(max(20, min(95, 58 - 12 * math.cos(2 * math.pi * (h - 14) / 24) + random.gauss(0, 4)))),
                                 precipitation=0.2 if (rid == "W-ALX" and h in (7, 8)) else 0.0,
                                 wind_speed_10m=round(abs(random.gauss(14, 4)), 1),
                                 weather_code=random.choice([0, 1, 1, 2, 3]),
                                 fetched_at=iso(RUN_TS)))
        self.raw["raw_weather_api"] = pd.DataFrame(rows)
        self.weather = {(r["request_region"], int(r["time"][11:13])): r["temperature_2m"] for r in rows}

        # corridors config + OSM-like roads and places
        cfg_rows, road_rows, way_id = [], [], 100000000
        for rid, cfg in CORRIDOR_CFG.items():
            orig = next(x for x in FIXED_LOCATIONS if x[0] == cfg["origin"])
            dest = next(x for x in FIXED_LOCATIONS if x[0] == cfg["dest"])
            cfg_rows.append(dict(route_id=rid, route_name=cfg["name"], road_name=cfg["road"],
                                 origin_osm_id=orig[1], dest_osm_id=dest[1], waypoints="[]",
                                 expected_duration_min=cfg["expected_min"]))
            for seq, p, q, length_m in self.corr[rid].segments():
                way_id += 1
                maxspeed = None if random.random() < 0.2 else str(HIGHWAY_DEFAULT_LIMIT[cfg["highway"]])
                road_rows.append(dict(osm_way_id=way_id, name=cfg["road"], highway_type=cfg["highway"],
                                      maxspeed=maxspeed, lanes=3 if cfg["highway"] == "motorway" else 2,
                                      geometry_wkt=f"LINESTRING({p[1]:.5f} {p[0]:.5f}, {q[1]:.5f} {q[0]:.5f})"))
        self.raw["cfg_corridors"] = pd.DataFrame(cfg_rows)
        self.raw["raw_osm_roads"] = pd.DataFrame(road_rows)

        places = [dict(osm_id=o, name=n, place_type=t, lat=la, lon=lo, addr_state=st)
                  for (_, o, n, t, la, lo, st) in FIXED_LOCATIONS]
        loc_map = [dict(location_id=lid, osm_id=o) for (lid, o, *_rest) in FIXED_LOCATIONS]
        stations, k = [], 0
        for rid, c in self.corr.items():
            for f in (0.2, 0.4, 0.6, 0.8):
                k += 1
                lat, lon = c.pos_at(c.length_km * f)
                osm_id = 4470000000 + k
                places.append(dict(osm_id=osm_id, name=f"Fuel Station {rid}-{int(f * 10)}", place_type="fuel",
                                   lat=round(lat + 0.001, 5), lon=round(lon + 0.001, 5),
                                   addr_state=None if k % 3 == 0 else "Cairo"))
                loc_map.append(dict(location_id=f"L-{20 + k:03d}", osm_id=osm_id))
                stations.append(osm_id)
        self.stations = stations
        self.raw["raw_osm_places"] = pd.DataFrame(places)
        self.raw["cfg_location_map"] = pd.DataFrame(loc_map)

        self.raw["raw_fuel_prices"] = pd.DataFrame([
            dict(effective_date="2026-08-01", fuel_type="Diesel", price_per_l_egp=13.75, source_note="sample value"),
            dict(effective_date="2026-09-01", fuel_type="Diesel", price_per_l_egp=14.50, source_note="sample value"),
            dict(effective_date="2026-10-01", fuel_type="Diesel", price_per_l_egp=15.50, source_note="sample value"),
        ])
        hol = [("2026-01-07", "Coptic Christmas"), ("2026-01-25", "Revolution Day"), ("2026-04-25", "Sinai Liberation Day"),
               ("2026-05-01", "Labour Day"), ("2026-06-30", "June 30 Revolution"), ("2026-07-23", "Revolution Day (July 23)"),
               ("2026-10-06", "Armed Forces Day")]
        self.raw["raw_public_holidays"] = pd.DataFrame(
            [dict(date=d, local_name="", name=n, country_code="EG") for d, n in hol])

        self.raw["raw_products"] = pd.DataFrame(
            [dict(product_id=p[0], product_name=p[1], category=p[2], temp_min_c=p[3], temp_max_c=p[4]) for p in PRODUCTS])
        self.prod_zone = {p[0]: zone_of(p[2], p[3], p[4]) for p in PRODUCTS}

    def build_people_assets(self):
        n = self.a.vehicles
        used_plates, veh, snaps = set(), [], []
        for i in range(1, n + 1):
            while True:
                plate = "".join(random.choices("ABCDEFGHJKLMNPRSTUVXYZ", k=3)) + f" {random.randint(1000, 9999)}"
                if plate not in used_plates:
                    used_plates.add(plate)
                    break
            reefer = random.random() < 0.7
            veh.append(dict(vehicle_id=f"VH-{i:05d}", plate_no=plate,
                            vehicle_type="Reefer Truck 10T" if reefer else "Dry Van 12T",
                            reefer_unit_id=f"RF-{i:04d}" if reefer else None,
                            home_depot=random.choice(["Cairo-6Oct", "Cairo-Nasr City", "Alexandria-Borg El Arab"]),
                            base_odo=random.randint(60000, 220000)))
        self.vehicles = veh
        self.odo_base = {v["vehicle_id"]: v["base_odo"] for v in veh}

        # maintenance orders -> status timeline (kept consistent with trips)
        orders, wo = [], 30000
        for v in veh:
            for _ in range(random.choice([0, 1, 1, 2])):
                opened = date(2026, 3, 1) + timedelta(days=random.randint(0, 220))
                closed = opened + timedelta(days=random.randint(1, 4))
                if any(abs((opened - o["opened_date"]).days) < 12 for o in orders if o["vehicle_id"] == v["vehicle_id"]):
                    continue
                if closed >= SIM_DAY.date() - timedelta(days=1):
                    continue
                wo += 1
                mt = random.choice(["Oil & Filter", "Brake Service", "Tire Replacement", "Engine Diagnostics", "Suspension"]
                                   + (["Refrigeration Repair"] if v["reefer_unit_id"] else []))
                orders.append(dict(work_order_id=f"WO-{wo}", vehicle_id=v["vehicle_id"], opened_date=opened, closed_date=closed,
                                   maint_type=mt, cost_egp=round(random.uniform(1500, 15000), 2),
                                   odometer_km=float(self.odo_base[v["vehicle_id"]] - (SIM_DAY.date() - opened).days * 350),
                                   vehicle_status_after="Active"))
        # forced: VH-00003 is still in the workshop on the simulation day (open order)
        wo += 1
        opened = SIM_DAY.date() - timedelta(days=1)
        orders = [o for o in orders if o["vehicle_id"] != "VH-00003"]
        orders.append(dict(work_order_id=f"WO-{wo}", vehicle_id="VH-00003", opened_date=opened, closed_date=None,
                           maint_type="Engine Diagnostics", cost_egp=None,
                           odometer_km=float(self.odo_base["VH-00003"] - 350), vehicle_status_after=None))
        self.orders = orders
        for v in veh:
            snaps.append((v, FIRST_DAY, "Active"))
        for o in orders:
            v = next(x for x in veh if x["vehicle_id"] == o["vehicle_id"])
            snaps.append((v, o["opened_date"], "In Maintenance"))
            if o["closed_date"]:
                snaps.append((v, o["closed_date"], "Active"))
        self.raw["raw_vehicles"] = pd.DataFrame([
            dict(vehicle_id=v["vehicle_id"], plate_no=v["plate_no"], vehicle_type=v["vehicle_type"],
                 reefer_unit_id=v["reefer_unit_id"], fleet_status=st, home_depot=v["home_depot"],
                 snapshot_date=d.isoformat()) for v, d, st in snaps]).sort_values(["vehicle_id", "snapshot_date"]).reset_index(drop=True)
        self.raw["raw_maintenance_orders"] = pd.DataFrame(orders).assign(
            opened_date=lambda d: d["opened_date"].astype(str),
            closed_date=lambda d: d["closed_date"].map(lambda x: None if x is None or pd.isna(x) else str(x)))

        # drivers (3 are "aggressive": they cruise over the speed limit)
        drivers, dsn = [], []
        for i in range(1, max(15, self.a.vehicles) + 1):   # at least one driver per vehicle
            d = dict(driver_id=f"D-{100 + i:04d}", full_name=self.name(), license_class="Heavy",
                     hire_date=(date(2019, 1, 1) + timedelta(days=random.randint(0, 2000))).isoformat())
            drivers.append(d)
            dsn.append(dict(**d, shift="Day", snapshot_date=FIRST_DAY.isoformat(), employment_status="ACTIVE"))
        for d in random.sample(drivers, 4):  # shift change -> SCD2 history
            dsn.append(dict(**d, shift="Night", snapshot_date=(date(2026, 4, 1) + timedelta(days=random.randint(0, 150))).isoformat(),
                            employment_status="ACTIVE"))
        self.drivers = drivers
        self.aggressive = {d["driver_id"]: True for d in random.sample(drivers, 3)}
        self.raw["raw_drivers"] = pd.DataFrame(dsn).sort_values(["driver_id", "snapshot_date"]).reset_index(drop=True)

        cust = []
        for i in range(1, 21):
            seg = random.choice(["Retail", "Pharma", "Food Service", "Wholesale"])
            city = random.choice(["Cairo", "Alexandria", "Assiut", "Suez", "Giza"])
            tier = random.choice(["Gold", "Silver", "Platinum"])
            if random.random() < 0.3:
                seg = seg.lower()
            if random.random() < 0.3:
                city += " "
            if random.random() < 0.3:
                tier = tier.lower()
            cust.append(dict(customer_id=f"C-{30 + i:04d}", customer_name=self.company(), segment=seg, city=city,
                             contract_tier=tier, created_at=(date(2023, 1, 1) + timedelta(days=random.randint(0, 1000))).isoformat()))
        self.raw["raw_customers"] = pd.DataFrame(cust)

    # ---- 2. trips + streams -------------------------------------------------
    def status_at(self, vid, ts):
        snaps = self.raw["raw_vehicles"]
        s = snaps[(snaps.vehicle_id == vid) & (pd.to_datetime(snaps.snapshot_date) <= pd.Timestamp(ts))]
        return s.iloc[-1]["fleet_status"] if len(s) else None

    def ambient_at(self, lat, lon, ts):
        reg = min(REGIONS, key=lambda r: haversine_km(lat, lon, r[2], r[3]))
        h = ts.hour if ts.date() == SIM_DAY.date() else 23
        return self.weather[(reg[0], h)] + random.gauss(0, 0.3)

    def plan_trip(self, idx, used_v, used_d):
        forced_routes = {0: "R-01", 1: "R-02", 2: "R-02", 3: "R-03"}   # makes every route appear in a small sample
        route_id = forced_routes.get(idx) or random.choices(list(ROUTE_WEIGHTS), weights=list(ROUTE_WEIGHTS.values()))[0]
        zones, weights = list(ZONE_WEIGHTS), list(ZONE_WEIGHTS.values())
        zone = random.choice(["CHILLED", "FROZEN", "PHARMA_COLD"]) if idx == 2 else random.choices(zones, weights=weights)[0]
        start = SIM_DAY + timedelta(hours=random.randint(5, 13), minutes=random.randint(0, 59))
        need_reefer = zone != "AMBIENT"
        cands = [v for v in self.vehicles if v["vehicle_id"] not in used_v
                 and (v["reefer_unit_id"] is not None or not need_reefer)
                 and self.status_at(v["vehicle_id"], start) == "Active"]
        if not cands:
            return None
        veh = random.choice(cands)
        drv = random.choice([d for d in self.drivers if d["driver_id"] not in used_d])
        prods = [p for p in PRODUCTS if self.prod_zone[p[0]] == zone]
        items = random.sample(prods, k=random.randint(1, min(3, len(prods))))
        reefer_items = [p for p in items if p[3] is not None]
        tmin = max([p[3] for p in reefer_items]) if reefer_items else None   # strictest range
        tmax = min([p[4] for p in reefer_items]) if reefer_items else None
        n = idx + 1
        return dict(idx=idx, trip_id=f"T-{100233 + n}", vehicle=veh, driver=drv, route_id=route_id,
                    planned_start=start, planned_end=start + timedelta(minutes=CORRIDOR_CFG[route_id]["expected_min"]),
                    shipment_id=f"SH-{55020 + n}", order_id=f"ORD-{7780 + n}", zone=zone, items=items,
                    tmin=tmin, tmax=tmax, setpoint=None if tmin is None else round((tmin + tmax) / 2, 1),
                    customer=random.choice(self.raw["raw_customers"]["customer_id"].tolist()))

    def _new_evt(self):
        self.cnt["evt"] += 1
        return f"e-{self.cnt['evt']:06x}"

    def simulate_trip(self, trip):
        route, iv, idx = self.corr[trip["route_id"]], self.interval, trip["idx"]
        vid, veh = trip["vehicle"]["vehicle_id"], trip["vehicle"]
        cruise = 78 + (17 if trip["driver"]["driver_id"] in self.aggressive else 0)
        est_n = int(route.length_km / (cruise * iv / 3600))
        can = est_n >= 9   # too-short trips get no injected anomalies
        do_idle = can and (idx == 0 or (idx not in (1, 2) and random.random() < 0.3))
        do_dev = can and (idx == 1 or (idx not in (0, 2) and random.random() < 0.2))
        do_cold = can and trip["zone"] != "AMBIENT" and (idx == 2 or random.random() < 0.5)
        idle_len, dev_len, cold_len = random.choice([2, 3]), 2, 3
        idle_s = dev_s = cold_s = None
        if do_idle and do_dev:
            for _ in range(200):
                a = random.randint(3, max(3, est_n - idle_len - 3))
                b = random.randint(3, max(3, est_n - dev_len - 3))
                if abs(a - b) > 4:
                    idle_s, dev_s = a, b
                    break
            else:
                idle_s, dev_s = 3, est_n - 4
        elif do_idle:
            idle_s = random.randint(3, max(3, est_n - idle_len - 3))
        elif do_dev:
            dev_s = random.randint(3, max(3, est_n - dev_len - 3))
        if do_cold:
            cold_s = random.randint(3, max(3, est_n - cold_len - 2))
        tel, rf = [], []
        ts, dist, i = trip["planned_start"] + timedelta(minutes=random.randint(0, 8)), 0.0, 0
        times = {}
        seq_t = self.seq.setdefault(vid, 0)
        sensor = f"{veh['reefer_unit_id']}-S1" if veh["reefer_unit_id"] else None
        while dist < route.length_km:
            in_idle = idle_s is not None and idle_s <= i < idle_s + idle_len
            in_dev = dev_s is not None and dev_s <= i < dev_s + dev_len
            in_cold = cold_s is not None and cold_s <= i < cold_s + cold_len
            if i == 0:
                speed = 30.0
            elif in_idle:
                speed = 0.0
            elif idle_s is not None and (i == idle_s - 1 or i == idle_s + idle_len):
                speed = 45.0
            else:
                speed = round(max(55, min(112, random.gauss(cruise, 5))), 1)
            lat, lon = route.pos_at(dist)
            if in_dev:
                off_km, b = random.uniform(2.5, 3.5), route.bearing_at(dist) + math.pi / 2
                lat += off_km * math.cos(b) / 111.0
                lon += off_km * math.sin(b) / (111.0 * math.cos(math.radians(lat)))
            lat, lon = lat + random.gauss(0, 0.00008), lon + random.gauss(0, 0.00008)
            amb = self.ambient_at(lat, lon, ts)
            rpm = int(750 + random.gauss(0, 25)) if speed == 0 else int(700 + 14 * speed + random.gauss(0, 40))
            fuel = round(2.1 + random.gauss(0, 0.2), 1) if speed == 0 else round(2.0 + 0.21 * speed + random.gauss(0, 0.8), 1)
            eng = round(82 + 0.12 * speed + 0.1 * (amb - 25) + random.gauss(0, 1.0), 1)
            seq_t += 1
            msg = dict(event_id=self._new_evt(), vehicle_id=vid, device_id=f"TU-{vid[3:]}", event_ts=iso(ts),
                       lat=round(lat, 5), lon=round(lon, 5), speed_kmh=speed, rpm=rpm, engine_temp_c=eng,
                       fuel_lph=fuel, odometer_km=round(self.odo_base[vid] + dist, 1),
                       ingest_ts=iso(ts + timedelta(seconds=random.randint(1, 3))), source_sequence=seq_t)
            protected = in_idle or in_dev or (idle_s is not None and i in (idle_s - 1, idle_s + idle_len))
            if not protected:                          # data defects on normal readings only
                if random.random() < 0.02:
                    msg["speed_kmh"] = None
                if random.random() < 0.03:
                    msg["lat"] = msg["lon"] = None
                if random.random() < 0.03:             # late arrival
                    msg["ingest_ts"] = iso(ts + timedelta(seconds=random.randint(60, 300)))
            tel.append(msg)
            if not protected and random.random() < 0.03:   # duplicate delivery
                tel.append({**msg, "ingest_ts": iso(ts + timedelta(seconds=random.randint(4, 9)))})
            if sensor:
                if trip["setpoint"] is None:      # dry-goods trip on a reefer truck: unit idle, no setpoint
                    cargo, comp = amb - 4 + random.gauss(0, 0.5), False
                elif in_cold:
                    cargo, comp = trip["tmax"] + (1.5, 3.5, 5.0)[i - cold_s], False
                elif cold_s is not None and i == cold_s + cold_len:
                    cargo, comp = trip["tmax"] - 1.0, True
                else:
                    cargo, comp = trip["setpoint"] + random.gauss(0, 0.4) + 0.02 * (amb - 25), True
                self.cnt["rf"] += 1
                seq_r = self.rseq.get(sensor, 0) + 1
                self.rseq[sensor] = seq_r
                r = dict(event_id=f"r-{self.cnt['rf']:06x}", vehicle_id=vid, sensor_id=sensor,
                         event_ts=iso(ts + timedelta(seconds=2)), ingest_ts=iso(ts + timedelta(seconds=random.randint(3, 6))),
                         cargo_temp_c=round(cargo, 1), setpoint_c=trip["setpoint"], compressor_on=comp,
                         door_open=(random.random() < 0.01 and not in_cold),
                         ambient_temp_c=round(amb, 1), source_sequence=seq_r)
                rf.append(r)
                if not in_cold and random.random() < 0.03:
                    rf.append({**r, "ingest_ts": iso(ts + timedelta(seconds=random.randint(7, 12)))})
            times[i] = ts
            if speed > 0:
                dist += speed * iv / 3600
            ts += timedelta(seconds=iv)
            i += 1
        self.seq[vid] = seq_t
        arrival = ts
        sd = self.a.seed
        if idle_s is not None:
            self.labels.append(dict(vehicle_id=vid, anomaly_type="EXCESSIVE_IDLING", start_ts=times[idle_s],
                                    end_ts=times[idle_s] + timedelta(seconds=idle_len * iv),
                                    params_json=json.dumps({"readings": idle_len}), generator_seed=sd))
        if dev_s is not None:
            self.labels.append(dict(vehicle_id=vid, anomaly_type="ROUTE_DEVIATION", start_ts=times[dev_s],
                                    end_ts=times[dev_s] + timedelta(seconds=dev_len * iv),
                                    params_json=json.dumps({"offset_km": "2.5-3.5"}), generator_seed=sd))
        if cold_s is not None:
            self.labels.append(dict(vehicle_id=vid, anomaly_type="COLD_CHAIN_BREACH", start_ts=times[cold_s],
                                    end_ts=times[cold_s] + timedelta(seconds=cold_len * iv),
                                    params_json=json.dumps({"peak_temp_c": round(trip["tmax"] + 5.0, 1)}), generator_seed=sd))
        return tel, rf, arrival

    def build_streams(self):
        self.seq, self.rseq = {}, {}
        trips, shipments, items, tel, rf = [], [], [], [], []
        used_v, used_d, idx = set(), set(), 0
        while sum(1 for _ in tel) < self.a.telemetry_rows and idx < self.a.vehicles:
            t = self.plan_trip(idx, used_v, used_d)
            if t is None:
                break
            used_v.add(t["vehicle"]["vehicle_id"])
            used_d.add(t["driver"]["driver_id"])
            m, r, arrival = self.simulate_trip(t)
            tel += m
            rf += r
            trips.append(dict(trip_id=t["trip_id"], vehicle_id=t["vehicle"]["vehicle_id"], driver_id=t["driver"]["driver_id"],
                              route_id=t["route_id"], planned_start_ts=t["planned_start"].strftime("%Y-%m-%d %H:%M"),
                              planned_end_ts=t["planned_end"].strftime("%Y-%m-%d %H:%M"),
                              status=random.choice(["COMPLETED", "completed"])))
            cfg = CORRIDOR_CFG[t["route_id"]]
            delivered = arrival + timedelta(minutes=random.randint(0, 10))
            shipments.append(dict(shipment_id=t["shipment_id"], order_id=t["order_id"], trip_id=t["trip_id"],
                                  customer_id=t["customer"], origin_location_id=cfg["origin"], dest_location_id=cfg["dest"],
                                  promised_ts=t["planned_end"].strftime("%Y-%m-%d %H:%M"),
                                  delivered_ts=delivered.strftime("%Y-%m-%d %H:%M"),
                                  status=random.choice(["DELIVERED", "delivered "])))
            for p in t["items"]:
                items.append(dict(shipment_id=t["shipment_id"], product_id=p[0], quantity=random.randint(10, 200),
                                  unit_value_egp=round(random.uniform(100, 3000), 2)))
            idx += 1
        # malformed events -> will be rejected by ingestion validation and land in the DLQ
        bad = []
        for kind in ("speed_text", "missing_vehicle", "bad_timestamp"):
            m = dict(random.choice(tel))
            m["event_id"] = self._new_evt()
            if kind == "speed_text":
                m["speed_kmh"] = "fast"
            elif kind == "missing_vehicle":
                m["vehicle_id"] = None
            else:
                m["event_ts"] = "not-a-timestamp"
            bad.append(m)
        self.trips_n = idx
        self.raw["raw_dispatch_trips"] = pd.DataFrame(trips)
        self.raw["raw_shipments"] = pd.DataFrame(shipments)
        self.raw["raw_shipment_items"] = pd.DataFrame(items)

        def validate(m):
            if not m.get("vehicle_id"):
                return "MISSING_FIELD"
            try:
                datetime.fromisoformat(m["event_ts"].replace("Z", "+00:00"))
            except Exception:
                return "BAD_TIMESTAMP"
            if m["speed_kmh"] is not None and not isinstance(m["speed_kmh"], (int, float)):
                return "SCHEMA_MISMATCH"
            return None

        good, dlq = [], []
        for m in tel + bad:
            err = validate(m)
            if err:
                dlq.append(dict(dlq_id=f"dlq-{len(dlq) + 1:04d}", source_topic="telemetry", received_ts=m["ingest_ts"],
                                error_type=err, raw_payload=json.dumps(m, default=str), retry_count=3, status="UNRESOLVED"))
            else:
                good.append(m)
        self.stream_in = {"telemetry": len(tel) + len(bad), "reefer": len(rf)}
        self.raw["bronze_telemetry_raw"] = pd.DataFrame(good).sort_values("ingest_ts").reset_index(drop=True)
        self.raw["bronze_reefer_raw"] = pd.DataFrame(rf).sort_values("ingest_ts").reset_index(drop=True)
        self.dlq = pd.DataFrame(dlq)

        # fuel card transactions (card returns the PLATE, not vehicle_id)
        fuel, price = [], 15.50
        for i in range(30):
            v = random.choice(self.vehicles)
            ts = SIM_DAY - timedelta(days=random.randint(1, 14), hours=random.randint(0, 12), minutes=random.randint(0, 59))
            liters = round(random.uniform(60, 200), 1)
            amt = round(liters * price * (1 + random.uniform(-0.02, 0.02)), 2)
            if i == 7:
                amt = round(liters * price * 1.12, 2)    # one price outlier for the DQ check
            fuel.append(dict(card_txn_id=f"FT-{880001 + i}", vehicle_plate=v["plate_no"],
                             driver_id=random.choice(self.drivers)["driver_id"], station_osm_id=random.choice(self.stations),
                             txn_ts=ts.strftime("%Y-%m-%d %H:%M"), liters=liters, amount_egp=amt,
                             odometer_km=float(self.odo_base[v["vehicle_id"]] - (SIM_DAY - ts).days * 350)))
        self.raw["raw_fuel_transactions"] = pd.DataFrame(fuel)

    # ---- 3. silver ---------------------------------------------------------
    def build_silver(self):
        R, S = self.raw, self.silver
        tz = lambda s: pd.to_datetime(s, utc=True).dt.tz_localize(None)

        t = R["bronze_telemetry_raw"].copy()
        t["event_ts"], t["ingest_ts"] = tz(t["event_ts"]), tz(t["ingest_ts"])
        t = t.sort_values(["ingest_ts"]).drop_duplicates("event_id").sort_values(["vehicle_id", "event_ts"]).reset_index(drop=True)
        t["speed_imputed"], t["gps_imputed"] = t["speed_kmh"].isna(), t["lat"].isna()
        g = t.groupby("vehicle_id")
        for c in ("speed_kmh", "lat", "lon"):
            t[c] = g[c].ffill()
        trips = R["raw_dispatch_trips"].copy()
        trips["status"] = trips["status"].str.strip().str.upper()
        trips["planned_start_ts"] = pd.to_datetime(trips["planned_start_ts"])
        trips["planned_end_ts"] = pd.to_datetime(trips["planned_end_ts"])
        S["silver_trips"] = trips
        m = t.merge(trips[["vehicle_id", "trip_id", "driver_id", "route_id", "planned_start_ts", "planned_end_ts"]], on="vehicle_id", how="left")
        ok = (m.event_ts >= m.planned_start_ts - pd.Timedelta(minutes=30)) & (m.event_ts <= m.planned_end_ts + pd.Timedelta(hours=6))
        m = m[ok].drop(columns=["planned_start_ts", "planned_end_ts"])
        self.unassigned = len(t) - len(m)
        S["silver_telemetry_clean"] = m.reset_index(drop=True)

        items = R["raw_shipment_items"].merge(R["raw_products"], on="product_id")
        items["zone"] = [self.prod_zone[p] for p in items["product_id"]]
        items["line_value_egp"] = (items["quantity"] * items["unit_value_egp"]).round(2)
        agg = items.groupby("shipment_id").agg(item_count=("product_id", "count"), total_value_egp=("line_value_egp", "sum"),
                                              temp_min_c=("temp_min_c", "max"), temp_max_c=("temp_max_c", "min"),
                                              temp_zone=("zone", "first")).reset_index()
        agg["is_reefer"] = agg["temp_zone"] != "AMBIENT"
        sh = R["raw_shipments"].copy()
        sh["status"] = sh["status"].str.strip().str.upper()
        sh["promised_ts"], sh["delivered_ts"] = pd.to_datetime(sh["promised_ts"]), pd.to_datetime(sh["delivered_ts"])
        sh["delay_min"] = ((sh["delivered_ts"] - sh["promised_ts"]).dt.total_seconds() / 60).round(1)
        sh["is_on_time"] = sh["delay_min"] <= ON_TIME_GRACE_MIN
        S["silver_shipments"] = sh.merge(agg, on="shipment_id", how="left")

        r = R["bronze_reefer_raw"].copy()
        r["event_ts"], r["ingest_ts"] = tz(r["event_ts"]), tz(r["ingest_ts"])
        r = r.sort_values("ingest_ts").drop_duplicates(["sensor_id", "source_sequence"]).sort_values(["vehicle_id", "event_ts"])
        r = r.merge(trips[["vehicle_id", "trip_id", "planned_start_ts", "planned_end_ts"]], on="vehicle_id", how="left")
        r = r[(r.event_ts >= r.planned_start_ts - pd.Timedelta(minutes=30)) & (r.event_ts <= r.planned_end_ts + pd.Timedelta(hours=6))]
        r = r.drop(columns=["planned_start_ts", "planned_end_ts"]).merge(
            S["silver_shipments"][["trip_id", "shipment_id", "temp_min_c", "temp_max_c", "is_reefer"]], on="trip_id", how="left")
        S["silver_reefer_clean"] = r.reset_index(drop=True)

        c = R["raw_customers"].copy()
        for col in ("customer_name", "city", "segment", "contract_tier"):
            c[col] = c[col].str.strip()
        c["city"], c["segment"], c["contract_tier"] = c["city"].str.title(), c["segment"].str.title(), c["contract_tier"].str.title()
        S["silver_customers"] = c

        veh = R["raw_vehicles"].sort_values("snapshot_date").drop_duplicates("vehicle_id", keep="last")
        f = R["raw_fuel_transactions"].merge(veh[["plate_no", "vehicle_id"]], left_on="vehicle_plate", right_on="plate_no", how="left")
        f["txn_ts"] = pd.to_datetime(f["txn_ts"])
        f["price_per_l_egp"] = (f["amount_egp"] / f["liters"]).round(2)
        prices = R["raw_fuel_prices"].assign(effective_date=lambda d: pd.to_datetime(d["effective_date"])).sort_values("effective_date")
        f = pd.merge_asof(f.sort_values("txn_ts"), prices[["effective_date", "price_per_l_egp"]].rename(columns={"price_per_l_egp": "official_price"}),
                          left_on="txn_ts", right_on="effective_date")
        f["price_diff_pct"] = ((f["price_per_l_egp"] / f["official_price"] - 1) * 100).round(1)
        f["price_outlier"] = f["price_diff_pct"].abs() > PRICE_TOLERANCE * 100
        S["silver_fuel_transactions"] = f.drop(columns=["plate_no", "effective_date"]).reset_index(drop=True)

    # ---- 4. gold -----------------------------------------------------------
    def build_gold(self):
        R, S, G = self.raw, self.silver, self.gold
        # dimensions
        v = R["raw_vehicles"].copy().sort_values(["vehicle_id", "snapshot_date"]).reset_index(drop=True)
        v["valid_from"] = pd.to_datetime(v["snapshot_date"])
        nxt = v.groupby("vehicle_id")["snapshot_date"].shift(-1)
        v["valid_to"] = nxt.fillna("9999-12-31")
        v["is_current"] = nxt.isna()
        v.insert(0, "vehicle_key", 1001 + np.arange(len(v)))
        G["dim_vehicle"] = v.drop(columns=["snapshot_date"])

        d = R["raw_drivers"].copy().sort_values(["driver_id", "snapshot_date"]).reset_index(drop=True)
        d["valid_from"] = pd.to_datetime(d["snapshot_date"])
        nxt = d.groupby("driver_id")["snapshot_date"].shift(-1)
        d["valid_to"], d["is_current"] = nxt.fillna("9999-12-31"), nxt.isna()
        d.insert(0, "driver_key", 201 + np.arange(len(d)))
        G["dim_driver"] = d.drop(columns=["snapshot_date", "employment_status"])

        pl = R["raw_osm_places"].merge(R["cfg_location_map"], on="osm_id", how="left")
        pl["location_type"] = pl["place_type"].str.title()
        gov = lambda la, lo: min(REGIONS, key=lambda r: haversine_km(la, lo, r[2], r[3]))[4]
        pl["governorate"] = [s if isinstance(s, str) else gov(a, b) for s, a, b in zip(pl["addr_state"], pl["lat"], pl["lon"])]
        pl = pl.sort_values("location_id").reset_index(drop=True)
        pl.insert(0, "location_key", 10 + np.arange(len(pl)))
        G["dim_location"] = pl[["location_key", "location_id", "osm_id", "name", "location_type", "governorate", "lat", "lon"]]
        lk = dict(zip(G["dim_location"]["location_id"], G["dim_location"]["location_key"]))
        lk_osm = dict(zip(G["dim_location"]["osm_id"], G["dim_location"]["location_key"]))

        roads = R["raw_osm_roads"].merge(R["cfg_corridors"][["route_id", "road_name"]], left_on="name", right_on="road_name")
        roads = roads.sort_values(["route_id", "osm_way_id"]).reset_index(drop=True)
        roads["segment_seq"] = roads.groupby("route_id").cumcount() + 1
        roads["speed_limit_kmh"] = [int(m) if isinstance(m, str) else HIGHWAY_DEFAULT_LIMIT[h] for m, h in zip(roads["maxspeed"], roads["highway_type"])]
        coords = roads["geometry_wkt"].str.extract(r"\(([-\d.]+) ([-\d.]+), ([-\d.]+) ([-\d.]+)\)").astype(float)
        roads["start_lon"], roads["start_lat"], roads["end_lon"], roads["end_lat"] = coords[0], coords[1], coords[2], coords[3]
        roads["length_m"] = [round(haversine_km(a, b, c, e) * 1000) for a, b, c, e in zip(roads.start_lat, roads.start_lon, roads.end_lat, roads.end_lon)]
        rkey = {"R-01": 1, "R-02": 2, "R-03": 3}
        roads["route_key"] = roads["route_id"].map(rkey)
        roads.insert(0, "segment_key", 1 + np.arange(len(roads)))
        G["dim_route_segment"] = roads[["segment_key", "route_key", "segment_seq", "start_lat", "start_lon", "end_lat", "end_lon",
                                        "length_m", "speed_limit_kmh", "highway_type"]]
        loc_by_osm = G["dim_location"].set_index("osm_id")["location_id"].to_dict()
        rt = R["cfg_corridors"].copy()
        rt["route_key"] = rt["route_id"].map(rkey)
        rt["origin_location_key"] = rt["origin_osm_id"].map(lk_osm)
        rt["dest_location_key"] = rt["dest_osm_id"].map(lk_osm)
        rt["distance_km"] = rt["route_id"].map(roads.groupby("route_id")["length_m"].sum() / 1000).round(1)
        rt["corridor_type"] = "Highway"
        G["dim_route"] = rt[["route_key", "route_id", "route_name", "origin_location_key", "dest_location_key", "distance_km",
                             "expected_duration_min", "corridor_type"]]

        c = S["silver_customers"].copy()
        c.insert(0, "customer_key", 31 + np.arange(len(c)))
        G["dim_customer"] = c.drop(columns=["created_at"])
        p = R["raw_products"].copy()
        p["temp_zone"] = [self.prod_zone[x] for x in p["product_id"]]
        p["is_reefer"] = p["temp_zone"] != "AMBIENT"
        p.insert(0, "product_key", 41 + np.arange(len(p)))
        G["dim_product"] = p
        hol = R["raw_public_holidays"].set_index("date")["name"].to_dict()
        days = pd.date_range("2026-08-01", "2026-11-30")
        G["dim_date"] = pd.DataFrame(dict(
            date_key=[dkey(x) for x in days], full_date=days.date, day_name=days.day_name(), month=days.month, quarter=days.quarter,
            is_weekend=days.dayofweek.isin([4, 5]),                   # Egypt weekend: Friday + Saturday
            is_public_holiday=[x.strftime("%Y-%m-%d") in hol for x in days],
            holiday_name=[hol.get(x.strftime("%Y-%m-%d")) for x in days]))
        G["dim_region_weather"] = pd.DataFrame(
            [dict(region_key=i + 1, region_id=r[0], region_name=r[1], lat=r[2], lon=r[3]) for i, r in enumerate(REGIONS)])
        rk = {r[0]: i + 1 for i, r in enumerate(REGIONS)}
        w = R["raw_weather_api"].copy()
        w["obs_ts"] = pd.to_datetime(w["time"])
        w.insert(0, "weather_key", 660001 + np.arange(len(w)))
        w["region_key"] = w["request_region"].map(rk)
        G["fact_weather_hourly"] = w.rename(columns={"temperature_2m": "temp_c", "relative_humidity_2m": "humidity_pct",
                                                     "precipitation": "precip_mm", "wind_speed_10m": "wind_kmh"})[
            ["weather_key", "region_key", "obs_ts", "temp_c", "humidity_pct", "precip_mm", "wind_kmh", "weather_code"]]

        # facts: telemetry (+ nearest road segment, distance, point-in-time vehicle/driver)
        t = S["silver_telemetry_clean"].copy()
        t["vehicle_key"] = pit(t, "vehicle_id", "event_ts", G["dim_vehicle"], "vehicle_id", "vehicle_key")
        t["driver_key"] = pit(t, "driver_id", "event_ts", G["dim_driver"], "driver_id", "driver_key")
        segs = G["dim_route_segment"]
        near = []
        for lat, lon, rid in zip(t["lat"], t["lon"], t["route_id"]):
            s = segs[segs.route_key == rkey[rid]]
            dists = [point_segment_m(lat, lon, (a, b), (c, e)) for a, b, c, e in zip(s.start_lat, s.start_lon, s.end_lat, s.end_lon)]
            j = int(np.argmin(dists))
            near.append((int(s.iloc[j]["segment_key"]), round(dists[j], 1), int(s.iloc[j]["speed_limit_kmh"])))
        t["segment_key"], t["dist_from_route_m"], t["speed_limit_kmh"] = zip(*near)
        t["route_key"] = t["route_id"].map(rkey)
        t["date_key"] = t["event_ts"].map(dkey)
        t["is_idling"] = (t["speed_kmh"] == 0) & (t["rpm"] > 0)
        t = t.sort_values(["vehicle_id", "event_ts"]).reset_index(drop=True)
        t.insert(0, "telemetry_key", 9000001 + np.arange(len(t)))
        self.t = t
        G["fact_telemetry"] = t[["telemetry_key", "vehicle_key", "driver_key", "route_key", "segment_key", "date_key", "event_ts", "lat", "lon",
                                 "speed_kmh", "rpm", "engine_temp_c", "fuel_lph", "is_idling", "dist_from_route_m", "speed_imputed", "gps_imputed"]]

        # trips, shipments
        tr = S["silver_trips"].copy()
        tel_by_trip = t.groupby("trip_id")
        tr["start_ts"], tr["end_ts"] = tr["trip_id"].map(tel_by_trip["event_ts"].min()), tr["trip_id"].map(tel_by_trip["event_ts"].max()) + pd.Timedelta(seconds=self.interval)
        last_speed = t.sort_values("event_ts").groupby("trip_id")["speed_kmh"].last()
        tr["distance_km"] = (tr["trip_id"].map(tel_by_trip["odometer_km"].max()) - tr["trip_id"].map(tel_by_trip["odometer_km"].min())
                             + tr["trip_id"].map(last_speed) * self.interval / 3600).round(1)
        tr["fuel_used_l"] = (tr["trip_id"].map(tel_by_trip["fuel_lph"].sum()) * self.interval / 3600).round(1)
        hours = (tr["end_ts"] - tr["start_ts"]).dt.total_seconds() / 3600
        tr["avg_speed_kmh"], tr["km_per_l"] = (tr["distance_km"] / hours).round(1), (tr["distance_km"] / tr["fuel_used_l"]).round(2)
        tr["vehicle_key"] = pit(tr, "vehicle_id", "planned_start_ts", G["dim_vehicle"], "vehicle_id", "vehicle_key")
        tr["driver_key"] = pit(tr, "driver_id", "planned_start_ts", G["dim_driver"], "driver_id", "driver_key")
        tr["route_key"], tr["date_key"] = tr["route_id"].map(rkey), tr["planned_start_ts"].map(dkey)
        tr.insert(0, "trip_key", 700001 + np.arange(len(tr)))
        G["fact_trip"] = tr[["trip_key", "trip_id", "vehicle_key", "driver_key", "route_key", "date_key", "start_ts", "end_ts",
                             "distance_km", "fuel_used_l", "avg_speed_kmh", "km_per_l"]]
        trip_key = dict(zip(tr["trip_id"], tr["trip_key"]))
        cust_key = dict(zip(G["dim_customer"]["customer_id"], G["dim_customer"]["customer_key"]))
        prod_key = dict(zip(G["dim_product"]["product_id"], G["dim_product"]["product_key"]))

        sh = S["silver_shipments"].copy()
        sh.insert(0, "shipment_key", 810001 + np.arange(len(sh)))
        sh["trip_key"] = sh["trip_id"].map(trip_key)
        sh["customer_key"] = sh["customer_id"].map(cust_key)
        sh["origin_location_key"], sh["dest_location_key"] = sh["origin_location_id"].map(lk), sh["dest_location_id"].map(lk)
        sh["date_key"] = sh["promised_ts"].map(dkey)
        G["fact_shipment_delivery"] = sh[["shipment_key", "shipment_id", "trip_key", "customer_key", "origin_location_key", "dest_location_key",
                                         "date_key", "promised_ts", "delivered_ts", "delay_min", "is_on_time", "item_count", "total_value_egp"]]
        ship_key = dict(zip(sh["shipment_id"], sh["shipment_key"]))
        it = R["raw_shipment_items"].copy()
        it.insert(0, "shipment_item_key", 820001 + np.arange(len(it)))
        it["shipment_key"], it["product_key"] = it["shipment_id"].map(ship_key), it["product_id"].map(prod_key)
        it["line_value_egp"] = (it["quantity"] * it["unit_value_egp"]).round(2)
        G["fact_shipment_item"] = it[["shipment_item_key", "shipment_key", "product_key", "quantity", "unit_value_egp", "line_value_egp"]]

        # events detected from DATA ONLY (no access to ground-truth labels)
        def runs(df, flag, min_len):
            out = []
            for tid, grp in df.groupby("trip_id"):
                grp = grp.sort_values("event_ts")
                cur = []
                for _, row in grp.iterrows():
                    if row[flag]:
                        cur.append(row)
                    else:
                        if len(cur) >= min_len:
                            out.append(cur)
                        cur = []
                if len(cur) >= min_len:
                    out.append(cur)
            return out

        iv = pd.Timedelta(seconds=self.interval)
        idle = []
        for k, run in enumerate(runs(t, "is_idling", IDLE_MIN_READINGS)):
            f, l = run[0], run[-1]
            idle.append(dict(idle_key=620001 + k, vehicle_key=f["vehicle_key"], driver_key=f["driver_key"], trip_key=trip_key[f["trip_id"]],
                             vehicle_id=f["vehicle_id"], start_ts=f["event_ts"], end_ts=l["event_ts"] + iv,
                             duration_min=round((l["event_ts"] + iv - f["event_ts"]).total_seconds() / 60, 1), lat=f["lat"], lon=f["lon"],
                             ambient_temp_c=round(self.ambient_at(f["lat"], f["lon"], f["event_ts"].to_pydatetime()), 1)))
        G["fact_idling_event"] = pd.DataFrame(idle, columns=["idle_key", "vehicle_key", "driver_key", "trip_key", "vehicle_id", "start_ts",
                                                            "end_ts", "duration_min", "lat", "lon", "ambient_temp_c"])
        t["is_off_route"] = t["dist_from_route_m"] > DEVIATION_M
        dev = []
        for k, run in enumerate(runs(t, "is_off_route", 1)):
            f, l = run[0], run[-1]
            dev.append(dict(deviation_key=630001 + k, vehicle_key=f["vehicle_key"], trip_key=trip_key[f["trip_id"]], vehicle_id=f["vehicle_id"],
                            detected_ts=f["event_ts"], max_deviation_m=round(max(x["dist_from_route_m"] for x in run), 0),
                            duration_min=round(len(run) * self.interval / 60, 1), resolved_ts=l["event_ts"] + iv))
        G["fact_route_deviation"] = pd.DataFrame(dev, columns=["deviation_key", "vehicle_key", "trip_key", "vehicle_id", "detected_ts",
                                                              "max_deviation_m", "duration_min", "resolved_ts"])
        r = S["silver_reefer_clean"].copy()
        r = r[r["is_reefer"].fillna(False)]
        r["above"] = r["cargo_temp_c"] > r["temp_max_c"]
        self.reefer_eval = r
        cold = []
        for k, run in enumerate(runs(r, "above", 1)):
            f, l = run[0], run[-1]
            peak = max(x["cargo_temp_c"] for x in run)
            sev = "High" if peak - f["temp_max_c"] >= 3 else "Medium"
            veh_key = pit(pd.DataFrame([f]), "vehicle_id", "event_ts", G["dim_vehicle"], "vehicle_id", "vehicle_key")[0]
            cold.append(dict(event_key=610001 + k, vehicle_key=veh_key, trip_key=trip_key[f["trip_id"]], shipment_key=ship_key[f["shipment_id"]],
                             vehicle_id=f["vehicle_id"], start_ts=f["event_ts"], end_ts=l["event_ts"] + iv,
                             duration_min=round(len(run) * self.interval / 60, 1), max_temp_c=peak, threshold_c=f["temp_max_c"], severity=sev))
        G["fact_cold_chain_event"] = pd.DataFrame(cold, columns=["event_key", "vehicle_key", "trip_key", "shipment_key", "vehicle_id", "start_ts",
                                                                "end_ts", "duration_min", "max_temp_c", "threshold_c", "severity"])

        f = S["silver_fuel_transactions"].copy()
        f["vehicle_key"] = pit(f, "vehicle_id", "txn_ts", G["dim_vehicle"], "vehicle_id", "vehicle_key")
        drv_df = f.rename(columns={})
        f["driver_key"] = pit(drv_df, "driver_id", "txn_ts", G["dim_driver"], "driver_id", "driver_key")
        f["location_key"], f["date_key"] = f["station_osm_id"].map(lk_osm), f["txn_ts"].map(dkey)
        f = f.sort_values("txn_ts").reset_index(drop=True)
        f.insert(0, "fuel_txn_key", 640001 + np.arange(len(f)))
        G["fact_fuel_transaction"] = f[["fuel_txn_key", "vehicle_key", "driver_key", "location_key", "date_key", "txn_ts", "liters",
                                        "price_per_l_egp", "amount_egp", "odometer_km", "price_diff_pct"]]

        mo = R["raw_maintenance_orders"].copy()
        mo["opened_ts"], mo["closed_ts"] = pd.to_datetime(mo["opened_date"]), pd.to_datetime(mo["closed_date"])
        mo["vehicle_key"] = pit(mo, "vehicle_id", "opened_ts", G["dim_vehicle"], "vehicle_id", "vehicle_key")
        mo["date_key"] = mo["opened_ts"].map(dkey)
        mo["downtime_hours"] = ((mo["closed_ts"] - mo["opened_ts"]).dt.total_seconds() / 3600).round(1)   # null while the order is open
        mo.insert(0, "maint_key", 650001 + np.arange(len(mo)))
        G["fact_maintenance"] = mo[["maint_key", "vehicle_key", "date_key", "maint_type", "cost_egp", "downtime_hours", "odometer_km"]]

        # driver scorecard (formula = simulation assumption)
        t = t.sort_values(["trip_id", "event_ts"])
        t["speeding"] = t["speed_kmh"] > t["speed_limit_kmh"] + SPEED_TOLERANCE_KMH
        t["harsh"] = (t.groupby("trip_id")["speed_kmh"].shift(1) - t["speed_kmh"]) >= HARSH_BRAKE_DROP_KMH
        sc = t.groupby(["date_key", "driver_key"]).agg(distance_km=("odometer_km", lambda s: round(s.max() - s.min(), 1)),
                                                       speeding_events=("speeding", "sum"), harsh_brake_events=("harsh", "sum"),
                                                       readings=("event_ts", "count")).reset_index()
        idle_min = G["fact_idling_event"].assign(date_key=lambda d: d["start_ts"].map(dkey)).groupby(["date_key", "driver_key"])["duration_min"].sum()
        sc["idle_minutes"] = [idle_min.get((a, b), 0.0) for a, b in zip(sc["date_key"], sc["driver_key"])]
        sc["idle_pct"] = (sc["idle_minutes"] / (sc["readings"] * self.interval / 60) * 100).round(1)
        sc["safety_score"] = (100 - 2 * sc["speeding_events"] - 5 * sc["harsh_brake_events"] - sc["idle_pct"]).clip(lower=0).round(0)
        G["agg_driver_scorecard_daily"] = sc.drop(columns=["readings"])

    # ---- 5. ops: ingestion log, DQ, ground truth, reconciliation -----------
    def build_ops(self):
        R, S, G = self.raw, self.silver, self.gold
        ops = self.ops
        ops["dlq_events"] = self.dlq
        lbl = pd.DataFrame(self.labels).sort_values(["start_ts", "vehicle_id"]).reset_index(drop=True)
        lbl.insert(0, "anomaly_id", [f"A-{i + 1:04d}" for i in range(len(lbl))])
        ops["gen_anomaly_labels"] = lbl

        def lg(src, rin, rok, rdlq, i):
            return dict(run_id=f"run-20261102-{i:02d}", source=src, started_ts=RUN_TS + timedelta(minutes=i),
                        ended_ts=RUN_TS + timedelta(minutes=i, seconds=40), records_in=rin, records_ok=rok, records_dlq=rdlq,
                        status="SUCCESS_WITH_DLQ" if rdlq else "SUCCESS")
        log = [lg("S1_telemetry_stream", self.stream_in["telemetry"], len(R["bronze_telemetry_raw"]), len(self.dlq), 1),
               lg("S2_reefer_stream", self.stream_in["reefer"], len(R["bronze_reefer_raw"]), 0, 2)]
        for i, (src, tbls) in enumerate([("S3_tms_batch", ["raw_dispatch_trips", "raw_shipments", "raw_shipment_items", "raw_customers", "raw_products"]),
                                         ("S4_fuel_cards", ["raw_fuel_transactions"]), ("S5_maintenance", ["raw_maintenance_orders"]),
                                         ("S6_hr_drivers", ["raw_drivers"]), ("S7_weather_api", ["raw_weather_api"]),
                                         ("S8_osm", ["raw_osm_roads", "raw_osm_places"]), ("S9_prices_holidays", ["raw_fuel_prices", "raw_public_holidays"]),
                                         ("S10_vehicle_registry", ["raw_vehicles"])], start=3):
            n = sum(len(R[x]) for x in tbls)
            log.append(lg(src, n, n, 0, i))
        ops["ingestion_log"] = pd.DataFrame(log)

        run_id, checks = "run-20261102-dq", []

        def chk(table, name, failed):
            checks.append(dict(check_id=len(checks) + 1, run_id=run_id, table_name=table, check_name=name,
                               status="PASS" if failed == 0 else "FAIL", failed_rows=int(failed), checked_ts=RUN_TS + timedelta(minutes=30)))
        bt = R["bronze_telemetry_raw"]
        chk("bronze_telemetry_raw", "event_id is unique", bt["event_id"].duplicated().sum())
        chk("bronze_telemetry_raw", "speed_kmh not null", bt["speed_kmh"].isna().sum())
        chk("bronze_telemetry_raw", "lat/lon not null", bt["lat"].isna().sum())
        st = S["silver_telemetry_clean"]
        chk("silver_telemetry_clean", "event_id is unique", st["event_id"].duplicated().sum())
        chk("silver_telemetry_clean", "speed_kmh between 0 and 200", ((st["speed_kmh"] < 0) | (st["speed_kmh"] > 200)).sum())
        chk("silver_telemetry_clean", "every reading assigned to a trip", self.unassigned)
        sr = S["silver_reefer_clean"]
        chk("silver_reefer_clean", "(sensor_id, source_sequence) is unique", sr.duplicated(["sensor_id", "source_sequence"]).sum())
        chk("silver_reefer_clean", "cargo_temp_c between -40 and 40", ((sr["cargo_temp_c"] < -40) | (sr["cargo_temp_c"] > 40)).sum())
        ft = G["fact_telemetry"]
        chk("fact_telemetry", "FK vehicle_key/driver_key/route_key/segment_key resolve",
            (~ft["vehicle_key"].isin(G["dim_vehicle"]["vehicle_key"])).sum() + (~ft["driver_key"].isin(G["dim_driver"]["driver_key"])).sum()
            + (~ft["route_key"].isin(G["dim_route"]["route_key"])).sum() + (~ft["segment_key"].isin(G["dim_route_segment"]["segment_key"])).sum())
        vs = G["dim_vehicle"].set_index("vehicle_key")["fleet_status"]
        chk("fact_telemetry", "vehicle was 'Active' at event time (SCD2 point-in-time)", (ft["vehicle_key"].map(vs) != "Active").sum())
        chk("fact_trip", "FK vehicle_key/driver_key/route_key resolve",
            (~G["fact_trip"]["vehicle_key"].isin(G["dim_vehicle"]["vehicle_key"])).sum() + (~G["fact_trip"]["driver_key"].isin(G["dim_driver"]["driver_key"])).sum())
        fs = G["fact_shipment_delivery"]
        chk("fact_shipment_delivery", "FK trip/customer/origin/dest resolve",
            (~fs["trip_key"].isin(G["fact_trip"]["trip_key"])).sum() + (~fs["customer_key"].isin(G["dim_customer"]["customer_key"])).sum()
            + (~fs["origin_location_key"].isin(G["dim_location"]["location_key"])).sum() + (~fs["dest_location_key"].isin(G["dim_location"]["location_key"])).sum())
        chk("fact_shipment_delivery", "grain: shipment_id is unique", fs["shipment_id"].duplicated().sum())
        fi = G["fact_shipment_item"]
        chk("fact_shipment_item", "FK shipment_key/product_key resolve",
            (~fi["shipment_key"].isin(fs["shipment_key"])).sum() + (~fi["product_key"].isin(G["dim_product"]["product_key"])).sum())
        ff = G["fact_fuel_transaction"]
        chk("fact_fuel_transaction", "FK vehicle/driver/location resolve",
            (~ff["vehicle_key"].isin(G["dim_vehicle"]["vehicle_key"])).sum() + (~ff["driver_key"].isin(G["dim_driver"]["driver_key"])).sum()
            + (~ff["location_key"].isin(G["dim_location"]["location_key"])).sum())
        chk("fact_fuel_transaction", "price within 5% of official price", (ff["price_diff_pct"].abs() > PRICE_TOLERANCE * 100).sum())
        ops["dq_results"] = pd.DataFrame(checks)

        # reconciliation: injected truth vs events detected from data only
        det = {"EXCESSIVE_IDLING": G["fact_idling_event"].rename(columns={"start_ts": "s", "end_ts": "e"}).assign(k=lambda d: d["idle_key"]),
               "ROUTE_DEVIATION": G["fact_route_deviation"].rename(columns={"detected_ts": "s", "resolved_ts": "e"}).assign(k=lambda d: d["deviation_key"]),
               "COLD_CHAIN_BREACH": G["fact_cold_chain_event"].rename(columns={"start_ts": "s", "end_ts": "e"}).assign(k=lambda d: d["event_key"])}
        rec = []
        for _, l in lbl.iterrows():
            d = det[l["anomaly_type"]]
            hit = d[(d["vehicle_id"] == l["vehicle_id"]) & (d["s"] < l["end_ts"]) & (d["e"] > l["start_ts"])]
            rec.append(dict(anomaly_id=l["anomaly_id"], anomaly_type=l["anomaly_type"], vehicle_id=l["vehicle_id"], injected_start=l["start_ts"],
                            detected=len(hit) > 0, detected_event_key=int(hit.iloc[0]["k"]) if len(hit) else None))
        ops["validation_detection_vs_truth"] = pd.DataFrame(rec)

    # ---- 6. output ---------------------------------------------------------
    def write(self, out):
        layers = [("raw", self.raw), ("silver", self.silver), ("gold", self.gold), ("ops", self.ops)]
        for layer, tables in layers:
            os.makedirs(os.path.join(out, layer), exist_ok=True)
            for name, df in tables.items():
                df.to_csv(os.path.join(out, layer, f"{name}.csv"), index=False)
        index = pd.DataFrame([dict(layer=l, table=n, rows=len(df), columns=len(df.columns)) for l, ts in layers for n, df in ts.items()])
        index.to_csv(os.path.join(out, "00_index.csv"), index=False)
        try:
            with pd.ExcelWriter(os.path.join(out, "fleet_sample_all_tables.xlsx"), engine="openpyxl") as xw:
                index.to_excel(xw, sheet_name="00_index", index=False)
                for l, ts in layers:
                    for n, df in ts.items():
                        d = df.copy()
                        for c in d.columns:
                            if str(d[c].dtype).startswith("datetime"):
                                d[c] = d[c].astype(str)
                        d.to_excel(xw, sheet_name=n[:31], index=False)
        except Exception as e:  # Excel is optional
            print("Excel not written:", e)
        return index


def main():
    ap = argparse.ArgumentParser(description="Fleet telematics sample data generator (demo size)")
    ap.add_argument("--telemetry-rows", type=int, default=100, help="approximate telemetry rows to generate")
    ap.add_argument("--interval-sec", type=int, default=600, help="sample interval (real project: 5-10 s)")
    ap.add_argument("--vehicles", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="sample_output")
    a = ap.parse_args()

    g = FleetSample(a)
    g.build_reference()
    g.build_people_assets()
    g.build_streams()
    g.build_silver()
    g.build_gold()
    g.build_ops()
    index = g.write(a.out)

    print(index.to_string(index=False))
    rec = g.ops["validation_detection_vs_truth"]
    print("\nDetection vs injected truth (detected from data only):")
    print(rec.groupby("anomaly_type")["detected"].agg(["sum", "count"]).rename(columns={"sum": "detected", "count": "injected"}).to_string())
    dq = g.ops["dq_results"]
    print("\nData-quality checks:", int((dq.status == "PASS").sum()), "PASS /", int((dq.status == "FAIL").sum()), "FAIL (raw-layer FAILs are expected)")
    trips = g.gold["fact_trip"].merge(g.gold["dim_route"][["route_key", "route_id"]], on="route_key")
    eff = trips.groupby("route_id").apply(lambda d: round(d["distance_km"].sum() / d["fuel_used_l"].sum(), 2), include_groups=False)
    print("\nFuel efficiency (km/l) per route:", eff.to_dict())
    r = g.reefer_eval
    if len(r):
        print("Cold-chain compliance %:", round((~r["above"]).mean() * 100, 1), f"(over {len(r)} reefer readings)")
    print(f"\nWritten to ./{a.out}/ (CSV per table + fleet_sample_all_tables.xlsx)")


if __name__ == "__main__":
    main()