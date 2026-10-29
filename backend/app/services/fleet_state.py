"""Live fleet picture built from the stream, as plain logic (no Kafka, no asyncio, so it can be tested with dicts):
the latest telemetry and reefer row per vehicle_id, alerts made from the row flags, and the live KPIs.
Every time rule uses event_ts (never "number of batches"), so it works for any upstream batch interval."""
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta

from ..domain.stream_source import StreamKind
from ..schemas.stream import AlertRow, AnomalyType, LiveKpis

# Row flag -> anomaly_type: the alert is active while the flag is true in the truck's latest row
FLAG_ALERTS: dict[StreamKind, dict[str, AnomalyType]] = {
    "telemetry": {"is_speeding": "SPEEDING", "is_engine_overheating": "ENGINE_OVERHEATING", "is_low_fuel": "LOW_FUEL"},
    "reefer": {"is_temp_breach": "COLD_CHAIN_BREACH", "is_reefer_unit_failure": "REEFER_UNIT_FAILURE"},
}
# Alerts that end when a truck's row of this kind is dropped (EXCESSIVE_IDLING comes from telemetry rows)
ALERT_TYPES: dict[StreamKind, list[AnomalyType]] = {
    "telemetry": [*FLAG_ALERTS["telemetry"].values(), "EXCESSIVE_IDLING"],
    "reefer": [*FLAG_ALERTS["reefer"].values()],
}
EXCESSIVE_IDLING_AFTER = timedelta(minutes=30)  # is_idling for this long (catalog KPI 34, assumption)
FEED_SIZE = 40  # alert changes kept for a new viewer's feed (same as FEED_SIZE in the dashboard)

Event = tuple[str, object]  # (SSE event name, data)


def _time(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp)


def _iso(moment: datetime) -> str:
    """Same format as event_ts, e.g. 2026-10-29T09:41:14Z"""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _compliance_pct(rows: list[dict]) -> float | None:
    """Share of reefer rows without is_temp_breach (%), null when there is no row."""
    return round(sum(not row.get("is_temp_breach") for row in rows) / len(rows) * 100, 1) if rows else None


class FleetState:
    def __init__(self, history: timedelta):
        self._history = history
        self._rows: dict[StreamKind, dict[str, dict]] = {"telemetry": {}, "reefer": {}}  # kind -> vehicle_id -> latest row
        self._idle_since: dict[str, str] = {}  # vehicle_id -> event_ts of the first is_idling row of the current idle
        self._active: dict[tuple[str, str], AlertRow] = {}  # (vehicle_id, anomaly_type) -> active alert
        self._feed: deque[AlertRow] = deque(maxlen=FEED_SIZE)  # latest alert changes, oldest first
        self._new_rows: dict[StreamKind, dict[str, dict]] = {"telemetry": {}, "reefer": {}}  # not sent yet
        self._new_alerts: list[AlertRow] = []  # not sent yet
        self._changed = False  # True when the KPIs must be sent again
        self._last_received_at: datetime | None = None

    def apply(self, kind: StreamKind, row: dict, now: datetime) -> None:
        """Keeps `row` only if it is inside the history window and newer than the truck's stored row.
        This drops duplicates (same event_ts, ~0.4%) and late rows, and makes reading the history again safe."""
        vehicle_id, event_ts = row["vehicle_id"], _time(row["event_ts"])
        stored = self._rows[kind].get(vehicle_id)
        if event_ts < now - self._history or (stored and event_ts <= _time(stored["event_ts"])):
            return
        self._rows[kind][vehicle_id] = row
        self._new_rows[kind][vehicle_id] = row
        self._changed = True
        self._last_received_at = now
        for flag, anomaly_type in FLAG_ALERTS[kind].items():
            self._set_alert(vehicle_id, anomaly_type, bool(row.get(flag)), row["event_ts"])
        if kind == "telemetry":
            self._update_idling(row)

    def take_changes(self, now: datetime) -> list[Event]:
        """Events for every viewer since the last call (empty when nothing changed). Drops old rows first."""
        self._expire(now)
        if not self._changed:
            return []
        events: list[Event] = [(kind, list(rows.values())) for kind, rows in self._new_rows.items() if rows]
        events += [("alert", alert) for alert in self._new_alerts]
        events.append(("kpis", self.kpis(now)))
        self._new_rows = {"telemetry": {}, "reefer": {}}
        self._new_alerts = []
        self._changed = False
        return events

    def snapshot(self, now: datetime) -> list[Event]:
        """Everything a new viewer needs, so the page is never empty: every kept row, the active alerts, the alerts
        of the last FEED_SIZE changes (latest version of each, oldest first, so the newest ends on top of the feed)
        and the KPIs."""
        oldest = now - self._history
        feed: dict[str, AlertRow] = {}  # anomaly_id -> latest version, in order of its latest change
        for alert in self._feed:
            if _time(alert.end_ts or alert.start_ts) >= oldest:
                feed.pop(alert.anomaly_id, None)
                feed[alert.anomaly_id] = alert
        alerts = [alert for alert in self._active.values() if alert.anomaly_id not in feed] + list(feed.values())
        return [
            ("telemetry", list(self._rows["telemetry"].values())),
            ("reefer", list(self._rows["reefer"].values())),
            *[("alert", alert) for alert in alerts],
            ("kpis", self.kpis(now)),
        ]

    def kpis(self, now: datetime) -> LiveKpis:
        telemetry = list(self._rows["telemetry"].values())
        reefer = list(self._rows["reefer"].values())
        valid = [row for row in reefer if row.get("cargo_temp_f") is not None]  # null = sensor dropped (catalog A.6)
        by_commodity = defaultdict(list)
        for row in valid:
            if row.get("commodity_type"):
                by_commodity[row["commodity_type"]].append(row)
        newest = max((row["event_ts"] for row in telemetry + reefer), key=_time, default=None)
        return LiveKpis(
            as_of=_iso(now),
            trucks_reporting=len(telemetry),
            motion_status=dict(Counter(row["motion_status"] for row in telemetry if row.get("motion_status"))),
            is_speeding=sum(bool(row.get("is_speeding")) for row in telemetry),
            is_engine_overheating=sum(bool(row.get("is_engine_overheating")) for row in telemetry),
            is_low_fuel=sum(bool(row.get("is_low_fuel")) for row in telemetry),
            reefers_reporting=len(reefer),
            is_reefer_unit_failure=sum(bool(row.get("is_reefer_unit_failure")) for row in reefer),
            cold_chain_compliance_pct=_compliance_pct(valid),
            cold_chain_compliance_pct_by_commodity={commodity: _compliance_pct(rows) for commodity, rows in sorted(by_commodity.items())},
            newest_event_ts=newest,
            data_age_min=round((now - _time(newest)).total_seconds() / 60, 1) if newest else None,
            last_received_at=_iso(self._last_received_at) if self._last_received_at else None,
        )

    def _update_idling(self, row: dict) -> None:
        """EXCESSIVE_IDLING starts when is_idling has been true for EXCESSIVE_IDLING_AFTER (by event_ts), with
        start_ts = the first idle row, and ends with the first row that is not idling."""
        vehicle_id = row["vehicle_id"]
        if row.get("is_idling"):
            self._idle_since.setdefault(vehicle_id, row["event_ts"])
        else:
            self._idle_since.pop(vehicle_id, None)
        since = self._idle_since.get(vehicle_id)
        idle_too_long = since is not None and _time(row["event_ts"]) - _time(since) >= EXCESSIVE_IDLING_AFTER
        self._set_alert(vehicle_id, "EXCESSIVE_IDLING", idle_too_long, row["event_ts"], start_ts=since)

    def _set_alert(self, vehicle_id: str, anomaly_type: AnomalyType, on: bool, event_ts: str, start_ts: str | None = None) -> None:
        """Starts the alert when `on` becomes true, ends it (end_ts = event_ts) when `on` becomes false."""
        active = self._active.get((vehicle_id, anomaly_type))
        if on and active is None:
            start_ts = start_ts or event_ts
            self._publish(AlertRow(anomaly_id=f"{vehicle_id}-{anomaly_type}-{start_ts}", anomaly_type=anomaly_type,
                                   vehicle_id=vehicle_id, trip_id=None, start_ts=start_ts, end_ts=None))
        elif not on and active is not None:
            self._publish(active.model_copy(update={"end_ts": event_ts}))

    def _publish(self, alert: AlertRow) -> None:
        key = (alert.vehicle_id, alert.anomaly_type)
        if alert.end_ts is None:
            self._active[key] = alert
        else:
            del self._active[key]
        self._feed.append(alert)
        self._new_alerts.append(alert)
        self._changed = True

    def _expire(self, now: datetime) -> None:
        """Drops rows whose event_ts is older than the history window. Their active alerts end at the row's last
        event_ts, so viewers do not keep them forever."""
        oldest = now - self._history
        for kind, rows in self._rows.items():
            for vehicle_id in [vehicle_id for vehicle_id, row in rows.items() if _time(row["event_ts"]) < oldest]:
                row = rows.pop(vehicle_id)
                self._new_rows[kind].pop(vehicle_id, None)
                for anomaly_type in ALERT_TYPES[kind]:
                    self._set_alert(vehicle_id, anomaly_type, False, row["event_ts"])
                if kind == "telemetry":
                    self._idle_since.pop(vehicle_id, None)
                self._changed = True
