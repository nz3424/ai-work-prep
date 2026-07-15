import sqlite3
from dataclasses import dataclass
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    label TEXT NOT NULL,
    model TEXT NOT NULL,
    temperature REAL,
    effort TEXT,
    prompt_variant TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    score REAL,
    pass_fail TEXT,
    cost_usd REAL,
    judge_cost_usd REAL,
    latency_ms REAL,
    timestamp TEXT NOT NULL,
    raw_response TEXT,
    error TEXT
)
"""


@dataclass
class ResultRow:
    run_id: str
    label: str
    model: str
    # None when the model doesn't accept temperature (e.g. sonnet-5) so the DB
    # never records a value that wasn't actually sent to the API.
    temperature: Optional[float]
    prompt_variant: str
    task_id: str
    task_type: str
    score: Optional[float]
    pass_fail: Optional[str]
    cost_usd: Optional[float]
    latency_ms: Optional[float]
    timestamp: str
    raw_response: Optional[str]
    error: Optional[str]
    judge_cost_usd: Optional[float] = None
    effort: Optional[str] = None


EXPECTED_COLUMNS = [
    "id", "run_id", "label", "model", "temperature", "effort", "prompt_variant",
    "task_id", "task_type", "score", "pass_fail", "cost_usd", "judge_cost_usd",
    "latency_ms", "timestamp", "raw_response", "error",
]


class ResultsStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        conn = sqlite3.connect(db_path)
        conn.execute(SCHEMA)
        self._migrate_if_stale(conn)
        conn.commit()
        conn.close()

    def _migrate_if_stale(self, conn: sqlite3.Connection) -> None:
        # The schema has changed shape (new columns, relaxed constraints) more than
        # once as MODEL_CONFIGS evolved. ALTER TABLE ADD COLUMN can't fix a stale
        # NOT NULL constraint on an existing column, so rebuild from EXPECTED_COLUMNS
        # instead, carrying over whatever data already exists.
        actual_columns = [r[1] for r in conn.execute("PRAGMA table_info(results)")]
        if actual_columns == EXPECTED_COLUMNS:
            return
        conn.execute("ALTER TABLE results RENAME TO results_old")
        conn.execute(SCHEMA)
        targets = [c for c in EXPECTED_COLUMNS if c != "id"]
        # label predates this migration and is NOT NULL with no default, so rows from
        # before it existed need an explicit backfill value rather than NULL.
        sources = [c if c in actual_columns else ("'legacy'" if c == "label" else "NULL") for c in targets]
        conn.execute(
            f"INSERT INTO results ({', '.join(targets)}) SELECT {', '.join(sources)} FROM results_old"
        )
        conn.execute("DROP TABLE results_old")

    def write_result(self, row: ResultRow) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO results
               (run_id, label, model, temperature, effort, prompt_variant, task_id, task_type,
                score, pass_fail, cost_usd, judge_cost_usd, latency_ms, timestamp, raw_response, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row.run_id, row.label, row.model, row.temperature, row.effort, row.prompt_variant,
             row.task_id, row.task_type, row.score, row.pass_fail, row.cost_usd, row.judge_cost_usd,
             row.latency_ms, row.timestamp, row.raw_response, row.error),
        )
        conn.commit()
        conn.close()

    def all_results(self) -> list[ResultRow]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM results")
        rows = [
            ResultRow(
                run_id=r["run_id"], label=r["label"], model=r["model"], temperature=r["temperature"],
                effort=r["effort"], prompt_variant=r["prompt_variant"], task_id=r["task_id"],
                task_type=r["task_type"], score=r["score"], pass_fail=r["pass_fail"],
                cost_usd=r["cost_usd"], judge_cost_usd=r["judge_cost_usd"], latency_ms=r["latency_ms"],
                timestamp=r["timestamp"], raw_response=r["raw_response"], error=r["error"],
            )
            for r in cursor.fetchall()
        ]
        conn.close()
        return rows

    def latest_run_id(self) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT run_id FROM results ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def results_for_run(self, run_id: str) -> list[ResultRow]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM results WHERE run_id = ?", (run_id,))
        rows = [
            ResultRow(
                run_id=r["run_id"], label=r["label"], model=r["model"], temperature=r["temperature"],
                effort=r["effort"], prompt_variant=r["prompt_variant"], task_id=r["task_id"],
                task_type=r["task_type"], score=r["score"], pass_fail=r["pass_fail"],
                cost_usd=r["cost_usd"], judge_cost_usd=r["judge_cost_usd"], latency_ms=r["latency_ms"],
                timestamp=r["timestamp"], raw_response=r["raw_response"], error=r["error"],
            )
            for r in cursor.fetchall()
        ]
        conn.close()
        return rows
