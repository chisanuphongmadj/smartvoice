"""Generate ER Diagram PNG for SmartVoice database design report."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import os

os.makedirs(os.path.dirname(__file__) or ".", exist_ok=True)

TABLES = {
    "calls": {
        "color": "#1e3a5f",
        "header_color": "#2563eb",
        "pos": (0.01, 0.04),
        "width": 0.23,
        "fields": [
            ("PK", "id", "INTEGER"),
            ("",   "filename", "TEXT"),
            ("UK", "file_hash", "TEXT"),
            ("",   "file_path", "TEXT"),
            ("",   "transcript", "TEXT"),
            ("",   "summary", "TEXT"),
            ("",   "sentiment", "TEXT"),
            ("",   "topic", "TEXT"),
            ("",   "speaker_mapping", "TEXT(JSON)"),
            ("",   "agent_performance", "TEXT(JSON)"),
            ("",   "keywords", "TEXT(JSON)"),
            ("",   "brand_mentions", "TEXT(JSON)"),
            ("",   "platform_mentions", "TEXT(JSON)"),
            ("",   "anomaly_detected", "INTEGER"),
            ("",   "anomaly_reason", "TEXT"),
            ("",   "sentiment_reason", "TEXT"),
            ("",   "anomaly_severity", "TEXT"),
            ("",   "customer_phone", "TEXT"),
            ("FK", "case_id", "INTEGER"),
            ("",   "processing_step", "TEXT"),
            ("",   "status", "TEXT"),
            ("",   "created_at", "TEXT"),
            ("",   "updated_at", "TEXT"),
        ],
    },
    "customers": {
        "color": "#1a3a2a",
        "header_color": "#16a34a",
        "pos": (0.35, 0.46),
        "width": 0.24,
        "fields": [
            ("PK", "id", "INTEGER"),
            ("",   "first_name", "TEXT"),
            ("",   "last_name", "TEXT"),
            ("UK", "phone", "TEXT"),
            ("",   "email", "TEXT"),
            ("",   "gender", "TEXT"),
            ("",   "date_of_birth", "TEXT"),
            ("",   "address", "TEXT"),
            ("",   "subdistrict", "TEXT"),
            ("",   "district", "TEXT"),
            ("",   "city_province", "TEXT"),
            ("",   "postcode", "TEXT"),
            ("",   "created_at", "TEXT"),
        ],
    },
    "warranty_registrations": {
        "color": "#3a1a2a",
        "header_color": "#9333ea",
        "pos": (0.34, 0.02),
        "width": 0.26,
        "fields": [
            ("PK", "id", "INTEGER"),
            ("UK", "registration_no", "TEXT"),
            ("FK", "customer_id", "INTEGER"),
            ("",   "channel", "TEXT"),
            ("",   "brand", "TEXT"),
            ("",   "model", "TEXT"),
            ("",   "size", "TEXT"),
            ("",   "category", "TEXT"),
            ("",   "purchase_channel", "TEXT"),
            ("",   "date_of_purchase", "TEXT"),
            ("",   "warranty_period_months", "INTEGER"),
            ("",   "expiry_date", "TEXT"),
            ("",   "created_at", "TEXT"),
        ],
    },
    "call_customer_links": {
        "color": "#3a2a0a",
        "header_color": "#d97706",
        "pos": (0.74, 0.30),
        "width": 0.25,
        "fields": [
            ("PK", "id", "INTEGER"),
            ("FK", "call_id", "INTEGER"),
            ("FK", "customer_id", "INTEGER"),
            ("FK", "warranty_id", "INTEGER"),
            ("",   "matched_by", "TEXT"),
            ("",   "created_at", "TEXT"),
        ],
    },
    "cases": {
        "color": "#2a1a3a",
        "header_color": "#a855f7",
        "pos": (0.74, 0.68),
        "width": 0.25,
        "fields": [
            ("PK", "id", "INTEGER"),
            ("FK", "customer_id", "INTEGER"),
            ("",   "subject", "TEXT"),
            ("",   "status", "TEXT"),
            ("",   "created_at", "TEXT"),
            ("",   "updated_at", "TEXT"),
        ],
    },
}

ROW_H = 0.028
HEADER_H = 0.042
PAD = 0.006

fig, ax = plt.subplots(figsize=(24, 14))
fig.patch.set_facecolor("#0f1117")
ax.set_facecolor("#0f1117")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

ax.text(0.5, 0.985, "SmartVoice — ER Diagram", ha="center", va="top",
        fontsize=20, fontweight="bold", color="white", fontfamily="DejaVu Sans")
ax.text(0.5, 0.963, "AI-Powered Call Center Analytics | SQLite 3 (Cloud-ready: PostgreSQL)",
        ha="center", va="top", fontsize=10, color="#9ca3af", fontfamily="DejaVu Sans")

table_centers = {}

for tname, tdata in TABLES.items():
    n_rows = len(tdata["fields"])
    total_h = HEADER_H + n_rows * ROW_H + PAD * 2
    x, y = tdata["pos"]
    w = tdata["width"]

    # Table box
    box = FancyBboxPatch((x, y), w, total_h,
                         boxstyle="round,pad=0.005",
                         facecolor=tdata["color"], edgecolor=tdata["header_color"],
                         linewidth=1.5, transform=ax.transAxes, zorder=2)
    ax.add_patch(box)

    # Header
    header = FancyBboxPatch((x, y + total_h - HEADER_H), w, HEADER_H,
                            boxstyle="round,pad=0.003",
                            facecolor=tdata["header_color"], edgecolor=tdata["header_color"],
                            linewidth=0, transform=ax.transAxes, zorder=3)
    ax.add_patch(header)
    ax.text(x + w / 2, y + total_h - HEADER_H / 2, tname,
            ha="center", va="center", fontsize=10, fontweight="bold",
            color="white", transform=ax.transAxes, zorder=4)

    # Fields
    for i, (constraint, fname, ftype) in enumerate(tdata["fields"]):
        row_y = y + total_h - HEADER_H - (i + 1) * ROW_H
        # Alternating row bg
        if i % 2 == 0:
            row_bg = FancyBboxPatch((x + 0.002, row_y + 0.002), w - 0.004, ROW_H - 0.004,
                                    boxstyle="round,pad=0.001",
                                    facecolor="#ffffff08", edgecolor="none",
                                    transform=ax.transAxes, zorder=3)
            ax.add_patch(row_bg)

        # Constraint badge color
        badge_colors = {"PK": "#f59e0b", "FK": "#60a5fa", "UK": "#34d399", "": "none"}
        bc = badge_colors.get(constraint, "none")
        if constraint:
            ax.text(x + 0.012, row_y + ROW_H / 2, constraint,
                    ha="center", va="center", fontsize=6.5, fontweight="bold",
                    color=bc, transform=ax.transAxes, zorder=4)

        ax.text(x + 0.030, row_y + ROW_H / 2, fname,
                ha="left", va="center", fontsize=8,
                color="white" if constraint in ("PK", "UK") else "#e2e8f0",
                fontweight="bold" if constraint == "PK" else "normal",
                transform=ax.transAxes, zorder=4)

        ax.text(x + w - 0.008, row_y + ROW_H / 2, ftype,
                ha="right", va="center", fontsize=7, color="#94a3b8",
                transform=ax.transAxes, zorder=4)

    # Store center for relationship arrows
    table_centers[tname] = (x + w / 2, y + total_h / 2)

# Relationship arrows
RELS = [
    ("customers", "warranty_registrations", "1 : N\nhas warranty"),
    ("customers", "call_customer_links", "1 : N\nlinked to"),
    ("calls", "call_customer_links", "1 : N\nlinked to"),
    ("warranty_registrations", "call_customer_links", "1 : N\nreferenced by"),
    ("customers", "cases", "1 : N\nhas case"),
    ("cases", "calls", "1 : N\ngroups calls"),
]

arrow_props = dict(arrowstyle="-|>", color="#64748b", lw=1.5,
                   mutation_scale=12, connectionstyle="arc3,rad=0.08")

for src, dst, label in RELS:
    sx, sy = table_centers[src]
    dx, dy = table_centers[dst]
    ax.annotate("", xy=(dx, dy), xytext=(sx, sy),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=arrow_props, zorder=1)
    mx, my = (sx + dx) / 2, (sy + dy) / 2
    ax.text(mx, my, label, ha="center", va="center", fontsize=7,
            color="#94a3b8", transform=ax.transAxes, zorder=5,
            bbox=dict(facecolor="#1e2130", edgecolor="#334155", boxstyle="round,pad=0.2", linewidth=0.8))

# Legend
legend_items = [
    mpatches.Patch(color="#f59e0b", label="PK = Primary Key"),
    mpatches.Patch(color="#60a5fa", label="FK = Foreign Key (References)"),
    mpatches.Patch(color="#34d399", label="UK = Unique Constraint"),
]
ax.legend(handles=legend_items, loc="lower right", fontsize=8,
          facecolor="#1e2130", edgecolor="#334155", labelcolor="white",
          framealpha=0.9)

out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "er_diagram.png")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
plt.tight_layout()
plt.savefig(out_path, dpi=150, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"Saved: {out_path}")
