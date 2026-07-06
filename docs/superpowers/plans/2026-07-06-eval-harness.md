# LLM Evaluation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a harness that runs Claude Opus/Sonnet/Haiku (plus prompt/temperature variants) against 5 code-gen tasks (scored by real pytest execution in Docker) and 5 API-design tasks (scored by Opus-as-judge), storing results in SQLite and producing a static HTML report + CSV export.

**Architecture:** A sequential runner (`run_eval.py`) builds a matrix of (model config × task), calls the Anthropic API for each, routes the response to the matching scorer (Docker-sandboxed pytest for code-gen, Opus-judge rubric scoring for API-design), and writes one row per result to SQLite immediately. A separate `report.py` reads the full results table and renders a self-contained HTML report plus a CSV export.

**Tech Stack:** Python 3.11+, `anthropic` SDK, `docker` (docker-py), stdlib `sqlite3`, `pytest` for both the harness's own tests and the sandboxed scoring of generated code.

## Global Constraints

- Anthropic API only. Models used: `claude-opus-4-8` (judge only, never scored as a subject), `claude-sonnet-5`, `claude-haiku-4-5-20251001` (subjects).
- Storage is SQLite via the stdlib `sqlite3` module — no ORM.
- Code-gen sandboxing uses `docker` (docker-py) against the `python:3.11-slim` image, with `network_disabled=True`, `mem_limit="256m"`, and a 10-second hard timeout enforced by killing the container.
- Execution is strictly sequential — no async, no threading, no multiprocessing.
- Exactly 5 code-gen tasks and 5 API-design tasks for the MVP suite.
- Reporting is a self-contained static HTML file (inline CSS/JS, no external CDN) plus a CSV export — no live/served dashboard.
- All new code lives under `eval-harness/` at the repo root, sibling to `docker-101/`, `aws-deploy-demo/`, `hermes-assistant/`.
- Every module must be testable without spending real API money or requiring Docker, **except** `scoring/test_scorer.py`'s own tests, which intentionally exercise real Docker (per the design spec's "golden task" testing requirement) — Docker Desktop must be running for those.

---

### Task 1: Project Scaffolding + Storage

**Files:**
- Create: `eval-harness/requirements.txt`
- Create: `eval-harness/conftest.py`
- Create: `eval-harness/storage.py`
- Test: `eval-harness/tests/test_storage.py`

**Interfaces:**
- Produces: `ResultRow` dataclass with fields `run_id: str, model: str, temperature: float, prompt_variant: str, task_id: str, task_type: str, score: Optional[float], pass_fail: Optional[str], cost_usd: Optional[float], latency_ms: Optional[float], timestamp: str, raw_response: Optional[str], error: Optional[str]`.
- Produces: `ResultsStore` class with `__init__(self, db_path: str)`, `write_result(self, row: ResultRow) -> None`, `all_results(self) -> list[ResultRow]`.

- [ ] **Step 1: Create the project skeleton and dependency list**

```bash
mkdir -p eval-harness/tests eval-harness/tasks eval-harness/scoring
touch eval-harness/tasks/__init__.py eval-harness/scoring/__init__.py
```

Create `eval-harness/requirements.txt`:

```
anthropic>=0.40.0
docker>=7.0.0
pytest>=8.0.0
```

Create `eval-harness/conftest.py` (empty — its presence makes pytest add `eval-harness/` to `sys.path` so test files can `import storage`, `import run_eval`, etc.):

```python
# Present so pytest adds this directory to sys.path for imports.
```

Install dependencies:

```bash
cd eval-harness && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
```

- [ ] **Step 2: Write the failing test for storage**

Create `eval-harness/tests/test_storage.py`:

```python
import os
import tempfile

from storage import ResultsStore, ResultRow


def _make_row(**overrides):
    defaults = dict(
        run_id="run1",
        model="claude-sonnet-5",
        temperature=0.2,
        prompt_variant="default",
        task_id="codegen_01",
        task_type="codegen",
        score=1.0,
        pass_fail="pass",
        cost_usd=0.001,
        latency_ms=250.0,
        timestamp="2026-07-06T00:00:00",
        raw_response="def reverse(s): return s[::-1]",
        error=None,
    )
    defaults.update(overrides)
    return ResultRow(**defaults)


def test_write_and_read_result():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        store = ResultsStore(path)
        store.write_result(_make_row())
        results = store.all_results()
        assert len(results) == 1
        assert results[0].task_id == "codegen_01"
        assert results[0].score == 1.0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_multiple_writes_accumulate():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        store = ResultsStore(path)
        store.write_result(_make_row(task_id="codegen_01"))
        store.write_result(_make_row(task_id="codegen_02", score=0.0, pass_fail="fail"))
        results = store.all_results()
        assert len(results) == 2
        assert {r.task_id for r in results} == {"codegen_01", "codegen_02"}
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_nullable_fields_roundtrip_as_none():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        store = ResultsStore(path)
        store.write_result(_make_row(score=None, pass_fail=None, cost_usd=None,
                                      latency_ms=None, raw_response=None, error="boom"))
        results = store.all_results()
        assert results[0].score is None
        assert results[0].error == "boom"
    finally:
        if os.path.exists(path):
            os.remove(path)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd eval-harness && pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'storage'`

- [ ] **Step 4: Implement storage.py**

Create `eval-harness/storage.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd eval-harness && pytest tests/test_storage.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add eval-harness/requirements.txt eval-harness/conftest.py eval-harness/storage.py eval-harness/tests/test_storage.py eval-harness/tasks/__init__.py eval-harness/scoring/__init__.py
git commit -m "feat(eval-harness): add project scaffolding and SQLite results storage"
```

---

### Task 2: LLM Client (Anthropic wrapper + cost calculation)

**Files:**
- Create: `eval-harness/llm_client.py`
- Test: `eval-harness/tests/test_llm_client.py`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: `LLMResponse` dataclass with fields `text: str, input_tokens: int, output_tokens: int, latency_ms: float, cost_usd: float`. `compute_cost(model: str, input_tokens: int, output_tokens: int) -> float`. `LLMClient` class with `__init__(self, client=None)` and `call(self, model: str, prompt: str, temperature: float, max_tokens: int = 2048) -> LLMResponse`.

- [ ] **Step 1: Write the failing tests**

Create `eval-harness/tests/test_llm_client.py`:

```python
from types import SimpleNamespace

from llm_client import LLMClient, compute_cost


class FakeMessages:
    def __init__(self, response):
        self._response = response

    def create(self, **kwargs):
        return self._response


class FakeAnthropic:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def make_fake_response(text="hello", input_tokens=10, output_tokens=5):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def test_call_returns_parsed_response():
    fake_client = FakeAnthropic(make_fake_response(text="def reverse(s): return s[::-1]"))
    client = LLMClient(client=fake_client)
    result = client.call(model="claude-sonnet-5", prompt="reverse a string", temperature=0.2)
    assert result.text == "def reverse(s): return s[::-1]"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.cost_usd > 0
    assert result.latency_ms >= 0


def test_compute_cost_known_model():
    cost = compute_cost("claude-sonnet-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == 3.0 + 15.0


def test_compute_cost_haiku_is_cheaper_than_opus():
    haiku_cost = compute_cost("claude-haiku-4-5-20251001", input_tokens=1000, output_tokens=1000)
    opus_cost = compute_cost("claude-opus-4-8", input_tokens=1000, output_tokens=1000)
    assert haiku_cost < opus_cost
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd eval-harness && pytest tests/test_llm_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm_client'`

- [ ] **Step 3: Implement llm_client.py**

Create `eval-harness/llm_client.py`:

```python
import time
from dataclasses import dataclass
from typing import Optional

from anthropic import Anthropic

PRICING_PER_MTOK = {
    "claude-opus-4-8": {"input": 15.0, "output": 75.0},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
}


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = PRICING_PER_MTOK[model]
    return (input_tokens / 1_000_000) * prices["input"] + (output_tokens / 1_000_000) * prices["output"]


class LLMClient:
    def __init__(self, client: Optional[Anthropic] = None):
        # max_retries=2 gives up to 3 total attempts on transient failures.
        self.client = client or Anthropic(max_retries=2)

    def call(self, model: str, prompt: str, temperature: float, max_tokens: int = 2048) -> LLMResponse:
        start = time.monotonic()
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - start) * 1000
        text = "".join(block.text for block in response.content if block.type == "text")
        cost = compute_cost(model, response.usage.input_tokens, response.usage.output_tokens)
        return LLMResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd eval-harness && pytest tests/test_llm_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add eval-harness/llm_client.py eval-harness/tests/test_llm_client.py
git commit -m "feat(eval-harness): add Anthropic client wrapper with cost calculation"
```

---

### Task 3: Code-Gen Scorer (Docker-sandboxed pytest execution)

**Files:**
- Create: `eval-harness/scoring/base.py`
- Create: `eval-harness/scoring/test_scorer.py`
- Test: `eval-harness/tests/test_test_scorer.py`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: `ScoreResult` dataclass with fields `score: Optional[float], pass_fail: Optional[str], raw_output: str, error: Optional[str] = None`. `score_codegen(generated_code: str, test_code: str) -> ScoreResult`.

**Note:** these tests require Docker Desktop running locally. The first run pulls `python:3.11-slim` (~50MB) and may take a minute.

- [ ] **Step 1: Write the failing tests (golden good/bad solutions)**

Create `eval-harness/scoring/base.py`:

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class ScoreResult:
    score: Optional[float]
    pass_fail: Optional[str]
    raw_output: str
    error: Optional[str] = None
```

Create `eval-harness/tests/test_test_scorer.py`:

```python
from scoring.test_scorer import score_codegen

GOOD_CODE = "def reverse_string(s):\n    return s[::-1]\n"
BAD_CODE = "def reverse_string(s):\n    return s\n"
BROKEN_CODE = "def reverse_string(s)\n    return s[::-1]\n"  # syntax error: missing colon

TEST_CODE = (
    "from solution import reverse_string\n\n"
    "def test_reverse_string():\n"
    "    assert reverse_string('hello') == 'olleh'\n"
)


def test_golden_good_solution_passes():
    result = score_codegen(GOOD_CODE, TEST_CODE)
    assert result.pass_fail == "pass"
    assert result.score == 1.0


def test_golden_bad_solution_fails():
    result = score_codegen(BAD_CODE, TEST_CODE)
    assert result.pass_fail == "fail"
    assert result.score == 0.0


def test_syntax_error_fails_without_crashing():
    result = score_codegen(BROKEN_CODE, TEST_CODE)
    assert result.pass_fail == "fail"
    assert result.score == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd eval-harness && pytest tests/test_test_scorer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scoring.test_scorer'`

- [ ] **Step 3: Implement scoring/test_scorer.py**

Create `eval-harness/scoring/test_scorer.py`:

```python
import os
import tempfile

import docker

from scoring.base import ScoreResult

DOCKER_IMAGE = "python:3.11-slim"
TIMEOUT_SECONDS = 10


def score_codegen(generated_code: str, test_code: str) -> ScoreResult:
    client = docker.from_env()
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "solution.py"), "w") as f:
            f.write(generated_code)
        with open(os.path.join(tmpdir, "test_solution.py"), "w") as f:
            f.write(test_code)

        container = client.containers.run(
            DOCKER_IMAGE,
            command=["python", "-m", "pytest", "test_solution.py", "-v", "-p", "no:cacheprovider"],
            volumes={tmpdir: {"bind": "/work", "mode": "rw"}},
            working_dir="/work",
            detach=True,
            mem_limit="256m",
            network_disabled=True,
        )
        try:
            result = container.wait(timeout=TIMEOUT_SECONDS)
            logs = container.logs().decode("utf-8", errors="replace")
            exit_code = result["StatusCode"]
        except Exception as exc:
            container.kill()
            logs = container.logs().decode("utf-8", errors="replace")
            return ScoreResult(score=0.0, pass_fail="fail", raw_output=logs, error=f"timeout_or_error: {exc}")
        finally:
            container.remove(force=True)

        if exit_code == 0:
            return ScoreResult(score=1.0, pass_fail="pass", raw_output=logs)
        return ScoreResult(score=0.0, pass_fail="fail", raw_output=logs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd eval-harness && pytest tests/test_test_scorer.py -v`
Expected: 3 passed (first run may take longer while Docker pulls `python:3.11-slim`)

- [ ] **Step 5: Commit**

```bash
git add eval-harness/scoring/base.py eval-harness/scoring/test_scorer.py eval-harness/tests/test_test_scorer.py
git commit -m "feat(eval-harness): add Docker-sandboxed code-gen scorer"
```

---

### Task 4: API-Design Judge Scorer

**Files:**
- Create: `eval-harness/scoring/judge_scorer.py`
- Test: `eval-harness/tests/test_judge_scorer.py`

**Interfaces:**
- Consumes: `ScoreResult` from `scoring/base.py` (Task 3).
- Produces: `score_api_design(llm_client, task_prompt: str, rubric: str, response_text: str) -> ScoreResult`. Expects `llm_client` to expose `.call(model: str, prompt: str, temperature: float, max_tokens: int = 2048)` returning an object with a `.text` attribute (matches `LLMClient`/`LLMResponse` from Task 2, but any object with that interface works — this is why tests use a lightweight fake rather than importing `LLMClient`).

- [ ] **Step 1: Write the failing tests**

Create `eval-harness/tests/test_judge_scorer.py`:

```python
from dataclasses import dataclass

from scoring.judge_scorer import score_api_design


@dataclass
class FakeLLMResponse:
    text: str


class FakeLLMClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def call(self, model, prompt, temperature, max_tokens=2048):
        self.calls.append((model, prompt, temperature))
        return FakeLLMResponse(text=self._responses.pop(0))


def test_score_api_design_parses_valid_json():
    client = FakeLLMClient(['{"score": 8, "rationale": "Good use of REST conventions"}'])
    result = score_api_design(client, "Design a REST API for a todo app", "rubric text", "response text")
    assert result.score == 8.0
    assert result.error is None


def test_score_api_design_retries_on_bad_json_then_succeeds():
    client = FakeLLMClient(["not json at all", '{"score": 5, "rationale": "ok"}'])
    result = score_api_design(client, "prompt", "rubric", "response")
    assert result.score == 5.0
    assert len(client.calls) == 2


def test_score_api_design_gives_up_after_second_failure():
    client = FakeLLMClient(["not json", "still not json"])
    result = score_api_design(client, "prompt", "rubric", "response")
    assert result.score is None
    assert result.error == "judge_parse_failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd eval-harness && pytest tests/test_judge_scorer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scoring.judge_scorer'`

- [ ] **Step 3: Implement scoring/judge_scorer.py**

Create `eval-harness/scoring/judge_scorer.py`:

```python
import json

from scoring.base import ScoreResult

JUDGE_MODEL = "claude-opus-4-8"

JUDGE_PROMPT_TEMPLATE = """You are grading an API design response against a rubric.

Original task prompt:
{task_prompt}

Rubric:
{rubric}

Candidate response to grade:
{response_text}

Respond with ONLY a JSON object, no other text, in this exact shape:
{{"score": <number 0-10>, "rationale": "<one sentence>"}}
"""


def score_api_design(llm_client, task_prompt: str, rubric: str, response_text: str) -> ScoreResult:
    prompt = JUDGE_PROMPT_TEMPLATE.format(task_prompt=task_prompt, rubric=rubric, response_text=response_text)
    judge_response = llm_client.call(model=JUDGE_MODEL, prompt=prompt, temperature=0.0)
    parsed = _parse_judge_output(judge_response.text)

    if parsed is None:
        strict_prompt = prompt + "\n\nRespond with ONLY the JSON object and nothing else."
        judge_response = llm_client.call(model=JUDGE_MODEL, prompt=strict_prompt, temperature=0.0)
        parsed = _parse_judge_output(judge_response.text)

    if parsed is None:
        return ScoreResult(score=None, pass_fail=None, raw_output=judge_response.text, error="judge_parse_failed")

    return ScoreResult(score=parsed["score"], pass_fail=None, raw_output=judge_response.text)


def _parse_judge_output(text: str):
    try:
        data = json.loads(text.strip())
        return {"score": float(data["score"]), "rationale": data.get("rationale", "")}
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd eval-harness && pytest tests/test_judge_scorer.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add eval-harness/scoring/judge_scorer.py eval-harness/tests/test_judge_scorer.py
git commit -m "feat(eval-harness): add Opus LLM-as-judge scorer for API-design tasks"
```

---

### Task 5: Model Configs + Task Suite

**Files:**
- Create: `eval-harness/configs.py`
- Create: `eval-harness/tasks/codegen_tasks.py`
- Create: `eval-harness/tasks/apidesign_tasks.py`
- Test: `eval-harness/tests/test_configs_and_tasks.py`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: `ModelConfig` dataclass (`label: str, model: str, temperature: float, prompt_variant: str, judge_only: bool = False`) and `MODEL_CONFIGS: list[ModelConfig]`. `CodegenTask` dataclass (`task_id: str, prompt: str, test_code: str`) and `CODEGEN_TASKS: list[CodegenTask]`. `ApiDesignTask` dataclass (`task_id: str, prompt: str, rubric: str`) and `API_DESIGN_TASKS: list[ApiDesignTask]`.

- [ ] **Step 1: Write the failing tests**

Create `eval-harness/tests/test_configs_and_tasks.py`:

```python
from configs import MODEL_CONFIGS
from tasks.codegen_tasks import CODEGEN_TASKS
from tasks.apidesign_tasks import API_DESIGN_TASKS


def test_exactly_one_judge_only_config():
    judge_configs = [c for c in MODEL_CONFIGS if c.judge_only]
    assert len(judge_configs) == 1
    assert judge_configs[0].model == "claude-opus-4-8"


def test_subject_configs_exclude_opus():
    subject_models = {c.model for c in MODEL_CONFIGS if not c.judge_only}
    assert "claude-opus-4-8" not in subject_models


def test_five_codegen_tasks_with_unique_ids():
    assert len(CODEGEN_TASKS) == 5
    ids = [t.task_id for t in CODEGEN_TASKS]
    assert len(set(ids)) == 5


def test_five_api_design_tasks_with_unique_ids():
    assert len(API_DESIGN_TASKS) == 5
    ids = [t.task_id for t in API_DESIGN_TASKS]
    assert len(set(ids)) == 5


def test_every_codegen_task_has_nonempty_test_code():
    for task in CODEGEN_TASKS:
        assert "def test_" in task.test_code


def test_every_api_design_task_has_rubric():
    for task in API_DESIGN_TASKS:
        assert len(task.rubric.strip()) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd eval-harness && pytest tests/test_configs_and_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'configs'`

- [ ] **Step 3: Implement configs.py and the task suite**

Create `eval-harness/configs.py`:

```python
from dataclasses import dataclass


@dataclass
class ModelConfig:
    label: str
    model: str
    temperature: float
    prompt_variant: str
    judge_only: bool = False


MODEL_CONFIGS = [
    ModelConfig(label="opus-judge", model="claude-opus-4-8", temperature=0.0,
                prompt_variant="default", judge_only=True),
    ModelConfig(label="sonnet-default", model="claude-sonnet-5", temperature=0.2,
                prompt_variant="default"),
    ModelConfig(label="sonnet-terse", model="claude-sonnet-5", temperature=0.2,
                prompt_variant="terse"),
    ModelConfig(label="sonnet-hot", model="claude-sonnet-5", temperature=0.8,
                prompt_variant="default"),
    ModelConfig(label="haiku-default", model="claude-haiku-4-5-20251001", temperature=0.2,
                prompt_variant="default"),
]

PROMPT_VARIANT_SUFFIXES = {
    "default": "",
    "terse": "\n\nBe as concise as possible in your response.",
}
```

Create `eval-harness/tasks/codegen_tasks.py`:

```python
from dataclasses import dataclass


@dataclass
class CodegenTask:
    task_id: str
    prompt: str
    test_code: str


CODEGEN_TASKS = [
    CodegenTask(
        task_id="codegen_01_reverse_string",
        prompt=(
            "Write a Python function `reverse_string(s: str) -> str` that returns "
            "the input string reversed. Respond with ONLY the function definition, "
            "no explanation, no markdown fences."
        ),
        test_code=(
            "from solution import reverse_string\n\n"
            "def test_basic():\n"
            "    assert reverse_string('hello') == 'olleh'\n\n"
            "def test_empty():\n"
            "    assert reverse_string('') == ''\n\n"
            "def test_single_char():\n"
            "    assert reverse_string('a') == 'a'\n"
        ),
    ),
    CodegenTask(
        task_id="codegen_02_is_palindrome",
        prompt=(
            "Write a Python function `is_palindrome(s: str) -> bool` that returns "
            "True if the input string reads the same forwards and backwards "
            "(case-sensitive, no whitespace stripping). Respond with ONLY the "
            "function definition, no explanation, no markdown fences."
        ),
        test_code=(
            "from solution import is_palindrome\n\n"
            "def test_palindrome_true():\n"
            "    assert is_palindrome('racecar') is True\n\n"
            "def test_palindrome_false():\n"
            "    assert is_palindrome('hello') is False\n\n"
            "def test_empty_string():\n"
            "    assert is_palindrome('') is True\n"
        ),
    ),
    CodegenTask(
        task_id="codegen_03_fizzbuzz",
        prompt=(
            "Write a Python function `fizzbuzz(n: int) -> list[str]` that returns "
            "a list of strings for numbers 1 to n inclusive: 'Fizz' for multiples "
            "of 3, 'Buzz' for multiples of 5, 'FizzBuzz' for multiples of both, "
            "otherwise the number as a string. Respond with ONLY the function "
            "definition, no explanation, no markdown fences."
        ),
        test_code=(
            "from solution import fizzbuzz\n\n"
            "def test_fizzbuzz_15():\n"
            "    result = fizzbuzz(15)\n"
            "    assert result[2] == 'Fizz'\n"
            "    assert result[4] == 'Buzz'\n"
            "    assert result[14] == 'FizzBuzz'\n"
            "    assert result[0] == '1'\n"
        ),
    ),
    CodegenTask(
        task_id="codegen_04_flatten_list",
        prompt=(
            "Write a Python function `flatten_list(nested: list) -> list` that "
            "flattens an arbitrarily nested list of integers into a single flat "
            "list, preserving order. Respond with ONLY the function definition, "
            "no explanation, no markdown fences."
        ),
        test_code=(
            "from solution import flatten_list\n\n"
            "def test_flat_already():\n"
            "    assert flatten_list([1, 2, 3]) == [1, 2, 3]\n\n"
            "def test_nested():\n"
            "    assert flatten_list([1, [2, 3], [4, [5, 6]]]) == [1, 2, 3, 4, 5, 6]\n\n"
            "def test_empty():\n"
            "    assert flatten_list([]) == []\n"
        ),
    ),
    CodegenTask(
        task_id="codegen_05_word_count",
        prompt=(
            "Write a Python function `word_count(text: str) -> dict` that returns "
            "a dictionary mapping each lowercase word to its number of occurrences "
            "in the input text. Split on whitespace and strip the punctuation "
            "characters '.', ',', '!', '?' from each word. Respond with ONLY the "
            "function definition, no explanation, no markdown fences."
        ),
        test_code=(
            "from solution import word_count\n\n"
            "def test_basic_count():\n"
            "    result = word_count('the cat sat on the mat')\n"
            "    assert result['the'] == 2\n"
            "    assert result['cat'] == 1\n\n"
            "def test_punctuation_stripped():\n"
            "    result = word_count('Hello, hello! world.')\n"
            "    assert result['hello'] == 2\n"
            "    assert result['world'] == 1\n"
        ),
    ),
]
```

Create `eval-harness/tasks/apidesign_tasks.py`:

```python
from dataclasses import dataclass


@dataclass
class ApiDesignTask:
    task_id: str
    prompt: str
    rubric: str


SHARED_RUBRIC = (
    "Score 0-10 total based on:\n"
    "- Resource naming follows REST conventions: plural nouns, no verbs in paths (0-2)\n"
    "- Correct HTTP verbs used for each operation: GET/POST/PUT/PATCH/DELETE (0-2)\n"
    "- Appropriate status codes specified for success and error cases (0-2)\n"
    "- Pagination or filtering addressed for list endpoints where relevant (0-2)\n"
    "- Response includes a consistent error format (0-2)\n"
)

API_DESIGN_TASKS = [
    ApiDesignTask(
        task_id="apidesign_01_todo",
        prompt=(
            "Design a REST API for a todo list app: users can create, list, "
            "update, complete, and delete tasks."
        ),
        rubric=SHARED_RUBRIC,
    ),
    ApiDesignTask(
        task_id="apidesign_02_url_shortener",
        prompt=(
            "Design a REST API for a URL shortener: users submit a long URL and "
            "get a short code; the short code redirects to the original URL; "
            "users can view click counts."
        ),
        rubric=SHARED_RUBRIC,
    ),
    ApiDesignTask(
        task_id="apidesign_03_blog",
        prompt=(
            "Design a REST API for a blog: supports posts and nested comments on "
            "posts, with listing, creation, editing, and deletion of both."
        ),
        rubric=SHARED_RUBRIC,
    ),
    ApiDesignTask(
        task_id="apidesign_04_product_catalog",
        prompt=(
            "Design a REST API for an e-commerce product catalog: products "
            "belong to categories, support search/filtering by category and "
            "price range."
        ),
        rubric=SHARED_RUBRIC,
    ),
    ApiDesignTask(
        task_id="apidesign_05_notifications",
        prompt=(
            "Design a REST API for a user notification system: users receive "
            "notifications, can mark them read/unread, and can list unread "
            "notifications."
        ),
        rubric=SHARED_RUBRIC,
    ),
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd eval-harness && pytest tests/test_configs_and_tasks.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add eval-harness/configs.py eval-harness/tasks/codegen_tasks.py eval-harness/tasks/apidesign_tasks.py eval-harness/tests/test_configs_and_tasks.py
git commit -m "feat(eval-harness): add model configs and 10-task evaluation suite"
```

---

### Task 6: Runner

**Files:**
- Create: `eval-harness/run_eval.py`
- Test: `eval-harness/tests/test_run_eval.py`

**Interfaces:**
- Consumes: `MODEL_CONFIGS` (Task 5), `CODEGEN_TASKS`/`API_DESIGN_TASKS` (Task 5), `LLMClient` (Task 2), `score_codegen` (Task 3), `score_api_design` (Task 4), `ResultsStore`/`ResultRow` (Task 1).
- Produces: `run(db_path: str) -> str` (returns the generated `run_id`). Module-level names `score_codegen` and `score_api_design` are imported directly into `run_eval`'s namespace (not accessed via `scoring.test_scorer.score_codegen`) specifically so tests can monkeypatch `run_eval.score_codegen` / `run_eval.score_api_design`.

- [ ] **Step 1: Write the failing test**

Create `eval-harness/tests/test_run_eval.py`:

```python
import os
import tempfile
from unittest.mock import MagicMock

import run_eval
from configs import MODEL_CONFIGS
from tasks.codegen_tasks import CODEGEN_TASKS
from tasks.apidesign_tasks import API_DESIGN_TASKS
from storage import ResultsStore


def test_run_writes_expected_number_of_rows(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)

    fake_response = MagicMock(text="fake code", cost_usd=0.001, latency_ms=100.0)
    monkeypatch.setattr(run_eval.LLMClient, "call", lambda self, **kwargs: fake_response)

    fake_codegen_result = MagicMock(score=1.0, pass_fail="pass", error=None)
    fake_judge_result = MagicMock(score=7.0, pass_fail=None, error=None)
    monkeypatch.setattr(run_eval, "score_codegen", lambda code, test_code: fake_codegen_result)
    monkeypatch.setattr(run_eval, "score_api_design", lambda client, prompt, rubric, text: fake_judge_result)

    try:
        run_id = run_eval.run(db_path)
        store = ResultsStore(db_path)
        results = store.all_results()

        subject_configs = [c for c in MODEL_CONFIGS if not c.judge_only]
        expected_rows = len(subject_configs) * (len(CODEGEN_TASKS) + len(API_DESIGN_TASKS))
        assert len(results) == expected_rows
        assert all(r.run_id == run_id for r in results)
        assert {r.task_type for r in results} == {"codegen", "api_design"}
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_run_records_error_row_on_api_failure(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)

    def raise_error(self, **kwargs):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(run_eval.LLMClient, "call", raise_error)

    try:
        run_eval.run(db_path)
        store = ResultsStore(db_path)
        results = store.all_results()
        assert len(results) > 0
        assert all(r.error == "rate limited" for r in results)
        assert all(r.score is None for r in results)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd eval-harness && pytest tests/test_run_eval.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'run_eval'`

- [ ] **Step 3: Implement run_eval.py**

Create `eval-harness/run_eval.py`:

```python
import uuid
from datetime import datetime, timezone

from configs import MODEL_CONFIGS
from llm_client import LLMClient
from storage import ResultsStore, ResultRow
from scoring.test_scorer import score_codegen
from scoring.judge_scorer import score_api_design
from tasks.codegen_tasks import CODEGEN_TASKS
from tasks.apidesign_tasks import API_DESIGN_TASKS

DB_PATH = "eval_results.db"


def run(db_path: str = DB_PATH) -> str:
    run_id = str(uuid.uuid4())[:8]
    store = ResultsStore(db_path)
    client = LLMClient()
    subject_configs = [c for c in MODEL_CONFIGS if not c.judge_only]

    for config in subject_configs:
        for task in CODEGEN_TASKS:
            _run_codegen(client, store, run_id, config, task)
        for task in API_DESIGN_TASKS:
            _run_api_design(client, store, run_id, config, task)

    return run_id


def _run_codegen(client, store, run_id, config, task):
    print(f"[{config.label}] {task.task_id} ... ", end="", flush=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        response = client.call(model=config.model, prompt=task.prompt, temperature=config.temperature)
    except Exception as exc:
        store.write_result(ResultRow(
            run_id=run_id, model=config.model, temperature=config.temperature,
            prompt_variant=config.prompt_variant, task_id=task.task_id, task_type="codegen",
            score=None, pass_fail=None, cost_usd=None, latency_ms=None,
            timestamp=timestamp, raw_response=None, error=str(exc),
        ))
        print(f"ERROR ({exc})")
        return

    result = score_codegen(response.text, task.test_code)
    store.write_result(ResultRow(
        run_id=run_id, model=config.model, temperature=config.temperature,
        prompt_variant=config.prompt_variant, task_id=task.task_id, task_type="codegen",
        score=result.score, pass_fail=result.pass_fail, cost_usd=response.cost_usd,
        latency_ms=response.latency_ms, timestamp=timestamp,
        raw_response=response.text, error=result.error,
    ))
    status = result.pass_fail.upper() if result.pass_fail else "ERROR"
    print(f"{status} ({response.latency_ms:.0f}ms, ${response.cost_usd:.4f})")


def _run_api_design(client, store, run_id, config, task):
    print(f"[{config.label}] {task.task_id} ... ", end="", flush=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        response = client.call(model=config.model, prompt=task.prompt, temperature=config.temperature)
    except Exception as exc:
        store.write_result(ResultRow(
            run_id=run_id, model=config.model, temperature=config.temperature,
            prompt_variant=config.prompt_variant, task_id=task.task_id, task_type="api_design",
            score=None, pass_fail=None, cost_usd=None, latency_ms=None,
            timestamp=timestamp, raw_response=None, error=str(exc),
        ))
        print(f"ERROR ({exc})")
        return

    result = score_api_design(client, task.prompt, task.rubric, response.text)
    store.write_result(ResultRow(
        run_id=run_id, model=config.model, temperature=config.temperature,
        prompt_variant=config.prompt_variant, task_id=task.task_id, task_type="api_design",
        score=result.score, pass_fail=result.pass_fail, cost_usd=response.cost_usd,
        latency_ms=response.latency_ms, timestamp=timestamp,
        raw_response=response.text, error=result.error,
    ))
    print(f"score={result.score} ({response.latency_ms:.0f}ms, ${response.cost_usd:.4f})")


if __name__ == "__main__":
    completed_run_id = run(DB_PATH)
    print(f"\nRun {completed_run_id} complete. Generating report...")
    from report import generate_report
    generate_report(DB_PATH, "report.html", "report.csv")
    print("Report written to report.html and report.csv")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd eval-harness && pytest tests/test_run_eval.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add eval-harness/run_eval.py eval-harness/tests/test_run_eval.py
git commit -m "feat(eval-harness): add sequential runner tying client, scorers, and storage together"
```

---

### Task 7: Report Generator

**Files:**
- Create: `eval-harness/report.py`
- Test: `eval-harness/tests/test_report.py`

**Interfaces:**
- Consumes: `ResultsStore`/`ResultRow` (Task 1).
- Produces: `generate_report(db_path: str, html_path: str, csv_path: str) -> None`.

- [ ] **Step 1: Write the failing test**

Create `eval-harness/tests/test_report.py`:

```python
import os
import tempfile

from storage import ResultsStore, ResultRow
from report import generate_report


def test_generate_report_creates_html_and_csv():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)
    html_path = db_path + ".html"
    csv_path = db_path + ".csv"

    try:
        store = ResultsStore(db_path)
        store.write_result(ResultRow(
            run_id="run1", model="claude-sonnet-5", temperature=0.2, prompt_variant="default",
            task_id="codegen_01", task_type="codegen", score=1.0, pass_fail="pass",
            cost_usd=0.002, latency_ms=300.0, timestamp="2026-07-06T00:00:00",
            raw_response="code", error=None,
        ))
        store.write_result(ResultRow(
            run_id="run1", model="claude-sonnet-5", temperature=0.2, prompt_variant="default",
            task_id="apidesign_01", task_type="api_design", score=8.0, pass_fail=None,
            cost_usd=0.003, latency_ms=500.0, timestamp="2026-07-06T00:00:01",
            raw_response="design", error=None,
        ))

        generate_report(db_path, html_path, csv_path)

        assert os.path.exists(html_path)
        assert os.path.exists(csv_path)
        with open(html_path) as f:
            content = f.read()
        assert "claude-sonnet-5" in content
        assert "<canvas" in content

        with open(csv_path) as f:
            csv_content = f.read()
        assert "codegen_01" in csv_content
        assert "apidesign_01" in csv_content
    finally:
        for p in (db_path, html_path, csv_path):
            if os.path.exists(p):
                os.remove(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd eval-harness && pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'report'`

- [ ] **Step 3: Implement report.py**

Create `eval-harness/report.py`:

```python
import csv
import html
from collections import defaultdict

from storage import ResultsStore


def generate_report(db_path: str, html_path: str, csv_path: str) -> None:
    store = ResultsStore(db_path)
    results = store.all_results()

    _write_csv(results, csv_path)
    _write_html(results, html_path)


def _write_csv(results, csv_path: str) -> None:
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["run_id", "model", "temperature", "prompt_variant", "task_id",
                          "task_type", "score", "pass_fail", "cost_usd", "latency_ms", "timestamp"])
        for r in results:
            writer.writerow([r.run_id, r.model, r.temperature, r.prompt_variant, r.task_id,
                              r.task_type, r.score, r.pass_fail, r.cost_usd, r.latency_ms, r.timestamp])


def _aggregate_by_config(results):
    groups = defaultdict(list)
    for r in results:
        groups[(r.model, r.temperature, r.prompt_variant)].append(r)

    summary = []
    for (model, temperature, variant), rows in groups.items():
        codegen_rows = [r for r in rows if r.task_type == "codegen"]
        judged_rows = [r for r in rows if r.task_type == "api_design" and r.score is not None]
        pass_count = sum(1 for r in codegen_rows if r.pass_fail == "pass")
        avg_judge_score = (sum(r.score for r in judged_rows) / len(judged_rows)) if judged_rows else None
        total_cost = sum(r.cost_usd for r in rows if r.cost_usd is not None)
        latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
        avg_latency = (sum(latencies) / len(latencies)) if latencies else None
        summary.append({
            "model": model, "temperature": temperature, "prompt_variant": variant,
            "codegen_pass_rate": (pass_count / len(codegen_rows)) if codegen_rows else None,
            "avg_judge_score": avg_judge_score,
            "total_cost_usd": total_cost,
            "avg_latency_ms": avg_latency,
        })
    return summary


def _write_html(results, html_path: str) -> None:
    summary = _aggregate_by_config(results)

    rows_html = ""
    for s in summary:
        pass_rate = f"{s['codegen_pass_rate']*100:.0f}%" if s["codegen_pass_rate"] is not None else "-"
        judge_score = f"{s['avg_judge_score']:.1f}/10" if s["avg_judge_score"] is not None else "-"
        avg_latency = f"{s['avg_latency_ms']:.0f}ms" if s["avg_latency_ms"] is not None else "-"
        rows_html += (
            "<tr>"
            f"<td>{html.escape(s['model'])}</td>"
            f"<td>{s['temperature']}</td>"
            f"<td>{html.escape(s['prompt_variant'])}</td>"
            f"<td>{pass_rate}</td>"
            f"<td>{judge_score}</td>"
            f"<td>${s['total_cost_usd']:.4f}</td>"
            f"<td>{avg_latency}</td>"
            "</tr>"
        )

    points_js = ",".join(
        f"{{x: {s['total_cost_usd']:.6f}, y: {(s['codegen_pass_rate'] or 0) * 100:.2f}, "
        f"label: {(s['model'] + ' ' + s['prompt_variant'])!r}}}"
        for s in summary
    )

    doc = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>LLM Eval Harness Report</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
  th, td {{ border: 1px solid #ccc; padding: 0.5rem 0.75rem; text-align: left; }}
  th {{ background: #f2f2f2; }}
  canvas {{ border: 1px solid #ccc; }}
</style>
</head>
<body>
<h1>LLM Eval Harness Report</h1>
<table>
<thead>
<tr><th>Model</th><th>Temp</th><th>Prompt Variant</th><th>Codegen Pass Rate</th>
<th>Avg Judge Score</th><th>Total Cost</th><th>Avg Latency</th></tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
<h2>Cost vs. Codegen Pass Rate</h2>
<canvas id="chart" width="600" height="400"></canvas>
<script>
const points = [{points_js}];
const canvas = document.getElementById('chart');
const ctx = canvas.getContext('2d');
const padding = 50;
const maxX = Math.max(...points.map(p => p.x), 0.001) * 1.2;
const maxY = 100;

ctx.strokeStyle = '#333';
ctx.beginPath();
ctx.moveTo(padding, 10);
ctx.lineTo(padding, canvas.height - padding);
ctx.lineTo(canvas.width - 10, canvas.height - padding);
ctx.stroke();

points.forEach(p => {{
  const px = padding + (p.x / maxX) * (canvas.width - padding - 10);
  const py = (canvas.height - padding) - (p.y / maxY) * (canvas.height - padding - 10);
  ctx.beginPath();
  ctx.arc(px, py, 5, 0, Math.PI * 2);
  ctx.fillStyle = '#2563eb';
  ctx.fill();
  ctx.fillStyle = '#000';
  ctx.font = '11px sans-serif';
  ctx.fillText(p.label, px + 8, py - 8);
}});

ctx.fillStyle = '#000';
ctx.fillText('Cost (USD) ->', canvas.width / 2, canvas.height - 15);
ctx.save();
ctx.translate(15, canvas.height / 2);
ctx.rotate(-Math.PI / 2);
ctx.fillText('Codegen Pass Rate (%) ->', 0, 0);
ctx.restore();
</script>
</body>
</html>"""

    with open(html_path, "w") as f:
        f.write(doc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd eval-harness && pytest tests/test_report.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add eval-harness/report.py eval-harness/tests/test_report.py
git commit -m "feat(eval-harness): add static HTML report and CSV export generator"
```

---

### Task 8: Repo Integration, README, and End-to-End Manual Verification

**Files:**
- Create: `eval-harness/README.md`
- Modify: `agent-capstone/README.md` (full rewrite)
- Modify: `GOALS.md:33-41` (mini-project table)

**Interfaces:** none (documentation + manual verification only).

- [ ] **Step 1: Run the full automated test suite**

Run: `cd eval-harness && pytest -v`
Expected: all tests from Tasks 1-7 pass (18 tests total: 3 storage + 3 llm_client + 3 test_scorer + 3 judge_scorer + 6 configs_and_tasks + 2 run_eval + 1 report... adjust if counts drift, but nothing should fail)

- [ ] **Step 2: Write eval-harness/README.md**

Create `eval-harness/README.md`:

```markdown
# eval-harness

**Maps to:** Itinerary Days 4-5 (agent-capstone slot) — see `../GOALS.md`.

## What this is

An LLM evaluation harness that compares Claude Opus/Sonnet/Haiku (plus prompt and
temperature variants) on two task types:

- **Code generation** (5 tasks) — scored by running real pytest unit tests inside a
  sandboxed, network-disabled Docker container.
- **API design** (5 tasks) — scored by Claude Opus acting as an LLM judge against a
  hand-written rubric. Opus is excluded from being scored as a subject, to avoid
  self-evaluation bias.

Results are stored in SQLite (`eval_results.db`) and rendered into a static,
self-contained HTML report (`report.html`) plus a CSV export (`report.csv`).

## Setup

```bash
cd eval-harness
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

Docker Desktop must be running (code-gen tasks execute inside containers).

## Running

```bash
python run_eval.py
```

This runs every subject model config against every task, prints progress as it goes,
writes results to `eval_results.db`, and regenerates `report.html` / `report.csv` at
the end. Re-running appends a new run rather than overwriting — all runs stay in the
same database, tagged by `run_id`.

## Running the harness's own tests

```bash
pytest -v
```

No API key needed for most tests (LLM calls are mocked). `tests/test_test_scorer.py`
requires Docker Desktop running (it exercises real container execution against golden
good/bad solutions).

## Architecture

See `../docs/superpowers/specs/2026-07-06-eval-harness-design.md` for the full design
rationale, and `../docs/superpowers/plans/2026-07-06-eval-harness.md` for the
implementation plan.

## Status

(Update as you go: what ran, what you found, what's fragile.)

## Findings

(Fill in after the first full run — e.g. which model won on cost/quality, any
surprising failures.)
```

- [ ] **Step 3: Rewrite agent-capstone/README.md**

Replace the full contents of `agent-capstone/README.md` with:

```markdown
# agent-capstone

**Maps to:** Itinerary Days 4-5 — see `../GOALS.md` for full context.

## Status: superseded by eval-harness/

This slot's chosen project is the **LLM Evaluation Harness** — see `../eval-harness/`
for the actual implementation, `../docs/superpowers/specs/2026-07-06-eval-harness-design.md`
for the design, and `../docs/superpowers/plans/2026-07-06-eval-harness.md` for the plan.

## Parked idea: AI Coding Agent for Non-Coders

An earlier brainstorm scoped a second project — an agent that turns natural-language
app descriptions into working FastAPI+React apps (template skeleton + free-form
business logic + one deterministic build-error retry). This was parked as a
stretch/afterward item, not required for this capstone. If picked back up later, it
still needs its own design spec written before implementation (the architecture was
discussed but never formally written down).

## Original idea list (for history)

- [x] LLM Evaluation Harness — chosen, see `../eval-harness/`
- [ ] AI Coding Agent for Non-Coders — parked, see note above
- [ ] Portfolio-company digest agent — not pursued
- [ ] Deal-memo drafting assistant — not pursued
- [ ] Meeting-notes to CRM sync tool — not pursued
```

- [ ] **Step 4: Update GOALS.md's mini-project table**

In `GOALS.md`, find the table row:

```
| `agent-capstone/` | Track 1, Days 4–5 | Small end-to-end agent: loop + sandboxed tool execution, containerized, deployed |
```

Replace it with two rows:

```
| `agent-capstone/` | Track 1, Days 4–5 | Superseded by `eval-harness/` — see its README |
| `eval-harness/` | Track 1, Days 4–5 | LLM eval harness: compare Claude models on code-gen + API-design tasks, Docker-sandboxed scoring, cost/quality tradeoffs |
```

- [ ] **Step 5: Commit the documentation changes**

```bash
git add eval-harness/README.md agent-capstone/README.md GOALS.md
git commit -m "docs(eval-harness): wire up README and GOALS.md for the new capstone project"
```

- [ ] **Step 6: Manual end-to-end verification (spends real API credits, requires Docker running)**

This step is not an automated test — it is the actual capstone deliverable running for
real. Requires `ANTHROPIC_API_KEY` set and Docker Desktop running.

```bash
cd eval-harness
python run_eval.py
```

Expected: progress lines for every (config, task) pair, ending with
`Report written to report.html and report.csv`. Open `report.html` in a browser and
confirm the comparison table and scatter chart render with real data, then update the
"Findings" section of `eval-harness/README.md` with the actual result (e.g. which
model won on cost vs. quality) and commit that update separately.
```

---

## Plan Self-Review Notes

- **Spec coverage:** every "Explicit scope decision" and architecture component in the
  design spec maps to a task above (models/judge exclusion → Task 5; code-gen/Docker
  scoring → Task 3; API-design/judge scoring → Task 4; sequential runner → Task 6;
  static HTML+CSV reporting → Task 7; testing plan's golden-task requirement → Task 3;
  repo integration → Task 8).
- **Resolved ambiguity:** the design spec's component list said Opus is "excluded from
  being scored as a subject" (unqualified), while its "Judge" bullet said Opus "can
  still be a subject on code-gen tasks" — these contradict. This plan resolves it as
  the simpler, unqualified reading: Opus is judge-only and never a scored subject on
  either task type (Task 5's `MODEL_CONFIGS` has no non-judge Opus entry). Flagged to
  the user in the plan handoff so they can override if they intended the narrower
  exclusion.
- **Type consistency checked:** `ScoreResult` (Task 3) is used identically in Task 4;
  `LLMResponse`/`LLMClient.call` (Task 2) signature matches every call site in Task 6;
  `ResultRow`/`ResultsStore` (Task 1) fields match every write in Task 6 and every read
  in Task 7.
