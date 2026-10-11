"""TimescaleDB / Tiger Data persistence. Enabled when DATABASE_URL is set.

The in-memory store stays the source of truth for the live demo (so it runs with Wi-Fi off); every reading,
rule evaluation, alert, delivery and lifecycle event is mirrored into hypertables, and the readings API serves
15-minute rollups from the readings_15m continuous aggregate when the database is connected.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("siren.db")
SCHEMA = Path(__file__).with_name("models.sql")
DEMO_TABLES = ["readings", "rule_evaluations", "incidents", "alerts", "alert_deliveries", "alert_events",
               "photo_reports", "lead_time_results"]


class TimescaleSink:
    def __init__(self, url: str):
        import psycopg  # imported lazily so the offline demo has no hard dependency

        self.psycopg = psycopg
        self.url = url
        self.conn = psycopg.connect(url, autocommit=True)
        self.q: queue.Queue = queue.Queue(maxsize=20000)
        self.healthy = True
        self.errors = 0
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    # -------------------------------------------------- setup

    def apply_schema(self) -> None:
        with self.psycopg.connect(self.url, autocommit=True) as c:
            for stmt in [s.strip() for s in SCHEMA.read_text().split(";\n") if s.strip()]:
                try:
                    c.execute(stmt)
                except Exception as e:  # already-exists noise on re-runs is fine
                    log.info("schema stmt skipped: %s", str(e).splitlines()[0])

    def reset_demo(self) -> None:
        self.q.put(("reset", None))

    # -------------------------------------------------- writes (queued, off the request path)

    def reading(self, r: dict) -> None:
        self._put("INSERT INTO readings (time, source, station_id, metric, value, quality, source_url) "
                  "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                  (r["time"], r["source"], r["station_id"], r["metric"], r["value"], r.get("quality"), r.get("source_url")))

    def rule_evaluation(self, row: dict) -> None:
        self._put("INSERT INTO rule_evaluations (time, zone_id, rule_id, rule_version, fired, severity, inputs, "
                  "inputs_hash, missing_data) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                  (row["time"], row["zone_id"], row["rule_id"], row["rule_version"], row["fired"], row["severity"],
                   json.dumps(row["inputs"], default=str), row["inputs_hash"], json.dumps(row["missing_data"])))

    def alert_event(self, ev: dict) -> None:
        self._put("INSERT INTO alert_events (time, alert_id, delivery_id, from_state, to_state, actor, note) "
                  "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                  (ev["time"], ev["alert_id"], ev["delivery_id"], ev["from_state"], ev["to_state"], ev["actor"], ev["note"]))

    def upsert(self, table: str, row: dict, key: str | None = "id") -> None:
        cols = list(row)
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
        if key:
            sql += f" ON CONFLICT ({key}) DO UPDATE SET " + ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != key)
        self._put(sql, tuple(row[c] for c in cols))

    def _put(self, sql: str, params: tuple) -> None:
        try:
            self.q.put_nowait(("sql", (sql, params)))
        except queue.Full:
            self.errors += 1

    def _run(self) -> None:
        while True:
            kind, payload = self.q.get()
            try:
                if kind == "reset":
                    self.conn.execute("TRUNCATE " + ", ".join(DEMO_TABLES))
                else:
                    self.conn.execute(*payload)
                self.healthy = True
            except Exception as e:
                self.errors += 1
                self.healthy = False
                log.warning("db write failed: %s", str(e).splitlines()[0])
                try:
                    self.conn = self.psycopg.connect(self.url, autocommit=True)
                except Exception:
                    pass

    def flush(self, timeout: float = 10.0) -> None:
        import time
        end = time.monotonic() + timeout
        while not self.q.empty() and time.monotonic() < end:
            time.sleep(0.05)

    # -------------------------------------------------- reads

    def rollup_15m(self, station: str, metric: str, start: datetime, end: datetime) -> list[dict] | None:
        """Read the readings_15m continuous aggregate (used by /api/readings?bucket=15m)."""
        try:
            with self.psycopg.connect(self.url, autocommit=True) as c:
                rows = c.execute("SELECT bucket, max_v, last_v, sum_v, n FROM readings_15m WHERE station_id=%s "
                                 "AND metric=%s AND bucket >= %s AND bucket <= %s ORDER BY bucket",
                                 (station, metric, start, end)).fetchall()
            return [{"bucket": r[0].isoformat(), "max_v": r[1], "last_v": r[2], "sum_v": r[3], "n": r[4]} for r in rows]
        except Exception as e:
            log.warning("aggregate read failed: %s", e)
            return None

    def stats(self) -> dict:
        try:
            with self.psycopg.connect(self.url, autocommit=True) as c:
                out = {"connected": True}
                out["readings"] = c.execute("SELECT count(*) FROM readings").fetchone()[0]
                out["rule_evaluations"] = c.execute("SELECT count(*) FROM rule_evaluations").fetchone()[0]
                out["alert_events"] = c.execute("SELECT count(*) FROM alert_events").fetchone()[0]
                try:
                    row = c.execute("SELECT before_compression_total_bytes, after_compression_total_bytes "
                                    "FROM hypertable_compression_stats('readings')").fetchone()
                    out["compression"] = {"before_bytes": row[0], "after_bytes": row[1]} if row and row[0] else None
                except Exception:
                    out["compression"] = None
                out["queue"] = self.q.qsize()
                out["write_errors"] = self.errors
                return out
        except Exception as e:
            return {"connected": False, "error": str(e).splitlines()[0]}


def make_sink(url: str) -> TimescaleSink | None:
    if not url:
        return None
    try:
        sink = TimescaleSink(url)
        sink.apply_schema()
        log.info("TimescaleDB sink enabled")
        return sink
    except Exception as e:
        log.warning("TimescaleDB unavailable, continuing in memory: %s", e)
        return None
