"""Common styles, colors, font setup, and utility functions for all visualizations."""

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os

# ── font setup (Chinese support on macOS) ──────────────────────────
def _find_chinese_font():
    """Return a font name that supports Chinese glyphs on macOS."""
    candidates = [
        "PingFang SC",
        "Heiti SC",
        "STHeiti",
        "Arial Unicode MS",
        "Hiragino Sans GB",
        "Songti SC",
        "SimHei",
        "WenQuanYi Micro Hei",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    # fallback: use sans-serif and hope
    return "sans-serif"

FONT_FAMILY = _find_chinese_font()

def setup_mpl():
    """Configure matplotlib defaults for consistent styling."""
    # Ensure writable cache directory
    import tempfile
    if not os.environ.get("MPLCONFIGDIR"):
        os.environ["MPLCONFIGDIR"] = os.path.join(tempfile.gettempdir(), "matplotlib_cache")

    matplotlib.rcParams.update({
        "font.family":     "sans-serif",
        "font.sans-serif": [FONT_FAMILY, "DejaVu Sans", "Arial", "Helvetica"],
        "axes.unicode_minus": False,
        "figure.dpi":      150,
        "savefig.dpi":     150,
        "savefig.bbox":    "tight",
        "savefig.pad_inches": 0.1,
        "font.size":       10,
        "axes.titlesize":  12,
        "axes.labelsize":  11,
        "legend.fontsize": 9,
    })

# ── color palette ───────────────────────────────────────────────────
SCHEDULER_COLORS = {
    "random_same":      "#999999",  # grey baseline
    "random_intensity": "#4477AA",  # blue
    "crux_no_compress": "#EE7733",  # orange (primary comparison)
    "crux":             "#CC3311",  # red
}

SCHEDULER_ORDER = ["random_same", "random_intensity", "crux_no_compress", "crux"]

GAIN_COLOR  = "#228833"   # green for improvement
LOSS_COLOR  = "#EE6677"   # red for degradation

# ── model color map ─────────────────────────────────────────────────
MODEL_COLORS = {
    "GPT-large":       "#CC3311",
    "GPT":              "#EE7733",
    "unknown-large":    "#DDAA33",
    "unknown-mid":      "#44AA99",
    "unknown-8gpu":     "#4477AA",
    "unknown-small":    "#999999",
}

# ── output helpers ──────────────────────────────────────────────────
def save_fig(fig, out_dir, name, formats=("svg",)):
    """Save figure to out_dir/name.{fmt} for each fmt in formats."""
    os.makedirs(out_dir, exist_ok=True)
    for fmt in formats:
        path = os.path.join(out_dir, f"{name}.{fmt}")
        fig.savefig(path, format=fmt)
        print(f"  saved: {path}")
    return fig

# ── data helpers ────────────────────────────────────────────────────
def parse_placement(placement_str):
    """Parse placement string like 'host:gpu;host:gpu;...' into list of (host, gpu)."""
    pairs = []
    for token in placement_str.split(";"):
        token = token.strip()
        if not token:
            continue
        h, g = token.split(":")
        pairs.append((int(h), int(g)))
    return pairs

def compute_cross_host_flows(placement, ranks):
    """Compute set of cross-host (src_host, dst_host) pairs for Ring AllReduce.
    
    For a Ring AllReduce with N ranks, each rank communicates with
    its next neighbor (rank i → rank i+1 mod N). Returns the set
    of (src_host, dst_host) for cross-host pairs.
    """
    pairs = set()
    for i in range(ranks):
        src = placement[i]
        dst = placement[(i + 1) % ranks]
        if src[0] != dst[0]:
            pairs.add((src[0], dst[0]))
    return pairs

def compute_switch_path(hosts, switches_per_level):
    """Compute which switches a cross-host pair traverses using SimGrid's hash.
    
    Uses the same deterministic hash as collective_sim.cpp:
    sw[lvl][(h1*31 + h2*17 + lvl*7) % sw[lvl].count]
    
    Returns list of switch indices per level.
    """
    path = []
    for lvl, sw_count in enumerate(switches_per_level):
        idx = (hosts[0] * 31 + hosts[1] * 17 + lvl * 7) % sw_count
        path.append(idx)
    return path
