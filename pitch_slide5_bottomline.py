"""Shark Tank pitch — Slide 5: The Bottom Line (Time / Quality / Coverage).

Three big-number hero cards. The "shark bait" slide — everything here is
memorable at a glance. Framed as CARE QUALITY, not cost savings.

Output: pitch_slide5_bottomline.png (1920x1080)
"""
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).parent

fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
fig.patch.set_facecolor("white")
ax.set_xlim(0, 100); ax.set_ylim(0, 60)
ax.axis("off")

fig.suptitle("The Bottom Line — For the Patient",
             fontsize=32, fontweight="bold", color="#111", y=0.95)
fig.text(0.5, 0.885,
         "In the language that matters to a 911 caller",
         fontsize=15, color="#555", ha="center", style="italic")

cards = [
    {
        "headline": "−5.8 MIN",
        "label": "TIME",
        "sub": "Faster response\nduring concurrent calls",
        "detail": "16.6 min → 10.8 min\nIn cardiac arrest, this is\nthe difference that matters.",
        "color": "#B22222",
        "bg": "#FFF5F5",
    },
    {
        "headline": "1",
        "label": "QUALITY",
        "sub": "Unified medical\nprotocol, county-wide",
        "detail": "Today: 12 separate protocols.\nTomorrow: every patient gets\nthe same standard of care.",
        "color": "#2C7FB8",
        "bg": "#F0F8FF",
    },
    {
        "headline": "41 → ~5",
        "label": "COVERAGE",
        "sub": "All-busy events\nclosed per year",
        "detail": "No Jefferson County resident\nwaits for mutual aid from\nanother county.",
        "color": "#228B22",
        "bg": "#F5FFF5",
    },
]

# 3 equal cards with gaps
card_w = 29
card_h = 44
gap = 2.5
total_w = 3 * card_w + 2 * gap
start_x = (100 - total_w) / 2
y0 = 5

for i, c in enumerate(cards):
    x = start_x + i * (card_w + gap)
    box = FancyBboxPatch((x, y0), card_w, card_h,
                         boxstyle="round,pad=0.02,rounding_size=0.8",
                         facecolor=c["bg"], edgecolor=c["color"],
                         linewidth=3)
    ax.add_patch(box)

    # Label (TIME / QUALITY / COVERAGE) — small, top
    ax.text(x + card_w / 2, y0 + card_h - 4, c["label"],
            fontsize=18, fontweight="bold", color=c["color"],
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=c["color"],
                      edgecolor="none", alpha=0.15))

    # Headline number — huge
    ax.text(x + card_w / 2, y0 + card_h - 14, c["headline"],
            fontsize=60, fontweight="bold", color=c["color"],
            ha="center", va="center")

    # Subtitle
    ax.text(x + card_w / 2, y0 + card_h - 24, c["sub"],
            fontsize=15, fontweight="bold", color="#333",
            ha="center", va="center")

    # Detail
    ax.text(x + card_w / 2, y0 + 10, c["detail"],
            fontsize=12, color="#555",
            ha="center", va="center", style="italic")

fig.text(0.5, 0.03,
         "We're not asking for funding. We're asking for partnership as the "
         "Jefferson County EMS Working Group moves into implementation.",
         fontsize=13, color="#444", ha="center",
         fontweight="bold", style="italic")

out = ROOT / "pitch_slide5_bottomline.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Saved: {out}")
