import sqlite3
from dataclasses import dataclass
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    model TEXT NOT NULL,
    temperature REAL NOT NULL,
    prompt_variant TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    score REAL,
    pass_fail TEXT,
    cost_usd REAL,
    latency_ms REAL,
    timestamp TEXT NOT NULL,
    raw_response TEXT,
    error TEXT
)
"""


@dataclass
class ResultRow:
    run_id: str
    model: str
    temperature: float
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


class ResultsStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        conn = sqlite3.connect(db_path)
        conn.execute(SCHEMA)
        conn.commit()
        conn.close()

    def write_result(self, row: ResultRow) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO results
               (run_id, model, temperature, prompt_variant, task_id, task_type,
                score, pass_fail, cost_usd, latency_ms, timestamp, raw_response, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row.run_id, row.model, row.temperature, row.prompt_variant, row.task_id,
             row.task_type, row.score, row.pass_fail, row.cost_usd, row.latency_ms,
             row.timestamp, row.raw_response, row.error),
        )
        conn.commit()
        conn.close()

    def all_results(self) -> list[ResultRow]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM results")
        rows = [
            ResultRow(
                run_id=r["run_id"], model=r["model"], temperature=r["temperature"],
                prompt_variant=r["prompt_variant"], task_id=r["task_id"],
                task_type=r["task_type"], score=r["score"], pass_fail=r["pass_fail"],
                cost_usd=r["cost_usd"], latency_ms=r["latency_ms"],
                timestamp=r["timestamp"], raw_response=r["raw_response"], error=r["error"],
            )
            for r in cursor.fetchall()
        ]
        conn.close()
        return rows
