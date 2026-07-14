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
        # exclude rows that errored before scoring, matching the judge metric's policy
        codegen_rows = [r for r in rows if r.task_type == "codegen" and r.pass_fail is not None]
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
