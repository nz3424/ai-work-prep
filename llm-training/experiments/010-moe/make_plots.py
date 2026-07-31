"""Regenerate the exp 010 results figures from training.log.

Two figures, matching results.md:
  fig1_loss_curves.png   — train vs val loss over steps, with the dense baseline
  fig2_ppl_compare.png   — 005-harness perplexity: dense vs MoE-best vs MoE-final

Run from the llm-training dir:  python3 experiments/010-moe/make_plots.py
Palette + mark rules follow the dataviz skill (validated categorical hues,
thin marks, legend for >=2 series, direct labels, recessive grid).
"""
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
LOG = HERE / "training.log"

# --- validated dataviz palette (light surface) ---
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e6e5e1"
BLUE = "#2a78d6"    # categorical 1 -> train
ORANGE = "#eb6834"  # categorical 2 -> val
GREEN = "#008300"   # status good    -> MoE beat baseline
RED = "#e34948"     # status critical -> MoE worse than baseline

# --- reference numbers (005 fixed-batch harness, 002 axis) ---
DENSE_PPL = 66.6
DENSE_VAL = 4.198
MOE_FINAL_PPL = 118.5
MOE_BEST_PPL = 43.4  # min val_loss checkpoint (step ~1200)

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "font.size": 11, "text.color": INK,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
})


def parse_log():
    steps_t, train, steps_v, val = [], [], [], []
    for line in LOG.read_text().splitlines():
        m = re.search(r"step (\d+) train_loss ([0-9.]+)", line)
        if not m:
            continue
        s, t = int(m.group(1)), float(m.group(2))
        steps_t.append(s); train.append(t)
        mv = re.search(r"val_loss ([0-9.]+)", line)
        if mv:
            steps_v.append(s); val.append(float(mv.group(1)))
    return steps_t, train, steps_v, val


def style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)


def fig_loss_curves(steps_t, train, steps_v, val):
    best_i = min(range(len(val)), key=lambda i: val[i])
    fig, ax = plt.subplots(figsize=(8.2, 4.6), dpi=150)
    style(ax)
    ax.plot(steps_t, train, color=BLUE, linewidth=1.6, label="train loss", zorder=3)
    ax.plot(steps_v, val, color=ORANGE, linewidth=2.0, label="val loss", zorder=4)
    ax.axhline(DENSE_VAL, color=MUTED, linestyle="--", linewidth=1.4, zorder=2)
    ax.text(steps_t[-1], DENSE_VAL + 0.06, "dense baseline (002-rope)  val 4.198 / ppl 66.6",
            ha="right", va="bottom", color=MUTED, fontsize=9.5)
    # mark the val trough (best checkpoint) and the shipped final checkpoint
    ax.scatter([steps_v[best_i]], [val[best_i]], s=42, color=GREEN, zorder=6)
    ax.annotate(f"best val {val[best_i]:.2f} / ppl {MOE_BEST_PPL:.0f}\n(step {steps_v[best_i]}) — beats dense",
                (steps_v[best_i], val[best_i]), xytext=(steps_v[best_i] + 250, val[best_i] - 0.75),
                color=GREEN, fontsize=9.5,
                arrowprops=dict(arrowstyle="->", color=GREEN, linewidth=1.2))
    ax.scatter([steps_v[-1]], [val[-1]], s=42, color=RED, zorder=6)
    ax.annotate(f"final {val[-1]:.2f} / ppl {MOE_FINAL_PPL:.0f}\n— overfit, shipped",
                (steps_v[-1], val[-1]), xytext=(steps_v[-1] - 1150, val[-1] + 0.15),
                color=RED, fontsize=9.5)
    ax.set_xlabel("training step")
    ax.set_ylabel("cross-entropy loss")
    ax.set_title("Exp 010 MoE — train keeps falling, val overfits past ~step 1200",
                 color=INK, fontsize=12.5, pad=10)
    ax.legend(frameon=False, loc="upper right")
    ax.set_ylim(1.5, 7.5)
    fig.tight_layout()
    fig.savefig(HERE / "fig1_loss_curves.png")
    print("wrote fig1_loss_curves.png  (best val at step", steps_v[best_i], ")")


def fig_ppl_compare():
    labels = ["dense 002-rope\n(harness)", "MoE best step 1200\n(in-loop val)", "MoE final step 3000\n(harness)"]
    vals = [DENSE_PPL, MOE_BEST_PPL, MOE_FINAL_PPL]
    colors = [BLUE, GREEN, RED]
    fig, ax = plt.subplots(figsize=(7.0, 4.7), dpi=150)
    style(ax)
    bars = ax.bar(labels, vals, color=colors, width=0.62, zorder=3)
    ax.axhline(DENSE_PPL, color=MUTED, linestyle="--", linewidth=1.2, zorder=2)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 2.5, f"{v:.1f}",
                ha="center", va="bottom", color=INK, fontsize=11, fontweight="bold")
    ax.set_ylabel("perplexity  (lower is better)")
    ax.set_title("MoE had the capacity to beat dense — the shipped checkpoint overfit",
                 color=INK, fontsize=11.5, pad=10)
    ax.set_ylim(0, 132)
    fig.tight_layout()
    fig.savefig(HERE / "fig2_ppl_compare.png")
    print("wrote fig2_ppl_compare.png")


if __name__ == "__main__":
    st, tr, sv, vl = parse_log()
    fig_loss_curves(st, tr, sv, vl)
    fig_ppl_compare()
