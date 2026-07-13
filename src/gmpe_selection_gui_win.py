#!/usr/bin/env python3
"""
gmpe_selection_gui_win.py —  Windows‑compatible version.

Same as gmpe_selection_gui.py but adapted for Windows:
  • OQ Python path → Scripts/python.exe
  • Dark mode via Windows registry
  • Font → Segoe UI
  • Mouse wheel → Button-4/Button-5 fallback

Usage:
  python src\gmpe_selection_gui_win.py
  python src\gmpe_selection_gui_win.py --catalogue gmpe_catalogue.csv
"""

import platform as _pltfrm

import csv
import json
import os
import re
import sys
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, filedialog


# ── Constants ─────────────────────────────────────────────────
DEFAULT_CATALOGUE = "gmpe_catalogue.csv"
DEFAULT_SELECTION = "gmpe_selection.json"
EVENTS = ["HF_SMS", "LF_SMS"]

# All possible values (populated from catalogue on load)
ALL_REGIONS = set()
ALL_DISTANCES = set()
ALL_SITES = set()
ALL_RUPTURES = set()
ALL_IMTS = set()
ALL_STDS = set()


# ── Colour scheme (dark‑mode aware) ──────────────────────────
def _detect_dark_mode():
    """Return True if the OS is in dark‑appearance mode (cross‑platform)."""
    _sys_name = _pltfrm.system()
    try:
        if _sys_name == "Darwin":
            import subprocess
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                               capture_output=True, text=True, timeout=2)
            return r.stdout.strip().lower() == "dark"
        elif _sys_name == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
                val, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
                return val == 0
        elif _sys_name == "Linux":
            import subprocess
            r = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface",
                                "color-scheme"], capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                return "dark" in r.stdout.strip().lower()
            r = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface",
                                "gtk-theme"], capture_output=True, text=True, timeout=2)
            return "dark" in r.stdout.strip().lower() if r.returncode == 0 else False
    except Exception:
        pass
    return False


_IS_DARK = _detect_dark_mode()

if _IS_DARK:
    COLORS = {
        "bg":         "#1e1e1e",
        "fg":         "#cccccc",
        "input_bg":   "#2d2d2d",
        "input_fg":   "#e0e0e0",
        "select_bg":  "#094771",
        "accent":     "#4aa3df",
        "accent_dark":"#2b7fc1",
        "card_bg":    "#252526",
        "card_fg":    "#cccccc",
        "panel_bg":   "#1e1e1e",
        "border":     "#3c3c3c",
        "status_fg":  "#888888",
        "header_bg":  "#2c3e50",   # keep dark header as-is
        "header_fg":  "#ffffff",
        "white":      "#2d2d2d",   # replacement for hardcoded "white" backgrounds
        "err_fg":     "#f48771",
    }
else:
    COLORS = {
        "bg":         "#f5f6fa",
        "fg":         "#2c3e50",
        "input_bg":   "#ffffff",
        "input_fg":   "#2c3e50",
        "select_bg":  "#3498db",
        "accent":     "#3498db",
        "accent_dark":"#2980b9",
        "card_bg":    "#ffffff",
        "card_fg":    "#2c3e50",
        "panel_bg":   "#f5f6fa",
        "border":     "#dcdde1",
        "status_fg":  "#888888",
        "header_bg":  "#2c3e50",
        "header_fg":  "#ffffff",
        "white":      "#ffffff",
        "err_fg":     "#e74c3c",
    }


# ═══════════════════════════════════════════════════════════════
#  Data layer
# ═══════════════════════════════════════════════════════════════

def load_catalogue(path):
    """Load GMPE catalogue CSV → list of dicts with parsed sets."""
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["Year"] = int(row["Year"]) if row["Year"].isdigit() else 0
            row["RequiresDistances"] = set(row["RequiresDistances"].split())
            row["RequiresRupture"] = set(row["RequiresRupture"].split())
            row["RequiresSites"] = set(row["RequiresSites"].split())
            row["DefinedForIMTs"] = set(row.get("DefinedForIMTs", "").split())
            row["DefinedForStdDevs"] = set(row.get("DefinedForStdDevs", "").split())
            rows.append(row)
    return rows


def catalogue_to_display_rows(catalogue):
    """Convert catalogue rows to a list of display dicts."""
    rows = []
    for r in catalogue:
        rows.append({
            "code": r.get("Shortcut", r["Code"]),
            "name": r["GMPE"],
            "year": r["Year"],
            "region": r["TectonicRegion"],
            "distances": " ".join(sorted(r["RequiresDistances"])),
            "rupture": " ".join(sorted(r["RequiresRupture"])),
            "sites": " ".join(sorted(r["RequiresSites"])),
            "imts": " ".join(sorted(r["DefinedForIMTs"])),
            "stds": " ".join(sorted(r["DefinedForStdDevs"])),
            # Keep sets for filtering
            "_dist_set": r["RequiresDistances"],
            "_rupt_set": r["RequiresRupture"],
            "_site_set": r["RequiresSites"],
            "_imt_set": r["DefinedForIMTs"],
            "_std_set": r["DefinedForStdDevs"],
        })
    return rows


def collect_all_values(catalogue):
    """Collect all possible values for filter dropdowns."""
    global ALL_REGIONS, ALL_DISTANCES, ALL_SITES, ALL_RUPTURES, ALL_IMTS, ALL_STDS
    for r in catalogue:
        if r["TectonicRegion"] and r["TectonicRegion"] != "—":
            ALL_REGIONS.add(r["TectonicRegion"])
        ALL_DISTANCES.update(r["RequiresDistances"])
        ALL_SITES.update(r["RequiresSites"])
        ALL_RUPTURES.update(r["RequiresRupture"])
        ALL_IMTS.update(r["DefinedForIMTs"])
        ALL_STDS.update(r["DefinedForStdDevs"])


def load_selection(path):
    """Load a GMPE selection JSON → dict event → set of full names.

    Supports two formats:
      • Classic multi-event:  {HF_SMS: [...], LF_SMS: [...]}
      • Single-event:         {event_name: [...]}
    For single-event files the GMPEs are distributed to both HF_SMS and LF_SMS
    so the rest of the GUI works unchanged.
    """
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        raw = json.load(f)

    # Heuristic: if no top-level key matches a classic event name, treat the
    # whole file as a single-event selection → broadcast to all EVENTS.
    has_single_event = not bool(set(raw) & set(EVENTS))

    if has_single_event:
        # Single-event format – merge all GMPEs into every classic event slot
        all_names = set()
        for items in raw.values():
            for it in items:
                all_names.add(it if isinstance(it, str) else it[1])
        return {ev: set(all_names) for ev in EVENTS}
    else:
        # Classic multi-event format
        result = {}
        for ev, items in raw.items():
            names = set()
            for it in items:
                fullname = it if isinstance(it, str) else it[1]
                names.add(fullname)
            result[ev] = names
        return result


def _gmpe_names_for_filters(catalogue, display_rows, filters):
    """Apply filter criteria and return a list of matched GMPE full names."""
    matched = []
    for row in display_rows:
        ok = True
        name = row["name"]
        yr = next((r["Year"] for r in catalogue if r["GMPE"] == name), 0)

        if "year_min" in filters and yr < filters["year_min"]:
            ok = False
        if "year_max" in filters and yr > filters["year_max"]:
            ok = False

        if ok and "region" in filters:
            cat_row = next((r for r in catalogue if r["GMPE"] == name), None)
            if cat_row:
                region_text = cat_row["TectonicRegion"]
                ok = any(r.lower() in region_text.lower() for r in filters["region"])

        if ok and "dist_any" in filters:
            if not row["_dist_set"].intersection(filters["dist_any"]):
                ok = False

        if ok and "site_all" in filters:
            if not row["_site_set"].issuperset(filters["site_all"]):
                ok = False

        if ok and "rupt_all" in filters:
            if not row["_rupt_set"].issuperset(filters["rupt_all"]):
                ok = False

        if ok and "imt_all" in filters:
            if not row["_imt_set"].issuperset(filters["imt_all"]):
                ok = False

        if ok and "std_all" in filters:
            if not row["_std_set"].issuperset(filters["std_all"]):
                ok = False

        if ok:
            matched.append(name)
    return matched


_COUNTRY_KEYWORDS = [
    "Italy", "Japan", "JPN", "Armenia", "China", "CHN", "Taiwan", "TWN",
    "Turkey", "TUR", "Iran", "Switzerland", "SWISS", "Hawaii", "Alaska",
    "Cascadia", "NewZealand", "NZL", "Germany", "France", "Brazil",
    "UK", "Craton", "India", "Tibet", "Wenchuan", "Greece",
    "California", "Alps", "Foreland", "Vietnam", "Africa",
    "NGA",
]


def _flag_country_specific_gmpes(gmpe_names):
    """Check GMPE names against country keywords.

    Returns a dict: {keyword: [(code, fullname), ...], ...}
    """
    flagged = {}
    for name in gmpe_names:
        code = make_gmpe_code(name)
        for kw in _COUNTRY_KEYWORDS:
            if kw.lower() in name.lower():
                flagged.setdefault(kw, []).append((code, name))
                break
    return flagged


def _show_country_keyword_dialog(parent, catalogue, display_rows, filters):
    """Show a dialog asking which countries/regions the user is targeting.

    Returns the set of GMPE names to REMOVE (those flagged with countries
    the user is NOT targeting), or an empty set if no country check needed.
    """
    # First get the matched GMPE list from filters
    matched_names = _gmpe_names_for_filters(catalogue, display_rows, filters)
    flagged = _flag_country_specific_gmpes(matched_names)

    if not flagged:
        return set()  # no country-specific GMPEs found

    to_remove = set()

    dialog = tk.Toplevel(parent)
    dialog.title("Region-Specific GMPEs")
    dialog.geometry("600x580")
    dialog.minsize(480, 400)
    dialog.configure(bg=COLORS["bg"])
    dialog.transient(parent)
    dialog.grab_set()

    # ── Header ──
    header = tk.Frame(dialog, bg="#e67e22", padx=20, pady=14)
    header.pack(fill=tk.X)
    tk.Label(header, text="🌍  Region-Specific GMPEs Detected",
             font=("Helvetica", 15, "bold"), fg="white", bg="#e67e22").pack()
    tk.Label(header, text="Some GMPEs are specific to particular countries/regions.\n"
                          "Please indicate which ones are relevant to your project.",
             font=("Helvetica", 10), fg="#fdebd0", bg="#e67e22", justify=tk.CENTER).pack(pady=(4, 0))

    # ── Scrollable body ──
    canvas = tk.Canvas(dialog, bg=COLORS["bg"], highlightthickness=0)
    scrollbar = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=canvas.yview)
    scroll_frame = tk.Frame(canvas, bg=COLORS["bg"])

    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=480)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0), pady=12)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=12)

    # ── Mousewheel / trackpad scrolling ──
    def _on_mousewheel(event):
        if canvas.winfo_exists():
            # macOS: trackpad gives small delta, mouse wheel gives ±120
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")

    row_idx = [0]

    def _next_row():
        r = row_idx[0]
        row_idx[0] += 1
        return r

    keyword_vars = {}

    for kw in sorted(flagged.keys()):
        items = flagged[kw]
        # Section header
        r = _next_row()
        lbl = tk.Label(scroll_frame,
                       text=f"Keyword: \"{kw}\" — {len(items)} GMPE(s)",
                       font=("Helvetica", 11, "bold"), bg=COLORS["bg"], fg=COLORS["fg"],
                       anchor=tk.W)
        lbl.grid(row=r, column=0, sticky=tk.W, pady=(10, 2), padx=6)

        # Yes/No radio
        r = _next_row()
        radio_frame = tk.Frame(scroll_frame, bg=COLORS["card_bg"], padx=10, pady=6)
        radio_frame.grid(row=r, column=0, sticky="ew", padx=6)

        keep_var = tk.StringVar(value="no")  # default: no, remove them
        tk.Radiobutton(radio_frame, text=f"✓ Yes, targeting {kw} — keep these GMPEs",
                       variable=keep_var, value="yes",
                       font=("Helvetica", 10), bg=COLORS["card_bg"], fg="#27ae60",
                       activebackground=COLORS["card_bg"], selectcolor=COLORS["card_bg"]).pack(anchor=tk.W)
        tk.Radiobutton(radio_frame, text=f"✗ No, NOT targeting {kw} — remove them",
                       variable=keep_var, value="no",
                       font=("Helvetica", 10), bg=COLORS["card_bg"], fg="#e74c3c",
                       activebackground=COLORS["card_bg"], selectcolor=COLORS["card_bg"]).pack(anchor=tk.W)

        keyword_vars[kw] = keep_var

        # List the flagged GMPEs
        r = _next_row()
        list_frame = tk.Frame(scroll_frame, bg=COLORS["panel_bg"], padx=10, pady=4)
        list_frame.grid(row=r, column=0, sticky="ew", padx=6)
        for code, name in items:
            tk.Label(list_frame, text=f"  [{code}] {name}",
                     font=("Helvetica", 9), bg=COLORS["panel_bg"], fg=COLORS["status_fg"],
                     anchor=tk.W).pack(anchor=tk.W)

    # ── Buttons ──
    btn_frame = tk.Frame(dialog, bg=COLORS["bg"], padx=16, pady=12)
    btn_frame.pack(fill=tk.X)

    result = {"remove": set()}

    def _cleanup():
        try:
            dialog.unbind_all("<MouseWheel>")
        except Exception:
            pass
        dialog.destroy()

    def _on_accept():
        for kw, items in flagged.items():
            if keyword_vars[kw].get() != "yes":
                for code, name in items:
                    result["remove"].add(name)
        _cleanup()

    def _on_cancel():
        _cleanup()

    dialog.protocol("WM_DELETE_WINDOW", _cleanup)

    tk.Button(btn_frame, text="✅  Apply", font=("Helvetica", 12, "bold"),
              bg="#27ae60", fg=COLORS["fg"], relief=tk.FLAT, padx=20, pady=6,
              activebackground="#219a52", cursor="hand2",
              command=_on_accept).pack(side=tk.LEFT, padx=4)
    tk.Button(btn_frame, text="Skip (keep all)", font=("Helvetica", 11),
              bg=COLORS["card_bg"], fg=COLORS["fg"], relief=tk.FLAT, padx=12, pady=6,
              activebackground=COLORS["border"], cursor="hand2",
              command=_on_cancel).pack(side=tk.LEFT, padx=4)

    # ── Center on parent ──
    dialog.update_idletasks()
    px = parent.winfo_x() + (parent.winfo_width() - dialog.winfo_reqwidth()) // 2
    py = parent.winfo_y() + (parent.winfo_height() - dialog.winfo_reqheight()) // 2
    dialog.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    parent.wait_window(dialog)
    return result["remove"]


def make_gmpe_code(name):
    """Generate short code from full OQ class name (same as GMPE_selection.py)."""
    m = re.search(r"(\d{4})", name)
    if not m:
        return name
    year = m.group(1)
    author_part = name[:m.start()]
    suffix = name[m.end():]
    if "EtAl" in author_part:
        first = author_part.split("EtAl")[0]
        code = first[:2]
    else:
        parts = re.findall(r'[A-Z][a-z]*', author_part)
        code = "".join(p[0] for p in parts if p)
    return code + year + suffix


def save_selection(path, selection, gmpe_map, event_name=None):
    """Save selection dict → JSON file with [shortcut, fullname] pairs.

    If *event_name* is given, all GMPEs from all events are combined into
    a single key (the event name).  Otherwise the current behaviour is
    preserved (one key per event, e.g. HF_SMS / LF_SMS).
    """
    data = {}
    if event_name:
        # Single-event format: {event_name: [[code, fullname], ...]}
        all_names = set()
        for names in selection.values():
            all_names.update(names)
        if all_names:
            pairs = []
            for n in sorted(all_names):
                code = make_gmpe_code(n)
                pairs.append([code, n])
            data[event_name] = pairs
    else:
        # Classic multi-event format
        for ev, names in selection.items():
            if not names:
                continue
            pairs = []
            for n in sorted(names):
                code = make_gmpe_code(n)
                pairs.append([code, n])
            data[ev] = pairs
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return True


# ═══════════════════════════════════════════════════════════════
#  Guided questions dialog (used by the startup wizard)
# ═══════════════════════════════════════════════════════════════

def _show_guided_questions_dialog(parent):
    """Show a step-by-step filter questions dialog.

    Collects filter criteria from the user (year range, region, distances,
    site, IMTs, std devs) and returns a filters dict if accepted, or None
    if cancelled. The dict is used by __init__ to pre-set the main window's
    filter controls.
    """
    dialog = tk.Toplevel(parent)
    dialog.title("Interactive GMPE Selection — Guided Questions")
    dialog.geometry("620x700")
    dialog.minsize(500, 500)
    dialog.configure(bg=COLORS["bg"])
    dialog.transient(parent)
    dialog.grab_set()

    result = {"accepted": False, "filters": {}}

    # ── Header ──
    header = tk.Frame(dialog, bg="#27ae60", padx=20, pady=14)
    header.pack(fill=tk.X)
    tk.Label(header, text="🎯  Guided GMPE Selection",
             font=("Helvetica", 16, "bold"), fg="white", bg="#27ae60").pack()
    tk.Label(header, text="Answer the questions below, then click \"Start Research\"\n"
                          "to filter suitable GMPEs and open the main window.",
             font=("Helvetica", 10), fg="#d5f5e3", bg="#27ae60", justify=tk.CENTER).pack(pady=(4, 0))

    # ── Scrollable body with questions ──
    canvas = tk.Canvas(dialog, bg=COLORS["bg"], highlightthickness=0)
    scrollbar = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=canvas.yview)
    scroll_frame = tk.Frame(canvas, bg=COLORS["bg"])

    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=520)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0), pady=12)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=12)

    # ── Mousewheel / trackpad scrolling ──
    def _on_mousewheel(event):
        if not canvas.winfo_exists():
            return
        if _pltfrm.system() == "Linux" and not hasattr(event, 'delta'):
            return
        canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")
    canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-3, "units")
                     if canvas.winfo_exists() else None, add="+")
    canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(3, "units")
                     if canvas.winfo_exists() else None, add="+")

    row_idx = [0]

    def _next_row():
        r = row_idx[0]
        row_idx[0] += 1
        return r

    def _add_section(title):
        r = _next_row()
        lbl = tk.Label(scroll_frame, text=title,
                       font=("Helvetica", 12, "bold"), bg=COLORS["bg"], fg=COLORS["fg"],
                       anchor=tk.W)
        lbl.grid(row=r, column=0, sticky=tk.W, pady=(12, 4), padx=6)
        return lbl

    def _add_checkbox_group(options, defaults):
        """Add a group of checkboxes. Returns {option: BooleanVar}."""
        frame = tk.Frame(scroll_frame, bg=COLORS["card_bg"], padx=10, pady=6)
        r = _next_row()
        frame.grid(row=r, column=0, sticky="ew", padx=6)
        vars_dict = {}
        for i, opt in enumerate(options):
            v = tk.BooleanVar(value=(opt in defaults))
            cb = tk.Checkbutton(frame, text=opt, variable=v,
                                font=("Helvetica", 10), bg=COLORS["card_bg"], fg=COLORS["fg"],
                                activebackground=COLORS["card_bg"])
            cb.grid(row=i // 3, column=i % 3, sticky=tk.W, padx=4, pady=1)
            vars_dict[opt] = v
        return vars_dict

    # ── 0. Event / Project Name ──
    _add_section("0. Event / Project Name")
    evt_frame = tk.Frame(scroll_frame, bg=COLORS["card_bg"], padx=10, pady=8)
    evt_frame.grid(row=_next_row(), column=0, sticky="ew", padx=6)
    tk.Label(evt_frame, text="Name:", font=("Helvetica", 10), bg=COLORS["card_bg"]).pack(side=tk.LEFT)
    event_name_var = tk.StringVar(value="")
    tk.Entry(evt_frame, textvariable=event_name_var, width=24,
             font=("Helvetica", 11)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
    tk.Label(evt_frame, text="  Used for the output filename", font=("Helvetica", 9),
             bg=COLORS["card_bg"], fg=COLORS["status_fg"]).pack(side=tk.LEFT)

    # ── 1. Publication Year Range ──
    _add_section("1. Publication Year Range")
    yr_frame = tk.Frame(scroll_frame, bg=COLORS["card_bg"], padx=10, pady=8)
    yr_frame.grid(row=_next_row(), column=0, sticky="ew", padx=6)
    tk.Label(yr_frame, text="Min year:", font=("Helvetica", 10), bg=COLORS["card_bg"]).pack(side=tk.LEFT)
    yr_min_var = tk.StringVar(value="2014")
    tk.Entry(yr_frame, textvariable=yr_min_var, width=8, font=("Helvetica", 10)).pack(side=tk.LEFT, padx=4)
    tk.Label(yr_frame, text="  Max year:", font=("Helvetica", 10), bg=COLORS["card_bg"]).pack(side=tk.LEFT, padx=(8, 0))
    yr_max_var = tk.StringVar(value="")
    tk.Entry(yr_frame, textvariable=yr_max_var, width=8, font=("Helvetica", 10)).pack(side=tk.LEFT, padx=4)

    # ── 2. Tectonic Region ──
    _add_section("2. Tectonic Region (substring match)")
    region_vars = _add_checkbox_group(
        sorted(ALL_REGIONS),
        defaults=["Active Shallow Crust", "Stable Shallow Crust"]
    )

    # ── 3. Required Distance Metrics (any) ──
    _add_section("3. Required Distance Metrics (at least one)")
    dist_vars = _add_checkbox_group(
        sorted(ALL_DISTANCES),
        defaults=["rjb", "rhypo", "rrup"]
    )

    # ── 4. Required Site Parameters (all) ──
    _add_section("4. Required Site Parameters (all must be supported)")
    site_vars = _add_checkbox_group(
        sorted(ALL_SITES),
        defaults=["vs30"]
    )

    # ── 5. IMT Types (all) ──
    _add_section("5. Intensity Measure Types (all must be supported)")
    imt_vars = _add_checkbox_group(
        sorted(ALL_IMTS),
        defaults=["SA", "PGA", "PGV"]
    )

    # ── 6. Standard Deviation Types (all) ──
    _add_section("6. Standard Deviation Types (all must be supported)")
    std_vars = _add_checkbox_group(
        sorted(ALL_STDS),
        defaults=["Total"]
    )

    # ── Buttons ──
    btn_frame = tk.Frame(dialog, bg=COLORS["bg"], padx=16, pady=12)
    btn_frame.pack(fill=tk.X)

    status_var = tk.StringVar(value="")
    status_label = tk.Label(btn_frame, textvariable=status_var,
                            font=("Helvetica", 9), bg=COLORS["bg"], fg=COLORS["status_fg"])
    status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))

    def _collect_filters():
        """Read all answers and build the filters dict."""
        filters = {}
        # Event name
        evt_name = event_name_var.get().strip()
        if evt_name:
            filters["event_name"] = evt_name
        # Year
        yr_min = yr_min_var.get().strip()
        yr_max = yr_max_var.get().strip()
        if yr_min:
            try:
                filters["year_min"] = int(yr_min)
            except ValueError:
                pass
        if yr_max:
            try:
                filters["year_max"] = int(yr_max)
            except ValueError:
                pass
        # Region
        selected_regions = [r for r, v in region_vars.items() if v.get()]
        if selected_regions:
            filters["region"] = selected_regions
        # Distance (any)
        selected_dists = [d for d, v in dist_vars.items() if v.get()]
        if selected_dists:
            filters["dist_any"] = selected_dists
        # Site (all)
        selected_sites = [s for s, v in site_vars.items() if v.get()]
        if selected_sites:
            filters["site_all"] = selected_sites
        # IMT (all)
        selected_imts = [i for i, v in imt_vars.items() if v.get()]
        if selected_imts:
            filters["imt_all"] = selected_imts
        # Std Dev (all)
        selected_stds = [s for s, v in std_vars.items() if v.get()]
        if selected_stds:
            filters["std_all"] = selected_stds
        return filters

    def _cleanup():
        """Unbind the global mousewheel handler and destroy the dialog."""
        try:
            dialog.unbind_all("<MouseWheel>")
        except Exception:
            pass
        dialog.destroy()

    def _on_accept():
        filters = _collect_filters()
        result["accepted"] = True
        result["filters"] = filters
        _cleanup()

    def _on_cancel():
        _cleanup()

    # Also clean up on window close (X button)
    dialog.protocol("WM_DELETE_WINDOW", _cleanup)

    tk.Button(btn_frame, text="🔬  Start Research", font=("Helvetica", 12, "bold"),
              bg="#27ae60", fg=COLORS["fg"], relief=tk.FLAT, padx=20, pady=6,
              activebackground="#219a52", cursor="hand2",
              command=_on_accept).pack(side=tk.LEFT, padx=4)
    tk.Button(btn_frame, text="Cancel", font=("Helvetica", 11),
              bg=COLORS["card_bg"], fg=COLORS["fg"], relief=tk.FLAT, padx=12, pady=6,
              activebackground=COLORS["border"], cursor="hand2",
              command=_on_cancel).pack(side=tk.LEFT, padx=4)

    # ── Center on parent ──
    dialog.update_idletasks()
    px = parent.winfo_x() + (parent.winfo_width() - dialog.winfo_reqwidth()) // 2
    py = parent.winfo_y() + (parent.winfo_height() - dialog.winfo_reqheight()) // 2
    dialog.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    parent.wait_window(dialog)
    return result["filters"] if result["accepted"] else None


def _show_family_variant_dialog(parent, catalogue, display_rows, filters,
                                already_removed=None):
    """Show a dialog to pick GMPE family variants.

    Groups GMPEs by family (base name before the year) and asks the user
    which variants to keep when multiple variants of the same family exist.

    Returns a set of additional GMPE names to remove.
    """
    if already_removed is None:
        already_removed = set()

    # Get the currently matched GMPE names (after filters and previous removals)
    matched_names = _gmpe_names_for_filters(catalogue, display_rows, filters)
    matched_names = [n for n in matched_names if n not in already_removed]

    # Group by family (base name before year)
    import re

    def _base_name(name):
        m = re.search(r"\d{4}", name)
        return name[:m.end()] if m else name

    families = {}
    for name in matched_names:
        base = _base_name(name)
        code = make_gmpe_code(name)
        families.setdefault(base, []).append((code, name))

    # Filter to only families with multiple variants
    multi_families = {b: m for b, m in sorted(families.items()) if len(m) > 1}
    if not multi_families:
        return set()

    to_remove = set()

    dialog = tk.Toplevel(parent)
    dialog.title("GMPE Family Variants")
    dialog.geometry("900x620")
    dialog.minsize(700, 400)
    dialog.configure(bg=COLORS["bg"])
    dialog.transient(parent)
    dialog.grab_set()

    # ── Header ──
    header = tk.Frame(dialog, bg="#8e44ad", padx=20, pady=14)
    header.pack(fill=tk.X)
    tk.Label(header, text="📦  GMPE Family Variants",
             font=("Helvetica", 15, "bold"), fg="white", bg="#8e44ad").pack()
    tk.Label(header, text="Some GMPE families have multiple variants.\n"
                          "Please choose which ones to keep.",
             font=("Helvetica", 10), fg="#e8daef", bg="#8e44ad", justify=tk.CENTER).pack(pady=(4, 0))

    # ── Body: horizontal paned window (left: families, right: detail) ──
    body_pane = ttk.PanedWindow(dialog, orient=tk.HORIZONTAL)
    body_pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    # ── Left pane: scrollable family list ──
    left_frame = ttk.Frame(body_pane)
    body_pane.add(left_frame, weight=1)

    canvas = tk.Canvas(left_frame, bg=COLORS["bg"], highlightthickness=0)
    scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=canvas.yview)
    scroll_frame = tk.Frame(canvas, bg=COLORS["bg"])

    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=460)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0), pady=6)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=6)

    # ── Right pane: GMPE detail panel ──
    right_frame = ttk.LabelFrame(body_pane, text=" GMPE Details ", padding="4")
    body_pane.add(right_frame, weight=1)

    fam_detail_text = tk.Text(right_frame, height=10, wrap=tk.WORD,
                               font=("Helvetica", 11),
                               foreground=COLORS["fg"],
                               background=COLORS["input_bg"],
                               padx=6, pady=4)
    fam_detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    fam_detail_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL,
                                       command=fam_detail_text.yview)
    fam_detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    fam_detail_text.configure(yscrollcommand=fam_detail_scroll.set)
    fam_detail_text.insert(tk.END, "Click on a GMPE checkbox\nto see its details")
    fam_detail_text.config(state=tk.DISABLED)

    # ── Helper: show GMPE details in the right panel ──
    def _show_fam_detail(gmpe_name):
        """Look up GMPE in the catalogue and display its details."""
        cat_row = next((r for r in catalogue if r["GMPE"] == gmpe_name), None)
        if not cat_row:
            return
        c_code = cat_row.get("Shortcut", cat_row["Code"])
        c_year = cat_row["Year"]
        c_region = cat_row["TectonicRegion"]
        c_dists = " ".join(sorted(cat_row["RequiresDistances"]))
        c_sites = " ".join(sorted(cat_row["RequiresSites"]))
        c_rupt = " ".join(sorted(cat_row["RequiresRupture"]))
        c_imts = " ".join(sorted(cat_row["DefinedForIMTs"]))
        c_stds = " ".join(sorted(cat_row["DefinedForStdDevs"]))
        c_desc = cat_row.get("Description", "").strip()
        # Try direct OQ import first, fall back to CSV Description column
        oq_text = None
        try:
            from openquake.hazardlib import gsim as _oq_gsim
            _oq_cls = _oq_gsim.get_available_gsims().get(gmpe_name)
            if _oq_cls is not None:
                _doc = (_oq_cls.__doc__ or "").strip()
                if _doc:
                    _para = _doc.split("\n\n")[0] if "\n\n" in _doc else _doc
                    _lines = [l.strip() for l in _para.split("\n") if l.strip()]
                    _short_desc = " ".join(_lines).replace("\t", " ")
                    if len(_short_desc) > 2000:
                        _short_desc = _short_desc[:1997] + "..."
                    oq_text = _short_desc[:500] + "…" if len(_short_desc) > 500 else _short_desc
        except Exception:
            pass
        if oq_text is None and c_desc:
            oq_text = c_desc[:500] + "…" if len(c_desc) > 500 else c_desc
        detail = (
            f"📌 [{c_code}] {gmpe_name}\n"
            f"{'=' * 50}\n"
            f"   Year: {c_year}  |  Region: {c_region}\n"
            f"   Distances: {c_dists}\n"
            f"   Sites:      {c_sites}\n"
            f"   Rupture:    {c_rupt}\n"
            f"   IMTs:       {c_imts}\n"
            f"   StdDevs:    {c_stds}\n"
        )
        if oq_text:
            detail += f"{'=' * 50}\n📘 {oq_text}\n"
        fam_detail_text.config(state=tk.NORMAL)
        fam_detail_text.delete("1.0", tk.END)
        fam_detail_text.insert(tk.END, detail)
        fam_detail_text.config(state=tk.DISABLED)

    # ── Mousewheel / trackpad ──
    def _on_mousewheel(event):
        if not canvas.winfo_exists():
            return
        if _pltfrm.system() == "Linux" and not hasattr(event, 'delta'):
            return
        canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")
    canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-3, "units")
                     if canvas.winfo_exists() else None, add="+")
    canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(3, "units")
                     if canvas.winfo_exists() else None, add="+")

    row_idx = [0]

    def _next_row():
        r = row_idx[0]
        row_idx[0] += 1
        return r

    all_keep_vars = {}  # base_name → StringVar("yes"/"no"/"pick")

    for base, members in multi_families.items():
        r = _next_row()
        lbl = tk.Label(scroll_frame,
                       text=f"🏷️  {base} — {len(members)} variant(s)",
                       font=("Helvetica", 12, "bold"), bg=COLORS["bg"], fg=COLORS["fg"],
                       anchor=tk.W)
        lbl.grid(row=r, column=0, sticky=tk.W, pady=(10, 2), padx=6)

        r = _next_row()
        radio_frame = tk.Frame(scroll_frame, bg=COLORS["card_bg"], padx=10, pady=6)
        radio_frame.grid(row=r, column=0, sticky="ew", padx=6)

        keep_var = tk.StringVar(value="none")  # default: keep none
        all_keep_vars[base] = keep_var

        tk.Radiobutton(radio_frame, text="Keep none (remove all)",
                       variable=keep_var, value="none",
                       font=("Helvetica", 10), bg=COLORS["card_bg"], fg="#e74c3c",
                       activebackground=COLORS["card_bg"], selectcolor=COLORS["card_bg"]).pack(anchor=tk.W)
        tk.Radiobutton(radio_frame, text="Pick specific variants (check below)",
                       variable=keep_var, value="pick",
                       font=("Helvetica", 10), bg=COLORS["card_bg"], fg=COLORS["fg"],
                       activebackground=COLORS["card_bg"], selectcolor=COLORS["card_bg"]).pack(anchor=tk.W)
        tk.Radiobutton(radio_frame, text="Keep all variants",
                       variable=keep_var, value="all",
                       font=("Helvetica", 10), bg=COLORS["card_bg"], fg=COLORS["fg"],
                       activebackground=COLORS["card_bg"], selectcolor=COLORS["card_bg"]).pack(anchor=tk.W)

        # List members with checkboxes (for "pick" mode)
        r = _next_row()
        list_frame = tk.Frame(scroll_frame, bg="#f8f9fa", padx=10, pady=4)
        list_frame.grid(row=r, column=0, sticky="ew", padx=6)

        member_vars = {}
        for code, name in members:
            v = tk.BooleanVar(value=False)  # default: unchecked
            cb = tk.Checkbutton(list_frame, text=f"[{code}] {name}",
                                variable=v,
                                font=("Helvetica", 9), bg=COLORS["panel_bg"], fg=COLORS["fg"],
                                activebackground=COLORS["panel_bg"])
            cb.pack(anchor=tk.W, padx=4, pady=1)
            # Show GMPE details in the right panel when toggled
            def _on_checkbox(*_, _code=code, _name=name, _v=v):
                if _v.get():
                    _show_fam_detail(_name)
                else:
                    fam_detail_text.config(state=tk.NORMAL)
                    fam_detail_text.delete("1.0", tk.END)
                    fam_detail_text.insert(tk.END, "Click on a GMPE checkbox\nto see its details")
                    fam_detail_text.config(state=tk.DISABLED)
            v.trace_add("write", _on_checkbox)
            member_vars[(code, name)] = v

        # When "none" is selected → uncheck all; when "all" → check all
        def _on_keep_change(*_, _kv=keep_var, _mv=member_vars):
            val = _kv.get()
            if val == "none":
                for mv in _mv.values():
                    mv.set(False)
            elif val == "all":
                for mv in _mv.values():
                    mv.set(True)
            # "pick" — leave checkboxes as they are
        keep_var.trace_add("write", _on_keep_change)

        all_keep_vars[base + "_members"] = member_vars

    # ── Buttons ──
    btn_frame = tk.Frame(dialog, bg=COLORS["bg"], padx=16, pady=12)
    btn_frame.pack(fill=tk.X)

    result = {"remove": set()}

    def _cleanup():
        try:
            dialog.unbind_all("<MouseWheel>")
        except Exception:
            pass
        dialog.destroy()

    def _on_accept():
        for base, members in multi_families.items():
            choice = all_keep_vars[base]
            member_vars = all_keep_vars.get(base + "_members", {})
            if choice.get() == "none":
                # Remove all members of this family
                for code, name in members:
                    to_remove.add(name)
                    print(f"    🗑️ Family '{base}': removed [{code}] {name}")
            elif choice.get() == "pick":
                # Remove only unchecked ones
                for (code, name), v in member_vars.items():
                    if not v.get():
                        to_remove.add(name)
                        print(f"    🗑️ Family '{base}': removed (unchecked) [{code}] {name}")
            # "all" — keep everything, nothing to remove
        print(f"    → Total family removals: {len(to_remove)}")
        result["remove"] = to_remove
        _cleanup()

    def _on_skip():
        _cleanup()

    dialog.protocol("WM_DELETE_WINDOW", _cleanup)

    tk.Button(btn_frame, text="✅  Apply", font=("Helvetica", 12, "bold"),
              bg="#8e44ad", fg=COLORS["fg"], relief=tk.FLAT, padx=20, pady=6,
              activebackground="#7d3c98", cursor="hand2",
              command=_on_accept).pack(side=tk.LEFT, padx=4)
    tk.Button(btn_frame, text="Skip (keep all)", font=("Helvetica", 11),
              bg=COLORS["card_bg"], fg=COLORS["fg"], relief=tk.FLAT, padx=12, pady=6,
              activebackground=COLORS["border"], cursor="hand2",
              command=_on_skip).pack(side=tk.LEFT, padx=4)

    # ── Center on parent ──
    dialog.update_idletasks()
    px = parent.winfo_x() + (parent.winfo_width() - dialog.winfo_reqwidth()) // 2
    py = parent.winfo_y() + (parent.winfo_height() - dialog.winfo_reqheight()) // 2
    dialog.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    parent.wait_window(dialog)
    return result["remove"]


# ── Auto‑generate catalogue CSV (silent) ──────────────────────

def _ensure_catalogue(catalogue_path):
    """Generate gmpe_catalogue.csv if missing — runs OpenQuake silently."""
    if os.path.exists(catalogue_path):
        return
    print(f"  ⚠ Catalogue '{catalogue_path}' not found — generating (this may take a moment)...")

    _OQ_PYTHON = os.path.expanduser("~/openquake/Scripts/python.exe")

    # If not in the OpenQuake environment, delegate to a subprocess.
    if _pltfrm.system() == "Windows":
        _OQ_CHECK = os.path.expanduser("~/openquake")
    else:
        _OQ_CHECK = os.path.expanduser("~/openquake/bin/python")
    if not sys.executable.startswith(_OQ_CHECK):
        print(f"🔁 Launching catalogue generator in OpenQuake environment...")
        import subprocess as _sp
        import tempfile as _tf

        # Write a self-contained helper script to a temp file
        _helper = _tf.NamedTemporaryFile(mode="w", suffix=".py", delete=False, prefix="oq_gen_")
        _helper.write("import csv, re, sys\n")
        _helper.write("from openquake.hazardlib import gsim\n\n")
        _helper.write("def _mc(name):\n")
        _helper.write("    m=re.search(r'(\\d{4})',name)\n")
        _helper.write("    if not m: return name\n")
        _helper.write("    yr=m.group(1); ap=name[:m.start()]; sf=name[m.end():]\n")
        _helper.write("    if 'EtAl' in ap:\n")
        _helper.write("        code=ap.split('EtAl')[0][:2]\n")
        _helper.write("    else:\n")
        _helper.write("        parts=re.findall(r'[A-Z][a-z]*',ap)\n")
        _helper.write("        code=''.join(p[0] for p in parts if p)\n")
        _helper.write("    return code+yr+sf\n\n")
        _helper.write("def _desc(cls):\n")
        _helper.write("    doc=(cls.__doc__ or '').strip()\n")
        _helper.write("    para=doc.split(chr(10)*2)[0] if chr(10)*2 in doc else doc\n")
        _helper.write("    lines=[l.strip() for l in para.split(chr(10)) if l.strip()]\n")
        _helper.write("    s=' '.join(lines).replace('\\t',' ')\n")
        _helper.write("    return s[:1997]+'...' if len(s)>2000 else s\n\n")
        _helper.write("rows=[]\n")
        _helper.write("for key,cls in sorted(gsim.get_available_gsims().items(),key=lambda x:x[0]):\n")
        _helper.write("    try:\n")
        _helper.write("        inst=cls()\n")
        _helper.write("        m=re.search(r'(\\d{4})',key)\n")
        _helper.write("        yr=int(m.group(1)) if m else 0\n")
        _helper.write("        reg=inst.DEFINED_FOR_TECTONIC_REGION_TYPE\n")
        _helper.write("        rs=reg.value if reg else '\\u2014'\n")
        _helper.write("        imts=inst.DEFINED_FOR_INTENSITY_MEASURE_TYPES\n")
        _helper.write("        imt_str=' '.join(sorted(i.__name__.upper() for i in imts)) if imts else ''\n")
        _helper.write("        stds_tmp=inst.DEFINED_FOR_STANDARD_DEVIATION_TYPES\n")
        _helper.write("        std_str=' '.join(sorted(stds_tmp)) if stds_tmp else ''\n")
        _helper.write("        dists=' '.join(sorted(inst.REQUIRES_DISTANCES))\n")
        _helper.write("        rupts=' '.join(sorted(inst.REQUIRES_RUPTURE_PARAMETERS))\n")
        _helper.write("        sites=' '.join(sorted(inst.REQUIRES_SITES_PARAMETERS))\n")
        _helper.write("        sc=_mc(key)\n")
        _helper.write("        desc=_desc(cls)\n")
        _helper.write("    except Exception:\n")
        _helper.write("        yr,rs,imt_str,std_str,dists,rupts,sites,sc,desc=0,'\\u2014','','','','','','',''\n")
        _helper.write("    rows.append((key,yr,rs,dists,rupts,sites,imt_str,std_str,sc,desc))\n")
        _helper.write("_CAT = %r\n" % catalogue_path)
        _helper.write("with open(_CAT,'w',newline='') as f:\n")
        _helper.write("    w=csv.writer(f)\n")
        _helper.write("    w.writerow(['Code','GMPE','Year','TectonicRegion',\n")
        _helper.write("        'RequiresDistances','RequiresRupture','RequiresSites',\n")
        _helper.write("        'DefinedForIMTs','DefinedForStdDevs','Shortcut','Description'])\n")
        _helper.write("    for r in rows:\n")
        _helper.write("        w.writerow([r[0],r[0]]+list(r[1:]))\n")
        _helper.write("print('  \\u2705 Generated ' + repr(_CAT) + ' (' + str(len(rows)) + ' GMPEs)')\n")
        _helper.write("sys.stdout.flush()\n")
        _helper.close()

        _result = _sp.run([_OQ_PYTHON, _helper.name], capture_output=True, text=True, timeout=180)
        os.unlink(_helper.name)

        if _result.returncode == 0:
            for line in _result.stdout.strip().splitlines():
                if line.strip():
                    print(f"  {line.strip()}")
        else:
            print(f"  ❌ OpenQuake catalogue generation failed:")
            for line in _result.stderr.strip().splitlines():
                print(f"     {line}")
            print(f"     → Create '{catalogue_path}' manually or run from OQ environment.")
        return

    # ── We are inside OpenQuake Python — generate the catalogue ──
    from openquake.hazardlib import gsim

    all_gsims = gsim.get_available_gsims()
    sorted_items = sorted(all_gsims.items(), key=lambda x: x[0])

    import re as _re
    _year_re = _re.compile(r"(\d{4})")

    rows = []
    for key, cls in sorted_items:
        try:
            inst = cls()
            m = _year_re.search(key)
            year = int(m.group(1)) if m else 0
            dists = inst.REQUIRES_DISTANCES
            rupt  = inst.REQUIRES_RUPTURE_PARAMETERS
            sites = inst.REQUIRES_SITES_PARAMETERS
            region = inst.DEFINED_FOR_TECTONIC_REGION_TYPE
            region_str = region.value if region else "—"
            imts = inst.DEFINED_FOR_INTENSITY_MEASURE_TYPES
            imt_str = " ".join(sorted(imt.__name__.upper() for imt in imts)) if imts else ""
            stds = inst.DEFINED_FOR_STANDARD_DEVIATION_TYPES
            std_str = " ".join(sorted(stds)) if stds else ""
            shortcut = make_gmpe_code(key)
            # Extract docstring (first paragraph) for user-friendly description
            doc = (cls.__doc__ or "").strip()
            para = doc.split("\n\n")[0] if "\n\n" in doc else doc
            lines = [l.strip() for l in para.split("\n") if l.strip()]
            description = " ".join(lines).replace("\t", " ")
            if len(description) > 2000:
                description = description[:1997] + "..."
        except Exception:
            year = 0
            dists, rupt, sites = set(), set(), set()
            region_str = "—"
            imt_str = ""
            std_str = ""
            shortcut = ""
            description = ""
        rows.append((key, year, region_str, dists, rupt, sites, imt_str, std_str, shortcut, description))

    import csv as _csv
    with open(catalogue_path, "w", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["Code", "GMPE", "Year", "TectonicRegion",
                     "RequiresDistances", "RequiresRupture", "RequiresSites",
                     "DefinedForIMTs", "DefinedForStdDevs", "Shortcut",
                     "Description"])
        for key, year, region, dists, rupt, sites, imt_str, std_str, shortcut, description in rows:
            w.writerow([key, key, year, region,
                        " ".join(sorted(dists)),
                        " ".join(sorted(rupt)),
                        " ".join(sorted(sites)),
                        imt_str, std_str, shortcut,
                        description])
    print(f"  ✅ Generated '{catalogue_path}' ({len(rows)} GMPEs)")


# ═══════════════════════════════════════════════════════════════
#  GUI Application
# ═══════════════════════════════════════════════════════════════

class GMPESelectionGUI:
    """Main application window."""

    def __init__(self, catalogue_path):
        self.catalogue_path = catalogue_path
        self.selection_path = DEFAULT_SELECTION
        self.catalogue = []
        self.display_rows = []
        self.event_names = list(EVENTS)  # dynamic event list (updated on load/guided)
        self.selection = {ev: set() for ev in self.event_names}  # event → set of full names
        self.current_event = self.event_names[0]
        self._guided_filters = None  # will hold filters from the guided dialog

        # Build a hidden root first (needed by the wizard dialog)
        self.root = tk.Tk()
        self.root.withdraw()
        # Apply global colour palette for dark‑mode compatibility
        self.root.tk_setPalette(
            background=COLORS["bg"],
            foreground=COLORS["fg"],
            selectBackground=COLORS["select_bg"],
            selectForeground=COLORS["input_fg"],
            activeBackground=COLORS["card_bg"],
            activeForeground=COLORS["fg"],
        )
        _FONT_FAMILY = "Segoe UI" if _pltfrm.system() == "Windows" else "Helvetica"
        self.root.option_add("*Font", _FONT_FAMILY + " 11")
        self.root.option_add("*Background", COLORS["bg"])
        self.root.option_add("*Foreground", COLORS["fg"])
        self.root.option_add("*SelectBackground", COLORS["select_bg"])
        self.root.option_add("*SelectForeground", COLORS["input_fg"])

        # Load data
        self._load_catalogue_data()

        # ── Show startup wizard (before building main UI) ──
        wizard_result = self._show_startup_wizard(
            catalogue=self.catalogue, display_rows=self.display_rows
        )
        wizard_action = wizard_result.get("action", "fresh")
        self._guided_filters = wizard_result.get("filters")
        loaded_sel = wizard_result.get("selection")
        remove_names = wizard_result.get("remove_names", set())
        print(f"  Wizard choice: {wizard_action}")

        # Re-show the root and build the main UI
        self.root.deiconify()
        self.root.protocol("WM_DELETE_WINDOW", self._quit_app)
        self.root.title("GMPE Selection — RESPMAtch")
        self.root.geometry("1400x850")
        self._setup_style()
        self._auto_apply_after_id = None
        self._build_ui()

        # Apply wizard choice
        if wizard_action == "load" and loaded_sel:
            # Use original keys from the file (raw data) to preserve the
            # exact event names, then populate selection from those keys.
            raw_data = wizard_result.get("selection_raw_data") or {}
            raw_keys = wizard_result.get("selection_keys")
            if raw_keys:
                self._set_event_names(raw_keys)
                # Populate from raw data so keys match self.event_names
                for ev in self.event_names:
                    pairs = raw_data.get(ev, [])
                    names = set()
                    for it in pairs:
                        names.add(it[1] if isinstance(it, list) else it)
                    self.selection[ev] = names
            else:
                # Fallback: use normalized keys from load_selection
                self._set_event_names(list(loaded_sel.keys()))
                for ev in self.event_names:
                    if ev in loaded_sel:
                        self.selection[ev] = loaded_sel[ev]
            # Remember the loaded file path for later saves
            if "selection_path" in wizard_result:
                self.selection_path = wizard_result["selection_path"]
            print(f"  ✓ Loaded selection from file via wizard")
        elif wizard_action == "review":
            # Apply guided filters from the questionnaire if available
            if self._guided_filters:
                # Use event name for the output filename & dropdown
                evt_name = self._guided_filters.get("event_name", "").strip()
                if evt_name:
                    safe = evt_name.replace(" ", "_").replace("/", "_")
                    self.selection_path = f"{safe}_selection.json"
                    self._set_event_names([evt_name])
                    print(f"  📝 Event name: '{evt_name}' → {self.selection_path}")
                self._apply_guided_filters(self._guided_filters)
                print(f"  ✓ Applied guided filters from questionnaire")
            # Remove country-specific GMPEs the user rejected
            if remove_names:
                for ev in self.event_names:
                    self.selection[ev] -= remove_names
                print(f"  ✓ Removed {len(remove_names)} region-specific GMPE(s) not relevant")
            print("  ✓ Starting interactive selection with guided filters")
        # "fresh" — keep empty selection, default filters apply

        # Initial filter (no debounce)
        self._apply_filters()

        # ── Populate selection with matched GMPEs (only for "review") ──
        if wizard_action == "review" and hasattr(self, '_matched_rows'):
            matched_names = {row["name"] for row in self._matched_rows}
            # Remove any names the user rejected via country/family dialogs
            if remove_names:
                before = len(matched_names)
                matched_names -= remove_names
                removed_count = before - len(matched_names)
                if removed_count:
                    print(f"  🗑️ Excluded {removed_count} rejected GMPE(s) from selection")
            # Add all remaining matched names to the current event's selection
            for ev in self.event_names:
                self.selection[ev] |= matched_names
            print(f"  ✓ Added {len(matched_names)} GMPE(s) to selection")
            # Safety pass: ensure removed names are truly gone
            if remove_names:
                for ev in self.event_names:
                    self.selection[ev] -= remove_names
            # Refresh both lists so the right column shows the selection
            self._refresh_both_lists()

    # ── Apply guided filters from the questionnaire ─────────────

    def _apply_guided_filters(self, filters):
        """Set UI filter controls to match the answers from the guided dialog."""
        if not filters:
            return
        # Year
        if "year_min" in filters:
            self.yr_min_var.set(str(filters["year_min"]))
        if "year_max" in filters:
            self.yr_max_var.set(str(filters["year_max"]))
        # Region
        selected_regions = set(filters.get("region", []))
        for reg, var in self.region_vars.items():
            var.set(reg in selected_regions)
        # Distance (any)
        selected_dists = set(filters.get("dist_any", []))
        for d, var in self.dist_vars.items():
            var.set(d in selected_dists)
        # Site (all)
        selected_sites = set(filters.get("site_all", []))
        for s, var in self.site_vars.items():
            var.set(s in selected_sites)
        # Rupture (all) — not asked in guided dialog, keep defaults
        # IMT (all)
        selected_imts = set(filters.get("imt_all", []))
        for imt, var in self.imt_vars.items():
            var.set(imt in selected_imts)
        # Std Dev (all)
        selected_stds = set(filters.get("std_all", []))
        for s, var in self.std_vars.items():
            var.set(s in selected_stds)
        print(f"  ✓ Applied {len(filters)} filter criteria from guided questions")

    # ── Startup wizard ─────────────────────────────────────────

    def _show_startup_wizard(self, catalogue=None, display_rows=None):
        """Show a startup dialog with two options before the main window.

        Returns a dict with:
          "action": "load" | "review" | "fresh"
          "filters": dict of filter criteria (only for "review")
          "selection": dict of event→set of names (only for "load")
          "remove_names": set of GMPE names to remove (country check)
        """
        import tkinter.simpledialog as simpledialog

        wizard = tk.Toplevel()
        wizard.title("GMPE Selection — Getting Started")
        wizard.geometry("600x580")
        wizard.minsize(480, 350)
        wizard.configure(bg=COLORS["bg"])
        wizard.grab_set()  # modal

        result = {"action": "fresh"}  # default fallback

        # ── Header ──
        header = tk.Frame(wizard, bg="#2c3e50", padx=20, pady=16)
        header.pack(fill=tk.X)
        tk.Label(header, text="🚀  GMPE Selection Wizard",
                 font=("Helvetica", 18, "bold"), fg="white", bg="#2c3e50").pack()
        tk.Label(header, text="How would you like to select GMPEs for this project?",
                 font=("Helvetica", 11), fg="#bdc3c7", bg="#2c3e50").pack(pady=(4, 0))

        # ── Body ──
        body = tk.Frame(wizard, bg=COLORS["bg"], padx=24, pady=20)
        body.pack(fill=tk.BOTH, expand=True)

        def _on_load():
            # Open file dialog immediately so the user picks a file
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title="Load GMPE Selection",
                initialdir=".",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            if path:
                # Read raw data to preserve original key names
                with open(path) as _f:
                    _raw_data = json.load(_f)
                _raw_keys = list(_raw_data.keys())
                # Also get the normalized version for backward-compat lookups
                sel = load_selection(path)
                if sel:
                    result["action"] = "load"
                    result["selection"] = sel
                    result["selection_raw_data"] = _raw_data
                    result["selection_keys"] = _raw_keys
                    result["selection_path"] = path
                    wizard.destroy()
                else:
                    from tkinter import messagebox
                    messagebox.showerror("Error",
                        f"No valid GMPE selection found in:\n{path}")

        def _on_review():
            # Show guided questions dialog; returns filters dict or None
            filters = _show_guided_questions_dialog(wizard)
            if filters is not None:
                result["action"] = "review"
                result["filters"] = filters
                all_removed = set()
                # Country-specific GMPE check
                if catalogue and display_rows:
                    country_removed = _show_country_keyword_dialog(
                        wizard, catalogue, display_rows, filters
                    )
                    all_removed.update(country_removed)
                    if country_removed:
                        print(f"  🗑️ {len(country_removed)} region-specific GMPE(s) removed")
                # Family variant selection
                if catalogue and display_rows:
                    family_removed = _show_family_variant_dialog(
                        wizard, catalogue, display_rows, filters,
                        already_removed=all_removed
                    )
                    all_removed.update(family_removed)
                    if family_removed:
                        print(f"  🗑️ {len(family_removed)} family variant(s) removed")
                result["remove_names"] = all_removed
                if all_removed:
                    print(f"  🗑️ {len(all_removed)} total GMPE(s) will be removed")
                wizard.destroy()

        def _on_fresh():
            result["action"] = "fresh"
            wizard.destroy()

        # Option 1: Load from file
        opt1 = tk.Frame(body, bg=COLORS["card_bg"], padx=16, pady=14, cursor="hand2")
        opt1.pack(fill=tk.X, pady=(0, 10))
        opt1.bind("<Button-1>", lambda e: _on_load())
        tk.Label(opt1, text="📂  Load existing selection from file",
                 font=("Helvetica", 14, "bold"), bg=COLORS["card_bg"], fg=COLORS["fg"]).pack(anchor=tk.W)
        tk.Label(opt1, text="Open a previously saved GMPE selection JSON file.\n"
                            "Quick start if you already have a selection ready.",
                 font=("Helvetica", 10), bg=COLORS["card_bg"], fg=COLORS["status_fg"], justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 0))
        opt1_btn = tk.Button(opt1, text="📂  Browse…", font=("Helvetica", 11, "bold"),
                             bg=COLORS["accent"], fg=COLORS["fg"], relief=tk.FLAT, padx=12, pady=4,
                             activebackground=COLORS["accent_dark"], cursor="hand2",
                             command=_on_load)
        opt1_btn.pack(anchor=tk.W, pady=(8, 0))

        # Option 2: Interactive review
        opt2 = tk.Frame(body, bg=COLORS["card_bg"], padx=16, pady=14, cursor="hand2")
        opt2.pack(fill=tk.X, pady=(0, 10))
        opt2.bind("<Button-1>", lambda e: _on_review())
        tk.Label(opt2, text="🎯  Interactive selection (questions)",
                 font=("Helvetica", 14, "bold"), bg=COLORS["card_bg"], fg=COLORS["fg"]).pack(anchor=tk.W)
        tk.Label(opt2, text="Answer guided questions to filter and select GMPEs.\n"
                            "Recommends defaults from GMPE_selection.py — year, region,\n"
                            "distance metrics, site parameters, IMTs, and std devs.",
                 font=("Helvetica", 10), bg=COLORS["card_bg"], fg=COLORS["status_fg"], justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 0))
        opt2_btn = tk.Button(opt2, text="🎯  Start selection", font=("Helvetica", 11, "bold"),
                             bg="#27ae60", fg=COLORS["fg"], relief=tk.FLAT, padx=12, pady=4,
                             activebackground="#219a52", cursor="hand2",
                             command=_on_review)
        opt2_btn.pack(anchor=tk.W, pady=(8, 0))

        # ── Footer — also "Start fresh" ──
        footer = tk.Frame(wizard, bg=COLORS["bg"], padx=24)
        footer.pack(fill=tk.X, pady=(0, 16))
        footer.pack(fill=tk.X)
        fresh_btn = tk.Button(footer, text="Skip — start with default filters",
                              font=("Helvetica", 9), fg=COLORS["status_fg"],
                              bg=COLORS["bg"],
                              relief=tk.FLAT, cursor="hand2", command=_on_fresh)
        fresh_btn.pack(side=tk.RIGHT)

        # ── Center on screen ──
        wizard.update_idletasks()
        x = (wizard.winfo_screenwidth() - wizard.winfo_reqwidth()) // 2
        y = (wizard.winfo_screenheight() - wizard.winfo_reqheight()) // 2
        wizard.geometry(f"+{x}+{y}")

        self.root.wait_window(wizard)
        return result

    # ── Styling ───────────────────────────────────────────────

    def _setup_style(self):
        style = ttk.Style()
        # Try to use a modern theme
        available = style.theme_names()
        for preferred in ("aqua", "clam", "alt"):
            if preferred in available:
                style.theme_use(preferred)
                break

        C = COLORS
        self.root.configure(bg=C["bg"])

        # General styles
        style.configure("TFrame", background=C["bg"])
        style.configure("TLabel", background=C["bg"], foreground=C["fg"],
                        font=("Helvetica", 12))
        style.configure("TButton", font=("Helvetica", 11, "bold"), padding=6)
        style.configure("TLabelframe", background=C["bg"], foreground=C["fg"],
                        font=("Helvetica", 11, "bold"))
        style.configure("TLabelframe.Label", background=C["bg"],
                        foreground=C["accent_dark"],
                        font=("Helvetica", 11, "bold"))
        style.configure("TEntry", fieldbackground=C["input_bg"],
                        foreground=C["input_fg"], font=("Helvetica", 12))

        # Treeview
        style.configure("Treeview", background=C["input_bg"],
                        foreground=C["input_fg"],
                        fieldbackground=C["input_bg"],
                        font=("Helvetica", 11))
        style.configure("Treeview.Heading", font=("Helvetica", 11, "bold"),
                        background=C["accent"], foreground="white")
        style.map("Treeview.Heading", background=[("active", C["accent_dark"])])
        style.map("Treeview", background=[("selected", C["select_bg"])])

        # Accent button (for primary actions)
        style.configure("Accent.TButton", font=("Helvetica", 11, "bold"),
                        foreground="white", background=C["accent"])
        style.map("Accent.TButton",
                  background=[("active", C["accent_dark"]),
                              ("pressed", C["accent_dark"])])

        # Status bar
        style.configure("Status.TLabel", background=C["bg"],
                        foreground=C["status_fg"], font=("Helvetica", 11))

        # Combobox
        style.configure("TCombobox", fieldbackground=C["input_bg"],
                        foreground=C["input_fg"], font=("Helvetica", 12))

        # Checkbutton
        style.configure("TCheckbutton", background=C["bg"], foreground=C["fg"],
                        font=("Helvetica", 11))

    # ── Data loading ──────────────────────────────────────────

    def _load_catalogue_data(self):
        if not os.path.exists(self.catalogue_path):
            print(f"  ✗ Catalogue '{self.catalogue_path}' not found. Exiting.")
            sys.exit(1)
        self.catalogue = load_catalogue(self.catalogue_path)
        collect_all_values(self.catalogue)
        self.display_rows = catalogue_to_display_rows(self.catalogue)
        print(f"  ✓ Loaded {len(self.catalogue)} GMPEs from '{self.catalogue_path}'")

    def _load_existing_selection(self):
        sel = load_selection(self.selection_path)
        for ev in self.event_names:
            if ev in sel:
                self.selection[ev] = sel[ev]
        if any(self.selection.values()):
            print(f"  ✓ Loaded existing selection from '{self.selection_path}'")

    # ── UI construction ───────────────────────────────────────

    def _build_ui(self):
        # ── Top bar: event tabs ──
        top_frame = ttk.Frame(self.root, padding="6")
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="Event:", font=("Helvetica", 13, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        self.event_var = tk.StringVar(value=self.current_event)
        self.event_combo = ttk.Combobox(
            top_frame, textvariable=self.event_var, values=self.event_names,
            state="readonly", width=16, font=("Helvetica", 13)
        )
        self.event_combo.pack(side=tk.LEFT)
        self.event_combo.bind("<<ComboboxSelected>>", self._on_event_change)

        ttk.Label(top_frame, text="  Catalogue:", font=("Helvetica", 11)).pack(side=tk.LEFT, padx=(12, 2))
        ttk.Label(top_frame, text=os.path.basename(self.catalogue_path),
                  font=("Helvetica", 11), foreground="gray").pack(side=tk.LEFT)

        ttk.Label(top_frame, text="  GMPEs loaded:", font=("Helvetica", 11)).pack(side=tk.LEFT, padx=(12, 2))
        self.lbl_count = ttk.Label(top_frame, text=str(len(self.catalogue)),
                                   font=("Helvetica", 11), foreground="gray")
        self.lbl_count.pack(side=tk.LEFT)

        # ── Main pane: filters (left) + GMPE list (right) ──
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # ── Left panel: Filters ──
        filter_frame = ttk.LabelFrame(main_pane, text=" Filters ", padding="8")
        main_pane.add(filter_frame, weight=0)
        self._build_filter_panel(filter_frame)

        # ── Right panel: GMPE list ──
        list_frame = ttk.LabelFrame(main_pane, text=" GMPE Catalogue ", padding="8")
        main_pane.add(list_frame, weight=1)
        self._build_list_panel(list_frame)

        # ── Bottom bar: status & actions ──
        self._build_bottom_bar()

    def _build_filter_panel(self, parent):
        # Make it scrollable — wider to fit two columns
        canvas = tk.Canvas(parent, width=420, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind mousewheel / trackpad
        def _on_mousewheel(event):
            if not canvas.winfo_exists():
                return
            # macOS trackpad: small delta; Windows/Linux: ±120
            if _pltfrm.system() == "Linux" and not hasattr(event, 'delta'):
                return  # handled by Button-4/Button-5
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-3, "units")
                         if canvas.winfo_exists() else None, add="+")
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(3, "units")
                         if canvas.winfo_exists() else None, add="+")
        canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")

        # Configure 2-column grid for the scroll_frame
        scroll_frame.grid_columnconfigure(0, weight=1, uniform="col")
        scroll_frame.grid_columnconfigure(1, weight=1, uniform="col")

        # ── Year range (spans both columns at top) ──
        yr_frame = ttk.LabelFrame(scroll_frame, text=" Year Range ", padding="4")
        yr_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=3, pady=3)
        row = ttk.Frame(yr_frame)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Min:").pack(side=tk.LEFT)
        self.yr_min_var = tk.StringVar(value="2014")
        self.yr_min_var.trace_add("write", lambda *a: self._auto_apply())
        ttk.Entry(row, textvariable=self.yr_min_var, width=8, font=("Helvetica", 11)).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text="Max:").pack(side=tk.LEFT, padx=(8, 0))
        self.yr_max_var = tk.StringVar(value="")
        self.yr_max_var.trace_add("write", lambda *a: self._auto_apply())
        ttk.Entry(row, textvariable=self.yr_max_var, width=8, font=("Helvetica", 11)).pack(side=tk.LEFT, padx=4)

        # ── Column 0: Source / Rupture parameters ──
        # Tectonic Region
        reg_frame = ttk.LabelFrame(scroll_frame, text=" Tectonic Region ", padding="4")
        reg_frame.grid(row=1, column=0, sticky="nsew", padx=3, pady=3)
        self.region_vars = {}
        for reg in sorted(ALL_REGIONS):
            v = tk.BooleanVar(value=(reg in ["Active Shallow Crust", "Stable Shallow Crust"]))
            v.trace_add("write", lambda *a: self._auto_apply())
            cb = ttk.Checkbutton(reg_frame, text=reg, variable=v)
            cb.pack(anchor=tk.W, padx=6)
            self.region_vars[reg] = v

        # Required Rupture Parameters
        rupt_frame = ttk.LabelFrame(scroll_frame, text=" Required Rupture Parameters ", padding="4")
        rupt_frame.grid(row=2, column=0, sticky="nsew", padx=3, pady=3)
        self.rupt_vars = {}
        for r in sorted(ALL_RUPTURES):
            v = tk.BooleanVar(value=False)
            v.trace_add("write", lambda *a: self._auto_apply())
            cb = ttk.Checkbutton(rupt_frame, text=r, variable=v)
            cb.pack(anchor=tk.W, padx=6)
            self.rupt_vars[r] = v

        # ── Column 1: Path / Site / Intensity Measure parameters ──
        # Required Distances
        dist_frame = ttk.LabelFrame(scroll_frame, text=" Required Distances (any) ", padding="4")
        dist_frame.grid(row=1, column=1, sticky="nsew", padx=3, pady=3)
        self.dist_vars = {}
        for d in sorted(ALL_DISTANCES):
            v = tk.BooleanVar(value=(d in ["rjb", "rhypo", "rrup"]))
            v.trace_add("write", lambda *a: self._auto_apply())
            cb = ttk.Checkbutton(dist_frame, text=d, variable=v)
            cb.pack(anchor=tk.W, padx=6)
            self.dist_vars[d] = v

        # Required Site Parameters (2 columns)
        site_frame = ttk.LabelFrame(scroll_frame, text=" Required Site Parameters (all) ", padding="4")
        site_frame.grid(row=2, column=1, sticky="nsew", padx=3, pady=3)
        site_inner = ttk.Frame(site_frame)
        site_inner.pack(fill=tk.X, padx=2)
        self.site_vars = {}
        for i, s in enumerate(sorted(ALL_SITES)):
            v = tk.BooleanVar(value=(s == "vs30"))
            v.trace_add("write", lambda *a: self._auto_apply())
            cb = ttk.Checkbutton(site_inner, text=s, variable=v)
            cb.grid(row=i//2, column=i%2, sticky=tk.W, padx=6, pady=1)
            self.site_vars[s] = v
        site_inner.grid_columnconfigure(0, weight=1)
        site_inner.grid_columnconfigure(1, weight=1)

        # IMT Types (2 columns)
        imt_frame = ttk.LabelFrame(scroll_frame, text=" IMT Types (all) ", padding="4")
        imt_frame.grid(row=3, column=0, sticky="nsew", padx=3, pady=3)
        imt_inner = ttk.Frame(imt_frame)
        imt_inner.pack(fill=tk.X, padx=2)
        self.imt_vars = {}
        for i, imt in enumerate(sorted(ALL_IMTS)):
            v = tk.BooleanVar(value=(imt in ["SA", "PGA", "PGV"]))
            v.trace_add("write", lambda *a: self._auto_apply())
            cb = ttk.Checkbutton(imt_inner, text=imt, variable=v)
            cb.grid(row=i//2, column=i%2, sticky=tk.W, padx=6, pady=1)
            self.imt_vars[imt] = v
        imt_inner.grid_columnconfigure(0, weight=1)
        imt_inner.grid_columnconfigure(1, weight=1)

        # Standard Deviation Types
        std_frame = ttk.LabelFrame(scroll_frame, text=" Standard Deviation Types (all) ", padding="4")
        std_frame.grid(row=3, column=1, sticky="nsew", padx=3, pady=3)
        self.std_vars = {}
        for s in sorted(ALL_STDS):
            v = tk.BooleanVar(value=(s == "Total"))
            v.trace_add("write", lambda *a: self._auto_apply())
            cb = ttk.Checkbutton(std_frame, text=s, variable=v)
            cb.pack(anchor=tk.W, padx=6)
            self.std_vars[s] = v

        # ── Filter buttons (span both columns) ──
        btn_frame = ttk.Frame(scroll_frame)
        btn_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=3, pady=6)
        ttk.Button(btn_frame, text="↺  Reset Filters",
                   command=self._reset_filters).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="🔄  Refresh Catalogue",
                   command=self._refresh_catalogue).pack(fill=tk.X, pady=2)
        # (Interactive Review removed)

    def _build_list_panel(self, parent):
        # ── Top: summary bar ──
        top_row = ttk.Frame(parent)
        top_row.pack(fill=tk.X)

        self.lbl_match_count = ttk.Label(top_row, text="0 GMPEs available",
                                         font=("Helvetica", 13, "bold"))
        self.lbl_match_count.pack(side=tk.LEFT)

        self.lbl_sel_count = ttk.Label(top_row, text="  |  0 selected",
                                       font=("Helvetica", 12))
        self.lbl_sel_count.pack(side=tk.LEFT, padx=8)

        # ── Vertical PanedWindow (transfer area + detail) ──
        self.detail_pane = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        self.detail_pane.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        # ── Dual-pane transfer area (first pane of detail_pane) ──
        transfer_frame = ttk.Frame(self.detail_pane)
        self.detail_pane.add(transfer_frame, weight=1)

        # ─── Left: Available GMPEs ────────────────────────────
        left_frame = ttk.LabelFrame(transfer_frame, text=" Available GMPEs ", padding="2")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 2))

        # Search within available
        search_row = ttk.Frame(left_frame)
        search_row.pack(fill=tk.X)
        ttk.Label(search_row, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._refresh_available_list())
        ent = ttk.Entry(search_row, textvariable=self.search_var, width=20, font=("Helvetica", 11))
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        # Available tree
        av_tree_frame = ttk.Frame(left_frame)
        av_tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("code", "name", "year", "region")
        self.av_tree = ttk.Treeview(av_tree_frame, columns=columns, show="headings",
                                    height=20, selectmode="extended")
        self.av_tree.heading("code", text="Code")
        self.av_tree.heading("name", text="Full Name")
        self.av_tree.heading("year", text="Year")
        self.av_tree.heading("region", text="Region")
        self.av_tree.column("code", width=80, anchor=tk.W)
        self.av_tree.column("name", width=220, anchor=tk.W)
        self.av_tree.column("year", width=45, anchor=tk.CENTER)
        self.av_tree.column("region", width=140, anchor=tk.W)

        av_vsb = ttk.Scrollbar(av_tree_frame, orient=tk.VERTICAL, command=self.av_tree.yview)
        av_hsb = ttk.Scrollbar(av_tree_frame, orient=tk.HORIZONTAL, command=self.av_tree.xview)
        self.av_tree.configure(yscrollcommand=av_vsb.set, xscrollcommand=av_hsb.set)
        self.av_tree.grid(row=0, column=0, sticky="nsew")
        av_vsb.grid(row=0, column=1, sticky="ns")
        av_hsb.grid(row=1, column=0, sticky="ew")
        av_tree_frame.grid_rowconfigure(0, weight=1)
        av_tree_frame.grid_columnconfigure(0, weight=1)

        self.av_tree.bind("<<TreeviewSelect>>", lambda e: self._on_av_tree_select())
        self.av_tree.bind("<Double-Button-1>", lambda e: self._move_selected_to_selected())
        # Right-click context menu for available
        self.av_tree.bind("<Button-3>", lambda e: self._on_av_context_menu(e))

        # ─── Center: Arrow buttons ────────────────────────────
        ctrl_frame = ttk.Frame(transfer_frame)
        ctrl_frame.grid(row=0, column=1, sticky="ns")

        # Spacer
        ctrl_frame.grid_rowconfigure(0, weight=1)

        ttk.Button(ctrl_frame, text="  →  ", width=6,
                   command=self._move_selected_to_selected).grid(row=1, column=0, pady=2)
        ttk.Button(ctrl_frame, text="  ←  ", width=6,
                   command=self._move_selected_to_available).grid(row=2, column=0, pady=2)
        # Double-arrow buttons (→→ / ←←) removed — uncomment to restore:
        # ttk.Button(ctrl_frame, text=" →→ ", width=6,
        #            command=self._move_all_to_selected).grid(row=3, column=0, pady=2)
        # ttk.Button(ctrl_frame, text=" ←← ", width=6,
        #            command=self._move_all_to_available).grid(row=4, column=0, pady=2)
        ttk.Label(ctrl_frame, text="Add by\nname:").grid(row=3, column=0, pady=(12, 2))
        self.add_entry_var = tk.StringVar()
        ttk.Entry(ctrl_frame, textvariable=self.add_entry_var, width=10).grid(row=4, column=0, padx=2)
        ttk.Button(ctrl_frame, text="Add", width=6,
                   command=self._add_by_name).grid(row=5, column=0, pady=2)

        ctrl_frame.grid_rowconfigure(6, weight=1)

        # ─── Right: Selected GMPEs ────────────────────────────
        right_frame = ttk.LabelFrame(transfer_frame, text=" Selected GMPEs ", padding="2")
        right_frame.grid(row=0, column=2, sticky="nsew", padx=(2, 0))

        # Selected count
        self.lbl_sel_count_right = ttk.Label(right_frame, text="0 selected",
                                             font=("Helvetica", 11, "bold"))
        self.lbl_sel_count_right.pack(anchor=tk.W)

        # Selected tree
        sel_tree_frame = ttk.Frame(right_frame)
        sel_tree_frame.pack(fill=tk.BOTH, expand=True)
        self.sel_tree = ttk.Treeview(sel_tree_frame, columns=columns, show="headings",
                                     height=20, selectmode="extended")
        self.sel_tree.heading("code", text="Code")
        self.sel_tree.heading("name", text="Full Name")
        self.sel_tree.heading("year", text="Year")
        self.sel_tree.heading("region", text="Region")
        self.sel_tree.column("code", width=80, anchor=tk.W)
        self.sel_tree.column("name", width=220, anchor=tk.W)
        self.sel_tree.column("year", width=45, anchor=tk.CENTER)
        self.sel_tree.column("region", width=140, anchor=tk.W)

        sel_vsb = ttk.Scrollbar(sel_tree_frame, orient=tk.VERTICAL, command=self.sel_tree.yview)
        sel_hsb = ttk.Scrollbar(sel_tree_frame, orient=tk.HORIZONTAL, command=self.sel_tree.xview)
        self.sel_tree.configure(yscrollcommand=sel_vsb.set, xscrollcommand=sel_hsb.set)
        self.sel_tree.grid(row=0, column=0, sticky="nsew")
        sel_vsb.grid(row=0, column=1, sticky="ns")
        sel_hsb.grid(row=1, column=0, sticky="ew")
        sel_tree_frame.grid_rowconfigure(0, weight=1)
        sel_tree_frame.grid_columnconfigure(0, weight=1)

        self.sel_tree.bind("<<TreeviewSelect>>", lambda e: self._on_sel_tree_select())
        self.sel_tree.bind("<Double-Button-1>", lambda e: self._move_selected_to_available())
        # Right-click context menu for selected
        self.sel_tree.bind("<Button-3>", lambda e: self._on_sel_context_menu(e))

        # Grid weights for transfer frame
        transfer_frame.grid_columnconfigure(0, weight=1)
        transfer_frame.grid_columnconfigure(1, weight=0)
        transfer_frame.grid_columnconfigure(2, weight=1)
        transfer_frame.grid_rowconfigure(0, weight=1)

        # Detail frame (second pane of detail_pane)
        detail_frame = ttk.LabelFrame(self.detail_pane, text=" GMPE Details ", padding="4")
        self.detail_pane.add(detail_frame, weight=0)

        # Text widget for details, with a resize grip inside
        text_pad = ttk.Frame(detail_frame)
        text_pad.pack(fill=tk.BOTH, expand=True)

        self.detail_text = tk.Text(text_pad, height=8, wrap=tk.WORD,
                                   font=("Helvetica", 13),
                                   foreground=COLORS["fg"],
                                   background=COLORS["input_bg"],
                                   padx=8, pady=6)
        self.detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        detail_scroll = ttk.Scrollbar(text_pad, orient=tk.VERTICAL,
                                       command=self.detail_text.yview)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.detail_text.configure(yscrollcommand=detail_scroll.set)

        self.detail_text.insert(tk.END, "Click on a GMPE in either list to see details")
        self.detail_text.config(state=tk.DISABLED)

        # Size grip at bottom-right of the detail pane
        self.detail_sizegrip = ttk.Sizegrip(detail_frame)
        self.detail_sizegrip.pack(side=tk.BOTTOM, anchor=tk.SE)

    def _build_bottom_bar(self):
        bar = ttk.Frame(self.root, padding="4")
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(bar, text="💾  Save Selection",
                   command=self._save_selection).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="📂  Load Selection",
                   command=self._load_selection_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="📁  Load From File…",
                   command=self._load_from_file_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="❌  Clear All Selections",
                   command=self._clear_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="📊  Plot GMPE Spectra",
                   command=self._plot_gmpe_spectra).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="🔙  Wizard",
                   command=self._rerun_wizard).pack(side=tk.LEFT, padx=2)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.status_var, style="Status.TLabel").pack(side=tk.RIGHT, padx=8)

        # Keyboard shortcuts
        self.root.bind("<Control-s>", lambda e: self._save_selection())
        self.root.bind("<Control-l>", lambda e: self._load_selection_dialog())

    # ── Filter logic ──────────────────────────────────────────

    def _get_active_filters(self):
        """Return a filters dict from the current UI state."""
        filters = {}

        # Year
        yr_min = self.yr_min_var.get().strip()
        yr_max = self.yr_max_var.get().strip()
        if yr_min:
            try:
                filters["year_min"] = int(yr_min)
            except ValueError:
                pass
        if yr_max:
            try:
                filters["year_max"] = int(yr_max)
            except ValueError:
                pass

        # Region
        selected_regions = [r for r, v in self.region_vars.items() if v.get()]
        if selected_regions:
            filters["region"] = selected_regions

        # Distance (any)
        selected_dists = [d for d, v in self.dist_vars.items() if v.get()]
        if selected_dists:
            filters["dist_any"] = selected_dists

        # Site (all)
        selected_sites = [s for s, v in self.site_vars.items() if v.get()]
        if selected_sites:
            filters["site_all"] = selected_sites

        # Rupture
        selected_rupts = [r for r, v in self.rupt_vars.items() if v.get()]
        if selected_rupts:
            filters["rupt_all"] = selected_rupts

        # IMT (all)
        selected_imts = [i for i, v in self.imt_vars.items() if v.get()]
        if selected_imts:
            filters["imt_all"] = selected_imts

        # Std Dev (all)
        selected_stds = [s for s, v in self.std_vars.items() if v.get()]
        if selected_stds:
            filters["std_all"] = selected_stds

        return filters

    def _apply_filters(self):
        """Apply current filters and refresh the list."""
        filters = self._get_active_filters()
        event = self.current_event

        matched = []
        for row in self.display_rows:
            ok = True
            name = row["name"]
            yr = next((r["Year"] for r in self.catalogue if r["GMPE"] == name), 0)

            # Year
            if "year_min" in filters and yr < filters["year_min"]:
                ok = False
            if "year_max" in filters and yr > filters["year_max"]:
                ok = False

            # Region (substring match)
            if ok and "region" in filters:
                cat_row = next((r for r in self.catalogue if r["GMPE"] == name), None)
                if cat_row:
                    region_text = cat_row["TectonicRegion"]
                    ok = any(r.lower() in region_text.lower() for r in filters["region"])

            # Distance (any)
            if ok and "dist_any" in filters:
                if not row["_dist_set"].intersection(filters["dist_any"]):
                    ok = False

            # Site (all)
            if ok and "site_all" in filters:
                if not row["_site_set"].issuperset(filters["site_all"]):
                    ok = False

            # Rupture (all)
            if ok and "rupt_all" in filters:
                if not row["_rupt_set"].issuperset(filters["rupt_all"]):
                    ok = False

            # IMT (all)
            if ok and "imt_all" in filters:
                if not row["_imt_set"].issuperset(filters["imt_all"]):
                    ok = False

            # Std Dev (all)
            if ok and "std_all" in filters:
                if not row["_std_set"].issuperset(filters["std_all"]):
                    ok = False

            if ok:
                matched.append(row)

        self._matched_rows = matched
        self._refresh_both_lists()
        self.status_var.set(f"Filters applied — {len(matched)} matches for [{event}]")

    def _reset_filters(self):
        """Reset all filters to blank and clear all selections."""
        self.yr_min_var.set("")
        self.yr_max_var.set("")

        for v in self.region_vars.values():
            v.set(False)

        for v in self.dist_vars.values():
            v.set(False)

        for v in self.site_vars.values():
            v.set(False)

        for v in self.rupt_vars.values():
            v.set(False)

        for v in self.imt_vars.values():
            v.set(False)

        for v in self.std_vars.values():
            v.set(False)

        self.search_var.set("")
        self.add_entry_var.set("")

        # Clear all selected GMPEs
        for ev in self.event_names:
            self.selection[ev] = set()

        self._apply_filters()
        self.status_var.set("Filters & selection cleared")

    def _refresh_catalogue(self):
        """Reload the catalogue CSV from disk and re-apply filters."""
        import tkinter.messagebox as mb
        try:
            self._load_catalogue_data()
            self._apply_filters()
            self.lbl_count.config(text=str(len(self.catalogue)))
            self.status_var.set(f"🔄 Catalogue reloaded — {len(self.catalogue)} GMPEs")
        except Exception as e:
            mb.showerror("Error", f"Failed to reload catalogue:\n{e}")
            self.status_var.set("⚠ Catalogue reload failed")

    # ── Auto-apply (debounced) ────────────────────────────────

    def _auto_apply(self):
        """Called automatically when any filter parameter changes."""
        # Guard: trees might not exist yet during UI construction
        if not hasattr(self, 'av_tree') or not self.av_tree:
            return
        # Cancel any pending auto-apply
        if self._auto_apply_after_id:
            self.root.after_cancel(self._auto_apply_after_id)
        # Schedule a new one (debounce 200ms)
        self._auto_apply_after_id = self.root.after(200, self._apply_filters)

    # ── Dual-pane refresh ─────────────────────────────────────

    def _refresh_available_list(self):
        """Refresh the available (left) treeview with filtered, unselected GMPEs."""
        for item in self.av_tree.get_children():
            self.av_tree.delete(item)

        search = self.search_var.get().strip().lower()
        event = self.current_event
        sel_names = self.selection.get(event, set())

        count = 0
        for row in self._matched_rows:
            if row["name"] in sel_names:
                continue  # already selected, not available
            name = row["name"].lower()
            code = row["code"].lower()
            if search and search not in name and search not in code:
                continue
            self.av_tree.insert("", tk.END, values=(
                row["code"], row["name"], str(row["year"]), row["region"]
            ))
            count += 1

        self.lbl_match_count.config(text=f"{count} GMPEs available")

    def _refresh_selected_list(self):
        """Refresh the selected (right) treeview."""
        for item in self.sel_tree.get_children():
            self.sel_tree.delete(item)

        event = self.current_event
        sel_names = self.selection.get(event, set())

        for name in sorted(sel_names):
            # Find the row data
            row = next((r for r in self.display_rows if r["name"] == name), None)
            if row is None:
                continue
            self.sel_tree.insert("", tk.END, values=(
                row["code"], row["name"], str(row["year"]), row["region"]
            ))

        self.lbl_sel_count.config(text=f"  |  {len(sel_names)} selected")
        self.lbl_sel_count_right.config(text=f"{len(sel_names)} selected")

    def _refresh_both_lists(self):
        """Refresh both available and selected lists."""
        self._refresh_available_list()
        self._refresh_selected_list()

    # ── Transfer operations ───────────────────────────────────

    def _move_selected_to_selected(self):
        """Move selected items from available (left) to selected (right)."""
        event = self.current_event
        sel_items = self.av_tree.selection()
        if not sel_items:
            return
        for item in sel_items:
            values = self.av_tree.item(item, "values")
            name = values[1]
            self.selection[event].add(name)
        self._refresh_both_lists()
        self.status_var.set(f"Moved {len(sel_items)} GMPE(s) to selected")

    def _move_selected_to_available(self):
        """Move selected items from selected (right) to available (left)."""
        event = self.current_event
        sel_items = self.sel_tree.selection()
        if not sel_items:
            return
        for item in sel_items:
            values = self.sel_tree.item(item, "values")
            name = values[1]
            self.selection[event].discard(name)
        self._refresh_both_lists()
        self.status_var.set(f"Moved {len(sel_items)} GMPE(s) back to available")

    def _move_all_to_selected(self):
        """Move all available GMPEs to selected."""
        event = self.current_event
        names = set()
        for item in self.av_tree.get_children():
            values = self.av_tree.item(item, "values")
            names.add(values[1])
        if not names:
            return
        self.selection[event] |= names
        self._refresh_both_lists()
        self.status_var.set(f"Moved all {len(names)} GMPE(s) to selected")

    def _move_all_to_available(self):
        """Move all selected GMPEs back to available."""
        event = self.current_event
        names = set()
        for item in self.sel_tree.get_children():
            values = self.sel_tree.item(item, "values")
            names.add(values[1])
        if not names:
            return
        self.selection[event] -= names
        self._refresh_both_lists()
        self.status_var.set(f"Moved all {len(names)} GMPE(s) back to available")

    def _add_by_name(self):
        """Add a GMPE by name substring search (like 'a <name>' in terminal)."""
        search = self.add_entry_var.get().strip()
        if not search:
            return
        event = self.current_event
        found = 0
        for row in self.display_rows:
            if search.lower() in row["name"].lower() or search.lower() in row["code"].lower():
                if row["name"] not in self.selection[event]:
                    self.selection[event].add(row["name"])
                    found += 1
        if found:
            self._refresh_both_lists()
            self.status_var.set(f"Added {found} GMPE(s) matching '{search}'")
        else:
            self.status_var.set(f"⚠ No GMPE matches '{search}'")
        self.add_entry_var.set("")

    # ── Detail display ────────────────────────────────────────

    def _show_detail_for_name(self, name):
        """Show detail info for a given GMPE full name."""
        cat_row = next((r for r in self.catalogue if r["GMPE"] == name), None)
        if not cat_row:
            return
        code = cat_row.get("Shortcut", cat_row["Code"])
        year = cat_row["Year"]
        region = cat_row["TectonicRegion"]
        dists = " ".join(sorted(cat_row["RequiresDistances"]))
        sites = " ".join(sorted(cat_row["RequiresSites"]))
        rupt = " ".join(sorted(cat_row["RequiresRupture"]))
        imts = " ".join(sorted(cat_row["DefinedForIMTs"]))
        stds = " ".join(sorted(cat_row["DefinedForStdDevs"]))

        # Build a human-readable description from available metadata
        desc_parts = []

        # Tectonic context
        if region and region != "—":
            desc_parts.append(f"Ground-motion model for {region}")

        # Year context
        if year > 0:
            era = "modern" if year >= 2010 else "early"
            desc_parts.append(f"published in {year} ({era})")

        # Distance metrics
        if dists:
            dist_desc = {
                "rjb": "Joyner-Boore distance (Rjb)",
                "rrup": "closest distance to rupture (Rrup)",
                "rhypo": "hypocentral distance (Rhypo)",
                "repi": "epicentral distance (Repi)",
                "rx": "horizontal distance from top of rupture (Rx)",
                "ry0": "horizontal distance from surface projection (Ry0)",
                "rvolc": "distance to volcanic center",
                "rcdpp": "distance to CDPP",
                "clat": "latitude difference",
                "clon": "longitude difference",
                "azimuth": "azimuth",
            }
            known = [dist_desc.get(d, d) for d in sorted(cat_row["RequiresDistances"])]
            desc_parts.append(f"uses distance metric(s): {', '.join(known)}")

        # Site parameters
        if sites:
            site_desc = {
                "vs30": "Vs30 (time-averaged shear-wave velocity to 30m)",
                "vs30measured": "measured Vs30",
                "z1pt0": "depth to 1.0 km/s (z1)",
                "z1pt4": "depth to 1.4 km/s",
                "z2pt5": "depth to 2.5 km/s (z2.5)",
                "backarc": "back-arc vs fore-arc indicator",
            }
            known = [site_desc.get(s, s) for s in sorted(cat_row["RequiresSites"])]
            desc_parts.append(f"requires site parameters: {', '.join(known)}")

        # Rupture parameters
        if rupt:
            rupt_desc = {
                "mag": "magnitude",
                "rake": "rake angle",
                "dip": "dip angle",
                "ztor": "depth to top of rupture (Ztor)",
                "width": "rupture width",
                "hypo_depth": "hypocentral depth",
            }
            known = [rupt_desc.get(r, r) for r in sorted(cat_row["RequiresRupture"])]
            desc_parts.append(f"uses rupture parameters: {', '.join(known)}")

        # IMTs
        if imts:
            imt_desc = {
                "SA": "spectral acceleration (SA)",
                "PGA": "peak ground acceleration (PGA)",
                "PGV": "peak ground velocity (PGV)",
                "PGD": "peak ground displacement (PGD)",
                "CAV": "cumulative absolute velocity (CAV)",
                "IA": "Arias intensity (Ia)",
                "MMI": "modified Mercalli intensity (MMI)",
                "FAS": "Fourier amplitude spectrum",
                "EAS": "effective amplitude spectrum",
                "SDI": "spectral duration index",
            }
            known = [imt_desc.get(i, i) for i in sorted(cat_row["DefinedForIMTs"])]
            desc_parts.append(f"defines intensity measures: {', '.join(known)}")

        # Std devs
        if stds:
            std_desc = {
                "Total": "total standard deviation",
                "Inter event": "inter-event (between-event) sigma",
                "Intra event": "intra-event (within-event) sigma",
                "Inter": "inter-event sigma",
                "Intra": "intra-event sigma",
                "event": "event-term sigma",
            }
            known = [std_desc.get(s, s) for s in sorted(cat_row["DefinedForStdDevs"])]
            desc_parts.append(f"provides standard deviation types: {', '.join(known)}")

        # Short code explanation
        code_parts = []
        if "EtAl" in name:
            author = name.split("EtAl")[0]
            code_parts.append(f"first author: {author} et al.")
        else:
            authors = re.findall(r'[A-Z][a-z]*', name.split("19")[0].split("20")[0])
            if authors:
                code_parts.append(f"authors: {', '.join(authors)}")
        if year > 0:
            # Extract suffix after year
            m = re.search(r"\d{4}", name)
            if m:
                suffix = name[m.end():]
                if suffix:
                    code_parts.append(f"variant: {suffix}")
        if code_parts:
            desc_parts.append(f"code breakdown — {'; '.join(code_parts)}")

        # Compose full description
        if desc_parts:
            description = " · ".join(desc_parts)
        else:
            description = "No additional metadata available."

        # Fetch OpenQuake docstring — try direct OQ import first, then CSV fallback
        oq_display_long = None
        try:
            from openquake.hazardlib import gsim as _oq_gsim
            _oq_cls = _oq_gsim.get_available_gsims().get(name)
            if _oq_cls is not None:
                _doc = (_oq_cls.__doc__ or "").strip()
                if _doc:
                    _para = _doc.split("\n\n")[0] if "\n\n" in _doc else _doc
                    _lines = [l.strip() for l in _para.split("\n") if l.strip()]
                    _short_desc = " ".join(_lines).replace("\t", " ")
                    if len(_short_desc) > 2000:
                        _short_desc = _short_desc[:1997] + "..."
                    oq_display_long = _short_desc[:1000] + "…" if len(_short_desc) > 1000 else _short_desc
        except Exception:
            pass
        if oq_display_long is None:
            oq_doc = cat_row.get("Description", "").strip()
            if oq_doc:
                oq_display_long = oq_doc[:1000] + "…" if len(oq_doc) > 1000 else oq_doc

        detail = ""
        if oq_display_long:
            detail += f"📘 {oq_display_long}\n\n"
        detail += (
            f"📌 [{code}] {name}\n"
            f"{'=' * 60}\n"
            f"   Year: {year}  |  Region: {region}\n"
            f"   Distances: {dists}\n"
            f"   Sites:      {sites}\n"
            f"   Rupture:    {rupt}\n"
            f"   IMTs:       {imts}\n"
            f"   StdDevs:    {stds}\n"
            f"{'=' * 60}\n"
            f"📖 {description}\n"
        )
        self.detail_text.config(state=tk.NORMAL)
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert(tk.END, detail)
        self.detail_text.config(state=tk.DISABLED)

    def _on_av_tree_select(self):
        """Show details for the selected available GMPE."""
        sel = self.av_tree.selection()
        if not sel:
            return
        values = self.av_tree.item(sel[0], "values")
        self._show_detail_for_name(values[1])

    def _on_sel_tree_select(self):
        """Show details for the selected (right) GMPE."""
        sel = self.sel_tree.selection()
        if not sel:
            return
        values = self.sel_tree.item(sel[0], "values")
        self._show_detail_for_name(values[1])

    # ── Context menus ─────────────────────────────────────────

    def _on_av_context_menu(self, event):
        item = self.av_tree.identify_row(event.y)
        if not item:
            return
        self.av_tree.selection_set(item)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="→  Select (move right)", command=self._move_selected_to_selected)
        menu.add_command(label="→→  Select All", command=self._move_all_to_selected)
        menu.add_separator()
        menu.add_command(label="📋 Copy Name",
                         command=lambda: self._copy_from_tree(self.av_tree, 1))
        menu.add_command(label="📋 Copy Code",
                         command=lambda: self._copy_from_tree(self.av_tree, 0))
        menu.post(event.x_root, event.y_root)

    def _on_sel_context_menu(self, event):
        item = self.sel_tree.identify_row(event.y)
        if not item:
            return
        self.sel_tree.selection_set(item)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="←  Deselect (move left)", command=self._move_selected_to_available)
        menu.add_command(label="←←  Deselect All", command=self._move_all_to_available)
        menu.add_separator()
        menu.add_command(label="📋 Copy Name",
                         command=lambda: self._copy_from_tree(self.sel_tree, 1))
        menu.add_command(label="📋 Copy Code",
                         command=lambda: self._copy_from_tree(self.sel_tree, 0))
        menu.post(event.x_root, event.y_root)

    def _copy_from_tree(self, tree, col_idx):
        sel = tree.selection()
        if sel:
            values = tree.item(sel[0], "values")
            self.root.clipboard_clear()
            self.root.clipboard_append(values[col_idx])
            self.status_var.set(f"Copied: {values[col_idx]}")

    # ── Event switching ───────────────────────────────────────

    def _on_event_change(self, event=None):
        self.current_event = self.event_var.get()
        self._refresh_both_lists()
        self.status_var.set(f"Switched to [{self.current_event}]")

    # ── Save / Load ───────────────────────────────────────────

    def _save_selection(self, path=None):
        """Save current selection to JSON.  If path is None, ask via dialog."""
        if not any(self.selection.values()):
            messagebox.showwarning("Empty Selection", "No GMPEs selected for any event.")
            return

        if path is None:
            from tkinter import filedialog
            # Ask: create a new file or append to an existing one?
            add_to_existing = messagebox.askyesno(
                title="Save Mode",
                message="Do you want to add this selection to an existing file?\n\n"
                        "  • Yes  → Pick an existing JSON file to append to\n"
                        "  • No   → Create a new file"
            )
            if add_to_existing:
                existing_path = filedialog.askopenfilename(
                    title="Add to existing GMPE Selection",
                    initialdir=".",
                    filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
                )
                if not existing_path:
                    return
                self._merge_into_file(existing_path)
                return
            else:
                # Suggest a filename based on the project / event name
                first_ev = self.event_names[0] if self.event_names else ""
                if first_ev and first_ev not in ("HF_SMS", "LF_SMS"):
                    safe = first_ev.replace(" ", "_").replace("/", "_")
                    suggested = f"{safe}_selection.json"
                else:
                    suggested = self.selection_path
                path = filedialog.asksaveasfilename(
                    title="Save GMPE Selection",
                    initialdir=".",
                    initialfile=suggested,
                    defaultextension=".json",
                    filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
                )
                if not path:
                    return  # user cancelled

        # Build a name→catalogue mapping
        name_map = {r["GMPE"]: r for r in self.catalogue}
        # If the guided questionnaire provided an event name, use it as the
        # single JSON key (instead of HF_SMS / LF_SMS).
        evt_name = None
        if self._guided_filters:
            evt_name = self._guided_filters.get("event_name", "").strip()
        save_selection(path, self.selection, name_map, event_name=evt_name or None)
        self.selection_path = path
        self.status_var.set(f"💾 Saved selection to '{os.path.basename(path)}'")
        messagebox.showinfo("Saved", f"Selection saved to:\n{os.path.abspath(path)}")

    def _merge_into_file(self, existing_path):
        """Append current selection as a new project field into an existing JSON file.

        The existing file's data is preserved as-is; a new key is added with the
        project / event name and the currently selected GMPEs.
        """
        import json, os

        with open(existing_path) as f:
            existing_data = json.load(f)

        # Determine the project name for the new field
        project_name = None
        if self._guided_filters:
            project_name = self._guided_filters.get("event_name", "").strip()
        if not project_name:
            # Fall back to the first event name in the dropdown
            project_name = self.event_names[0] if self.event_names else "project"

        # Build the list of [code, fullname] pairs from the current selection
        all_names = set()
        for names in self.selection.values():
            all_names.update(names)
        new_pairs = []
        for n in sorted(all_names):
            new_pairs.append([make_gmpe_code(n), n])

        # Add the new field — it may overwrite an existing key with the same name
        existing_data[project_name] = new_pairs

        # Write back
        with open(existing_path, "w") as f:
            json.dump(existing_data, f, indent=2)

        self.selection_path = existing_path
        self.status_var.set(f"💾 Appended selection as '{project_name}' in '{os.path.basename(existing_path)}'")
        messagebox.showinfo("Saved", f"Selection appended as '{project_name}' to:\n{os.path.abspath(existing_path)}")

    def _load_selection_dialog(self):
        """Load a selection from a user-chosen JSON file."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Load GMPE Selection",
            initialdir=".",
            initialfile=self.selection_path,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        # Read raw data to preserve original key names
        with open(path) as _f:
            _raw_data = json.load(_f)
        _raw_keys = list(_raw_data.keys())
        sel = load_selection(path)
        if sel:
            self._set_event_names(_raw_keys)
            # Populate from raw data so keys match self.event_names
            for ev in self.event_names:
                pairs = _raw_data.get(ev, [])
                names = set()
                for it in pairs:
                    names.add(it[1] if isinstance(it, list) else it)
                self.selection[ev] = names
            self._refresh_both_lists()
            self.selection_path = path
            self.status_var.set(f"📂 Loaded selection from '{os.path.basename(path)}'")
        else:
            messagebox.showwarning("Empty", "No GMPE selections found in that file.")

    def _load_from_file_dialog(self):
        """Load a selection from a user-chosen JSON file."""
        path = filedialog.askopenfilename(
            title="Load GMPE Selection",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        # Read raw data to preserve original key names
        with open(path) as _f:
            _raw_data = json.load(_f)
        _raw_keys = list(_raw_data.keys())
        sel = load_selection(path)
        if sel:
            self._set_event_names(_raw_keys)
            # Populate from raw data so keys match self.event_names
            for ev in self.event_names:
                pairs = _raw_data.get(ev, [])
                names = set()
                for it in pairs:
                    names.add(it[1] if isinstance(it, list) else it)
                self.selection[ev] = names
            self._refresh_both_lists()
            self.status_var.set(f"📂 Loaded selection from '{os.path.basename(path)}'")
        else:
            messagebox.showwarning("Empty", "No GMPE selections found in that file.")

    def _set_event_names(self, new_names):
        """Update the event list and rebuild the selection dict accordingly."""
        if list(new_names) == self.event_names:
            return  # no change
        old_sel = self.selection
        self.event_names = list(new_names)
        self.selection = {ev: set() for ev in self.event_names}
        # Carry over any existing data for keys that still match
        for ev in self.event_names:
            if ev in old_sel:
                self.selection[ev] = old_sel[ev]
        if self.current_event not in self.event_names:
            self.current_event = self.event_names[0] if self.event_names else ""
        # Update the combobox if it already exists
        if hasattr(self, 'event_combo') and self.event_combo:
            self.event_combo['values'] = self.event_names
            self.event_var.set(self.current_event)

    def _rerun_wizard(self):
        """Re‑open the startup wizard to re‑load / re‑select GMPEs."""
        wizard_result = self._show_startup_wizard(
            catalogue=self.catalogue, display_rows=self.display_rows
        )
        wizard_action = wizard_result.get("action", "fresh")
        guided_filters = wizard_result.get("filters")
        loaded_sel = wizard_result.get("selection")
        remove_names = wizard_result.get("remove_names", set())

        if wizard_action == "load" and loaded_sel:
            raw_data = wizard_result.get("selection_raw_data") or {}
            raw_keys = wizard_result.get("selection_keys")
            if raw_keys:
                self._set_event_names(raw_keys)
                for ev in self.event_names:
                    pairs = raw_data.get(ev, [])
                    names = set()
                    for it in pairs:
                        names.add(it[1] if isinstance(it, list) else it)
                    self.selection[ev] = names
            else:
                self._set_event_names(list(loaded_sel.keys()))
                for ev in self.event_names:
                    if ev in loaded_sel:
                        self.selection[ev] = loaded_sel[ev]
            if "selection_path" in wizard_result:
                self.selection_path = wizard_result["selection_path"]
            self._refresh_both_lists()
            self.status_var.set("📂 Loaded selection from file via wizard")
            print("  ✓ Re‑loaded selection from file via wizard")

        elif wizard_action == "review":
            self._guided_filters = guided_filters
            if guided_filters:
                evt_name = guided_filters.get("event_name", "").strip()
                if evt_name:
                    safe = evt_name.replace(" ", "_").replace("/", "_")
                    self.selection_path = f"{safe}_selection.json"
                    self._set_event_names([evt_name])
                self._apply_guided_filters(guided_filters)
            if remove_names:
                for ev in self.event_names:
                    self.selection[ev] -= remove_names
            # Re‑apply filters and populate
            self._apply_filters()
            if hasattr(self, '_matched_rows') and self._matched_rows:
                matched_names = {row["name"] for row in self._matched_rows}
                if remove_names:
                    matched_names -= remove_names
                for ev in self.event_names:
                    self.selection[ev] |= matched_names
                if remove_names:
                    for ev in self.event_names:
                        self.selection[ev] -= remove_names
                self._refresh_both_lists()
            self.status_var.set("🎯 Guided selection applied via wizard")
            print("  ✓ Re‑applied guided selection via wizard")

        else:  # fresh
            self._set_event_names(list(EVENTS))
            for ev in self.event_names:
                self.selection[ev] = set()
            self._guided_filters = None
            self._reset_filters()
            self.status_var.set("🔄 Reset to fresh state")
            print("  ✓ Reset to fresh state via wizard")

    def _clear_all(self):
        """Clear all selections."""
        for ev in self.event_names:
            self.selection[ev] = set()
        self._refresh_both_lists()
        self.status_var.set("All selections cleared")

    # ── Plot GMPE spectra (inline, using gmpe.py) ─────────────

    def _plot_gmpe_spectra(self):
        """Open a dialog to enter event parameters, then plot GMPE spectra with quantiles."""
        dialog = tk.Toplevel(self.root)
        dialog.title("GMPE Spectra — Event Parameters")
        dialog.geometry("540x840")
        dialog.minsize(540, 700)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=COLORS["bg"])

        # ── Event-specific defaults ──
        _ev_defaults = {
            "HF_SMS": {"Epi": 0, "depth": 7,  "mag": 5.6},
            "LF_SMS": {"Epi": 0, "depth": 15, "mag": 6.4},
        }
        _edef = _ev_defaults.get(self.current_event, {"Epi": 0, "depth": 15, "mag": 6.4})

        # ── Determine which parameters are required by selected GMPEs ──
        event = self.current_event
        sel_names = self.selection.get(event, set())
        gmpe_list = sorted(sel_names) if sel_names else ["AbrahamsonEtAl2014"]

        # Collect the union of all required parameters across selected GMPEs
        _req_dist = set()
        _req_rupt = set()
        _req_site = set()
        for gname in gmpe_list:
            row = next((r for r in self.catalogue if r["GMPE"] == gname), None)
            if row:
                _req_dist.update(row["RequiresDistances"])
                _req_rupt.update(row["RequiresRupture"])
                _req_site.update(row["RequiresSites"])

        # Define all known parameters: (key, label, default, category)
        # category → which attribute set the param belongs to ("dist","rupt","site","meta")
        # Pre‑fill Z1.0 with value inferred from default Vs30 (same formula as gmpe.py)
        import math as _m
        _vs30_def = 980
        if _vs30_def < 180:
            _z1pt0_def = _m.exp(6.745) * 0.001
        elif _vs30_def < 500:
            _z1pt0_def = _m.exp(6.745 - 1.35 * _m.log(_vs30_def / 180)) * 0.001
        else:
            _z1pt0_def = _m.exp(5.394 - 4.48 * _m.log(_vs30_def / 500)) * 0.001
        # Infer Z2.5 from Z1.0 (same formula as gmpe.py)
        _z2pt5_def = (519 + 3.595 * (_z1pt0_def * 1000.)) * 0.001
        _PARAMS = [
            # Rupture parameters
            ("mag",      "Mag",        str(_edef["mag"]),   "rupt"),
            ("depth",    "Depth (km)", str(_edef["depth"]), "rupt"),
            ("dip",      "Dip (°)",    "90",                 "rupt"),
            ("rake",     "Rake (°)",   "0",                  "rupt"),
            ("ztor",     "Ztor (km)",  "",                   "rupt"),
            ("width",    "Width (km)", "",                   "rupt"),
            # hypo_depth omitted — same as Depth
            # Distance parameters
            ("epi",      "Epi (km)",   str(_edef["Epi"]),   "dist"),
            ("rjb",      "Rjb (km)",   "",                   "dist"),
            ("rrup",     "Rrup (km)",  "",                   "dist"),
            ("rhypo",    "Rhypo (km)", "",                   "dist"),
            ("repi",     "Repi (km)",  "",                   "dist"),
            ("rx",       "Rx (km)",    "-1",                 "dist"),
            ("ry0",      "Ry0 (km)",   "0",                  "dist"),
            ("rvolc",    "Rvolc (km)", "",                   "dist"),
            ("rcdpp",    "Rcdpp (km)", "",                   "dist"),
            ("clat",     "Clat (°)",   "",                   "dist"),
            ("clon",     "Clon (°)",   "",                   "dist"),
            ("azimuth",  "Azimuth (°)","",                   "dist"),
            # Site parameters
            ("vs30",     "Vs30 (m/s)", "980",                "site"),
            ("vs30measured","Vs30 measured","980",           "site"),
            ("z1pt0",    "Z1.0 (km)",  f"{_z1pt0_def:.4f}",   "site"),
            ("z1pt4",    "Z1.4 (km)",  "",                   "site"),
            ("z2pt5",    "Z2.5 (km)",  f"{_z2pt5_def:.4f}",   "site"),
            ("backarc",  "Back-arc",   "",                   "site"),
        ]

        # ── Build parameter UI frames ──
        _all_entries = {}  # key → (tk.Entry, StringVar)
        _group_frames = {}

        _CAT_LABELS = {
            "rupt": ("Rupture Parameters", "#fee2e2"),
            "dist": ("Distance Parameters", "#dbeafe"),
            "site": ("Site Parameters", "#d1fae5"),
        }
        # Add an extra frame for metadata (event name)
        _meta_frame = ttk.LabelFrame(dialog, text=" Meta ", padding="6")
        _meta_frame.pack(fill=tk.X, padx=10, pady=(4, 2))
        _meta_row = ttk.Frame(_meta_frame)
        _meta_row.pack(fill=tk.X)
        ttk.Label(_meta_row, text="Event name:").pack(side=tk.LEFT)
        _ev_name_var = tk.StringVar(value=self.current_event)
        ttk.Entry(_meta_row, textvariable=_ev_name_var, width=24,
                  font=("Helvetica", 11)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        _all_entries["event_name"] = (None, _ev_name_var)

        for cat_key in ("rupt", "dist", "site"):
            cat_label, cat_color = _CAT_LABELS[cat_key]
            frm = ttk.LabelFrame(dialog, text=f" {cat_label} ", padding="6")
            frm.pack(fill=tk.X, padx=10, pady=2)
            _group_frames[cat_key] = frm
            # Filter params for this category
            cat_params = [p for p in _PARAMS if p[3] == cat_key]
            # Layout in 2‑column grid
            for idx, (key, label, default, _) in enumerate(cat_params):
                row_i = idx // 2
                col_i = idx % 2
                # Determine if this param is required by any selected GMPE
                _req_set = {"dist": _req_dist, "rupt": _req_rupt, "site": _req_site}[cat_key]
                _is_required = key in _req_set
                # Human‑readable label: map OQ key → label
                _lbl = ttk.Label(frm, text=label)
                _lbl.grid(row=row_i, column=col_i * 2, sticky=tk.W, padx=(6, 2), pady=1)
                _var = tk.StringVar(value=default)
                # Use tk.Entry (not ttk) so we can set background color per field
                _ent = tk.Entry(frm, textvariable=_var, width=16,
                                font=("Helvetica", 10),
                                relief=tk.SUNKEN, bd=1)
                _ent.grid(row=row_i, column=col_i * 2 + 1, sticky=tk.W, padx=(0, 10), pady=1)
                # Background: red-ish if required, white otherwise
                _bg = "#fecaca" if _is_required else "#ffffff"
                _ent.configure(bg=_bg)
                _all_entries[key] = (_ent, _var)

        # ── GMPE count info ──
        gmpe_info = ttk.Label(dialog,
                              text=f"📌 {len(gmpe_list)} GMPE{'s' if len(gmpe_list)!=1 else ''} selected",
                              font=("Helvetica", 9, "bold"), foreground="#555")
        gmpe_info.pack(padx=12, pady=(2, 0), anchor=tk.W)

        # ── Options ──
        opt_frame = ttk.LabelFrame(dialog, text=" Options ", padding="6")
        opt_frame.pack(fill=tk.X, padx=10, pady=4)

        # Frequency range
        fr_row = ttk.Frame(opt_frame)
        fr_row.pack(fill=tk.X, pady=2)
        ttk.Label(fr_row, text="Freq range (Hz):").pack(side=tk.LEFT)
        fmin_var = tk.StringVar(value="0.25")
        ttk.Entry(fr_row, textvariable=fmin_var, width=6,
                  font=("Helvetica", 10)).pack(side=tk.LEFT, padx=2)
        ttk.Label(fr_row, text="–").pack(side=tk.LEFT)
        fmax_var = tk.StringVar(value="33.0")
        ttk.Entry(fr_row, textvariable=fmax_var, width=6,
                  font=("Helvetica", 10)).pack(side=tk.LEFT, padx=2)
        ttk.Label(fr_row, text="Hz   ").pack(side=tk.LEFT)
        ttk.Label(fr_row, text="N.pts:").pack(side=tk.LEFT)
        npts_var = tk.StringVar(value="100")
        ttk.Entry(fr_row, textvariable=npts_var, width=5,
                  font=("Helvetica", 10)).pack(side=tk.LEFT, padx=2)

        show_quantiles_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Show quantiles (q16 / q84)",
                        variable=show_quantiles_var).pack(anchor=tk.W, padx=6)

        # ── Status / error message ──
        err_var = tk.StringVar()
        ttk.Label(dialog, textvariable=err_var, foreground="red",
                  font=("Helvetica", 9)).pack(pady=(4, 0))

        # ── Storage for computed data ──
        plot_data = {"fig": None, "results": None, "freq": None,
                     "name": None, "mag": None, "dep": None, "Vs30": None}

        def _read_params():
            """Read and validate dialog inputs, return params dict or None."""
            def _g(key):
                """Get the string value of a parameter entry."""
                return _all_entries[key][1].get().strip()
            def _gf(key, default=None):
                """Get float value, returning default if empty/invalid."""
                v = _g(key)
                if not v:
                    return default
                try:
                    return float(v)
                except ValueError:
                    return default

            name = _g("event_name")
            if not name:
                err_var.set("Event name is required.")
                return None

            mag  = _gf("mag")
            dep  = _gf("depth")
            dip  = _gf("dip")
            rake = _gf("rake")
            epi  = _gf("epi")
            vs30 = _gf("vs30")
            rx   = _gf("rx")
            ry0  = _gf("ry0")
            ztor = _gf("ztor")
            width = _gf("width")
            rjb  = _gf("rjb")
            rrup = _gf("rrup")
            rhypo = _gf("rhypo")
            z1pt0 = _gf("z1pt0")
            z2pt5 = _gf("z2pt5")
            repi = _gf("repi")
            rvolc = _gf("rvolc")
            rcdpp = _gf("rcdpp")
            clat = _gf("clat")
            clon = _gf("clon")
            azimuth = _gf("azimuth")
            vs30measured = _gf("vs30measured")
            z1pt4 = _gf("z1pt4")
            backarc = _gf("backarc")

            # Validate required numeric fields
            if mag is None or dep is None:
                err_var.set("Mag and Depth are required numeric fields.")
                return None
            if dip is None:
                dip = 90.0
            if rake is None:
                rake = 0.0
            if epi is None:
                epi = 0.0
            if vs30 is None:
                vs30 = 980.0
            if rx is None:
                rx = -1.0
            if ry0 is None:
                ry0 = 0.0

            # Frequency range
            try:
                fmin = float(fmin_var.get().strip())
                fmax = float(fmax_var.get().strip())
                npts = int(npts_var.get().strip())
            except ValueError:
                err_var.set("Frequency range (fmin, fmax, npts) must be numeric.")
                return None
            if fmin <= 0 or fmax <= fmin or npts < 5:
                err_var.set("Invalid frequency range: fmin > 0, fmax > fmin, pts ≥ 5")
                return None
            return {"mag": mag, "dep": dep, "dip": dip, "rake": rake,
                    "name": name, "epi": epi, "Vs30": vs30, "Rx": rx, "Ry0": ry0,
                    "ztor": ztor, "width": width, "Rjb": rjb, "Rrup": rrup,
                    "z1pt0": z1pt0, "z2pt5": z2pt5,
                    "repi": repi,
                    "rvolc": rvolc, "rcdpp": rcdpp,
                    "clat": clat, "clon": clon, "azimuth": azimuth,
                    "vs30measured": vs30measured, "z1pt4": z1pt4,
                    "backarc": backarc,
                    "fmin": fmin, "fmax": fmax, "npts": npts}

        def _compute():
            """Compute GMPE spectra using the OpenQuake Python environment, then build figure."""
            import numpy as np
            import matplotlib
            matplotlib.use('TkAgg')  # interactive backend compatible with Tkinter
            import matplotlib.pyplot as plt
            import math
            import json, tempfile, subprocess

            p = _read_params()
            if p is None:
                return

            err_var.set("")
            self.status_var.set(f"📊 Computing {len(gmpe_list)} GMPEs via OQ environment…")
            self.root.update()

            try:
                # Geometry — auto-compute values that are not explicitly set
                rk = p["rake"]
                if rk >= 30.0 and rk <= 150.0:
                    width_val = 10 ** (-1.61 + 0.41 * p["mag"])
                elif rk >= -120.0 and rk <= -60.0:
                    width_val = 10 ** (-1.14 + 0.35 * p["mag"])
                else:
                    width_val = 10 ** (-0.76 + 0.27 * p["mag"])

                _ztor = p.get("ztor")
                if _ztor is None:
                    _ztor = max(p["dep"] - 0.6 * width_val * math.sin(math.pi / 180 * p["dip"]), 0)

                _Rjb = p.get("Rjb")
                if _Rjb is None:
                    _Rjb = p["epi"]

                _Rrup = p.get("Rrup")
                if _Rrup is None:
                    _Rrup = np.sqrt(_ztor ** 2 + _Rjb ** 2)

                _width = p.get("width")
                if _width is None:
                    _width = width_val

                freq = np.logspace(np.log10(p["fmin"]), np.log10(p["fmax"]), p["npts"])
                print(f"\n  📊 Frequency grid ({len(freq)} points): "
                      f"{freq[0]:.4f}  …  {freq[len(freq)//2-1]:.4f}  …  {freq[-1]:.4f} Hz")
                print(f"     Corresponding periods: "
                      f"{1/freq[-1]:.4f}  …  {1/freq[len(freq)//2-1]:.4f}  …  {1/freq[0]:.4f} s")

                # Build a small Python script that computes GMPEs via gmpe.py
                script_code = f'''
import numpy as np, sys, json
sys.path.insert(0, "{os.path.dirname(os.path.abspath(__file__))}")
import gmpe
tool = gmpe.gmmtools()
freq = np.array({freq.tolist()})
gmpe_list = {json.dumps(gmpe_list)}
result = tool.compute_batch(
    gmpe_list, freq,
    mag={p["mag"]}, depth={p["dep"]}, epi={p["epi"]}, vs30={p["Vs30"]},
    dip={p["dip"]}, rake={rk}, Rx={p["Rx"]},
    Rjb={_Rjb}, Rrup={_Rrup}, ztor={_ztor},
    width={_width}, z1pt0={p.get('z1pt0')}, z2pt5={p.get('z2pt5')},
    repi={p.get('repi')}, rvolc={p.get('rvolc')}, rcdpp={p.get('rcdpp')},
    clat={p.get('clat')}, clon={p.get('clon')}, azimuth={p.get('azimuth')},
    vs30measured={p.get('vs30measured')}, z1pt4={p.get('z1pt4')},
    backarc={p.get('backarc')},
)
try:
    out = json.dumps(result)
    print(out)
    sys.stdout.flush()
except Exception as e:
    msg = "FATAL: json.dumps failed: %s" % e
    print(msg, file=sys.stderr)
    print('{{"results": {{}}, "errors": [{{"gmpe": "GLOBAL", "error": "JSON serialization failed: %s"}}]}}' % e)
    sys.stderr.flush()
'''
                tmp_script = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", delete=False, prefix="oq_compute_"
                )
                tmp_script.write(script_code)
                tmp_script.close()

                oq_python = _OQ_PYTHON
                proc = subprocess.run(
                    [oq_python, tmp_script.name],
                    capture_output=True, text=True, timeout=120
                )
                os.unlink(tmp_script.name)

                if proc.returncode != 0:
                    print(f"\n❌ OQ subprocess failed (return code {proc.returncode}):")
                    # Print full stderr
                    for line in proc.stderr.strip().splitlines():
                        print(f"   {line}")
                    if proc.stdout.strip():
                        print(f"   stdout: {proc.stdout.strip()[:500]}")
                    err_var.set(f"OQ process failed — see terminal for details")
                    return

                # Print any warnings from GMPE computation (stderr)
                if proc.stderr.strip():
                    for line in proc.stderr.strip().splitlines():
                        line = line.strip()
                        if line:
                            print(f"  {line}")

                # The last line of stdout is the JSON output (preceded by debug prints)
                stdout_lines = proc.stdout.strip().splitlines()
                json_line = stdout_lines[-1] if stdout_lines else ""
                try:
                    output = json.loads(json_line)
                except json.JSONDecodeError:
                    err_var.set(f"Could not parse OQ output: {proc.stdout[:200]}")
                    return
                raw_results = output["results"]
                errors = output["errors"]

                # Report errors in the terminal
                if errors:
                    print(f"\n📊 GMPE computation errors ({len(errors)}):")
                    for e in errors:
                        print(f"  ✗ {e['gmpe']}: {e['error']}")
                if raw_results:
                    ok_count = len(raw_results)
                    print(f"  ✓ {ok_count} GMPE(s) computed successfully"
                          + (f", {len(errors)} failed" if errors else ""))
                else:
                    print("  ⚠ No GMPE returned valid results.")

                if not raw_results:
                    if errors:
                        details = "; ".join(f"{e['gmpe']}: {e['error'][:60]}" for e in errors[:5])
                        if len(errors) > 5:
                            details += f" … and {len(errors)-5} more"
                        err_var.set(f"All GMPEs failed:\n{details}")
                    else:
                        err_var.set("No results returned.")
                    return

                # Convert lists back to numpy arrays
                results = {}
                for gname, val in raw_results.items():
                    mean_l, sig1m_l, sig1p_l = val[0], val[1], val[2]
                    nat_freq_l = val[3] if len(val) >= 4 else None
                    results[gname] = (np.array(mean_l), np.array(sig1m_l),
                                      np.array(sig1p_l), np.array(nat_freq_l) if nat_freq_l is not None else freq)

                # Print summary of each GMPE's native frequency range
                print(f"\n  ✓ {len(results)} GMPEs computed  ({len(errors)} failed)" if errors
                      else f"\n  ✓ {len(results)} GMPEs computed")
                for gname, v in results.items():
                    nf = v[3]
                    print(f"    {gname:45s}  {nf[0]:.4f}–{nf[-1]:.4f} Hz  ({len(nf)} pts)")

                # Ensemble statistics — interpolate all GMPEs to common freq grid
                all_means = []
                for v in results.values():
                    mn, _, _, nf = v
                    # Interpolate this GMPE's data to the full user frequency grid
                    all_means.append(np.interp(freq, nf, mn, left=np.nan, right=np.nan))
                all_means = np.array(all_means)
                # Determine the common frequency range (intersection of all
                # GMPE native frequency domains) — statistics are computed
                # only within this common band.
                f_common_min = -np.inf
                f_common_max = np.inf
                for v in results.values():
                    nf = v[3]
                    f_common_min = max(f_common_min, nf.min())
                    f_common_max = min(f_common_max, nf.max())
                common_mask = (freq >= f_common_min) & (freq <= f_common_max)
                # Mean, median and quantiles — only on the common range
                mean_spec = np.full_like(freq, np.nan)
                median_spec = np.full_like(freq, np.nan)
                q16 = np.full_like(freq, np.nan)
                q84 = np.full_like(freq, np.nan)
                if np.any(common_mask):
                    mean_spec[common_mask] = np.nanmean(all_means[:, common_mask], axis=0)
                    median_spec[common_mask] = np.nanmedian(all_means[:, common_mask], axis=0)
                    q16[common_mask] = np.nanpercentile(all_means[:, common_mask], 16, axis=0)
                    q84[common_mask] = np.nanpercentile(all_means[:, common_mask], 84, axis=0)
                n_common = int(np.sum(common_mask))
                print(f"     Common frequency range: {f_common_min:.4f} – {f_common_max:.4f} Hz  ({n_common} pts)")

                # Build figure
                fig, ax = plt.subplots(1, 1, figsize=(12, 7))
                _fig_name = p["name"].replace(" ", "_").replace("/", "_")
                _json_name = os.path.splitext(os.path.basename(self.selection_path))[0]
                fig.canvas.manager.set_window_title(f"{_fig_name}_{_json_name}")
                ax.set_xscale('log')
                ax.set_yscale('log')
                ax.set_xlabel('Frequency [Hz]', fontsize=14)
                ax.set_ylabel('SA [g]', fontsize=14)
                ax.set_title(f'GMPE Spectra — {p["name"]}  (Mw={p["mag"]}, '
                             f'depth={p["dep"]}km, Vs30={p["Vs30"]})', fontsize=13)
                # Auto-scale y with a small buffer
                all_sa = np.concatenate([v[0] for v in results.values()])
                all_sa = all_sa[np.isfinite(all_sa)]
                if len(all_sa) == 0:
                    y_min, y_max = 0.001, 1.0
                else:
                    y_min = max(np.min(all_sa) * 0.5, 1e-5)
                    y_max = np.max(all_sa) * 2.0
                ax.set_ylim([y_min, y_max])

                cmap = plt.colormaps.get_cmap('Blues')
                n = len(results)
                for idx, (gname, val) in enumerate(results.items()):
                    mn = val[0]
                    nat_freq = val[3] if len(val) >= 4 else None
                    # Use the GMPE's native frequency vector for plotting
                    plot_freq = np.array(nat_freq) if nat_freq is not None else freq
                    c = cmap(0.4 + 0.5 * idx / max(n, 1))
                    short = make_gmpe_code(gname)
                    ax.plot(plot_freq, mn, color=c, lw=1.2, alpha=0.7, label=short)
                    # Dots at native frequencies (same as data points)
                    ax.scatter(plot_freq, mn, color=c, s=20, zorder=4,
                               edgecolors='face', linewidths=0.3, alpha=0.7,
                               marker='.')
                ax.set_xlim([freq[0], freq[-1]])

                # Mean
                (mean_line,) = ax.plot(freq, mean_spec, color='crimson', lw=2.5, label='Mean')
                (median_line,) = ax.plot(freq, median_spec, color='darkorange', lw=2.0, ls=':',
                                         label='Median')
                (q16_line,) = ax.plot(freq, q16, color='crimson', lw=1.5, ls='--',
                                      label='q16', visible=show_quantiles_var.get())
                (q84_line,) = ax.plot(freq, q84, color='crimson', lw=1.5, ls='--',
                                      label='q84', visible=show_quantiles_var.get())
                fill = ax.fill_between(freq, q16, q84, color='crimson', alpha=0.10,
                                       visible=show_quantiles_var.get())

                ax.legend(fontsize=7, loc='upper left', bbox_to_anchor=(1.02, 1.0), borderaxespad=0)
                ax.grid(which='both', alpha=0.3)
                fig.subplots_adjust(right=0.78)

                # Interactive curve labels on hover — uses normalised
                # Euclidean distance in (log10(f), log10(SA)) space so that
                # hovering near a curve or its data dots shows the GMPE name.
                _annot = ax.annotate(
                    "", xy=(0, 0), xytext=(12, 12),
                    textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow",
                              ec="gray", alpha=0.9),
                    fontsize=9, zorder=100)
                _annot.set_visible(False)

                # Pre‑compute axis spans in log space for normalisation
                _lx_lim = np.log10(ax.get_xlim())
                _ly_lim = np.log10(ax.get_ylim())
                _lx_span = _lx_lim[1] - _lx_lim[0]
                _ly_span = _ly_lim[1] - _ly_lim[0]

                def _on_hover(event):
                    if event.inaxes != ax:
                        _annot.set_visible(False)
                        fig.canvas.draw_idle()
                        return
                    if event.xdata is None or event.ydata is None \
                       or not np.isfinite(event.xdata) or not np.isfinite(event.ydata) \
                       or event.xdata <= 0 or event.ydata <= 0:
                        _annot.set_visible(False)
                        fig.canvas.draw_idle()
                        return
                    _lx0 = np.log10(event.xdata)
                    _ly0 = np.log10(event.ydata)
                    _best_dist = float('inf')
                    _best_label = ""
                    _best_x = _best_y = None
                    for _line in ax.lines:
                        lbl = _line.get_label()
                        if lbl in ("Mean", "Median", "q16", "q84"):
                            continue
                        xd, yd = _line.get_data()
                        if len(xd) == 0:
                            continue
                        # Normalised Euclidean distance in log‑log space
                        _lx = np.log10(np.maximum(xd, 1e-30))
                        _ly = np.log10(np.maximum(yd, 1e-30))
                        _dx = (_lx - _lx0) / _lx_span
                        _dy = (_ly - _ly0) / _ly_span
                        _dist = np.sqrt(_dx ** 2 + _dy ** 2)
                        _idx = np.argmin(_dist)
                        if _idx < len(yd) and np.isfinite(yd[_idx]) and np.isfinite(xd[_idx]):
                            if _dist[_idx] < _best_dist:
                                _best_dist = _dist[_idx]
                                _best_label = lbl
                                _best_x = xd[_idx]
                                _best_y = yd[_idx]
                    # Threshold: 6 % of the normalised diagonal
                    if _best_dist < 0.06:
                        _annot.xy = (_best_x, _best_y)
                        _annot.set_text(_best_label)
                        _annot.set_visible(True)
                    else:
                        _annot.set_visible(False)
                    fig.canvas.draw_idle()

                fig.canvas.mpl_connect('motion_notify_event', _on_hover)

                plot_data["fig"] = fig
                plot_data["ax"] = ax
                plot_data["results"] = results
                plot_data["freq"] = freq
                plot_data["mean_spec"] = mean_spec
                plot_data["median_spec"] = median_spec
                plot_data["q16"] = q16
                plot_data["q84"] = q84
                plot_data["q16_line"] = q16_line
                plot_data["q84_line"] = q84_line
                plot_data["median_line"] = median_line
                plot_data["fill"] = fill
                plot_data["name"] = p["name"]
                plot_data["mag"] = p["mag"]
                plot_data["dep"] = p["dep"]
                plot_data["Vs30"] = p["Vs30"]

                err_msg = ""
                if errors:
                    details = "; ".join(f"{e['gmpe']}: {e['error'][:50]}" for e in errors[:3])
                    if len(errors) > 3:
                        details += f" … and {len(errors)-3} more"
                    err_msg = f" ({len(errors)} failed: {details})"
                err_var.set(f"✓ Computed {len(results)} GMPEs{err_msg}" if not errors or len(errors) < len(results) else "")
                self.status_var.set(f"✅ Computed {len(results)} GMPEs" if not errors else f"✅ {len(results)} OK, {len(errors)} failed")
                # Save a PNG snapshot to a temp file (needed for the HTML report)
                import tempfile as _tf
                show_q = show_quantiles_var.get()
                plot_data["q16_line"].set_visible(show_q)
                plot_data["q84_line"].set_visible(show_q)
                plot_data["median_line"].set_visible(show_q)
                plot_data["fill"].set_visible(show_q)
                _tmp = _tf.NamedTemporaryFile(suffix=".png", delete=False, prefix="gmpe_plot_")
                plot_data["fig"].savefig(_tmp.name, bbox_inches="tight", dpi=150)
                plot_data["_tmp_path"] = _tmp.name
                # Show the figure interactively so mouse hover works
                fig.canvas.draw_idle()
                plt.show(block=False)
                # Close the temp‑file handle so it can be read below
                _tmp.close()

                # ── Generate self‑contained HTML report ──
                try:
                    import base64 as _b64
                    # Read the PNG and encode as base64
                    with open(_tmp.name, "rb") as _fh:
                        _img_b64 = _b64.b64encode(_fh.read()).decode("ascii")
                    # Build common‑freq table rows
                    _common_idx = np.where(common_mask)[0]
                    _html_rows = []
                    _html_rows.append(
                        "<tr><th>Freq (Hz)</th>"
                        + "".join(f"<th>{g}</th>" for g in sorted(results.keys()))
                        + "<th>Mean</th><th>Median</th><th>q16</th><th>q84</th></tr>"
                    )
                    for _i in _common_idx:
                        _f = freq[_i]
                        _row = f"<tr><td>{_f:.6f}</td>"
                        for _g in sorted(results.keys()):
                            _mn = results[_g][0]
                            # Interpolate this GMPE to the user grid
                            _nf = results[_g][3]
                            _v = float(np.interp(_f, _nf, _mn, left=np.nan, right=np.nan))
                            _cell = f"{_v:.6e}" if np.isfinite(_v) else "—"
                            _row += f"<td>{_cell}</td>"
                        _row += (f"<td>{mean_spec[_i]:.6e}</td>"
                                 f"<td>{median_spec[_i]:.6e}</td>"
                                 f"<td>{q16[_i]:.6e}</td>"
                                 f"<td>{q84[_i]:.6e}</td>")
                        _row += "</tr>"
                        _html_rows.append(_row)
                    # Build the HTML page
                    _ev_name = p["name"]
                    _safe_name = _ev_name.replace(" ", "_").replace("/", "_")
                    _html_path = os.path.join(os.getcwd(), f"{_safe_name}_gmpe_report.html")
                    _params_list = (
                        f"<li><b>Event:</b> {_ev_name}</li>"
                        f"<li><b>Magnitude:</b> {p['mag']}</li>"
                        f"<li><b>Depth:</b> {p['dep']} km</li>"
                        f"<li><b>Epicentral distance:</b> {p['epi']} km</li>"
                        f"<li><b>Vs30:</b> {p['Vs30']} m/s</li>"
                        f"<li><b>Dip:</b> {p['dip']}°</li>"
                        f"<li><b>Rake:</b> {p['rake']}°</li>"
                        f"<li><b>Rx:</b> {p['Rx']} km</li>"
                        f"<li><b>Ry0:</b> {p['Ry0']} km</li>"
                    )
                    _freq_info = (
                        f"<li><b>User frequency grid:</b> {freq[0]:.4f} – {freq[-1]:.4f} Hz  "
                        f"({len(freq)} pts)</li>"
                        f"<li><b>Common GMPE frequency range:</b> {f_common_min:.4f} – "
                        f"{f_common_max:.4f} Hz  ({n_common} pts)</li>"
                    )
                    _gmpe_list = "".join(
                        f"<li>{g}{'  ⚠' if any(e['gmpe']==g for e in errors) else ''}</li>"
                        for g in sorted(gmpe_list)
                    )
                    _error_list = ""
                    if errors:
                        _error_list = (
                            "<h3>⚠ Computation Errors</h3><ul>"
                            + "".join(f"<li><b>{e['gmpe']}:</b> {e['error'][:100]}</li>"
                                      for e in errors)
                            + "</ul>"
                        )
                    _html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>GMPE Report — {_ev_name}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:opsz@14..32&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #e8ecf1 0%, #d5dce6 100%); color: #1a2332; min-height: 100vh; padding: 30px; }}
  .container {{ max-width: 1300px; margin: auto; background: rgba(255,255,255,0.92); backdrop-filter: blur(12px); padding: 32px 36px; border-radius: 16px; box-shadow: 0 8px 32px rgba(0,0,0,0.10), 0 1px 4px rgba(0,0,0,0.04); }}
  h1 {{ font-size: 26px; font-weight: 700; color: #0f172a; margin-bottom: 4px; letter-spacing: -0.3px; }}
  .subtitle {{ font-size: 13px; color: #64748b; margin-bottom: 24px; }}
  h2 {{ font-size: 17px; font-weight: 600; color: #0f172a; margin: 24px 0 10px 0; padding-bottom: 6px; border-bottom: 2px solid #e2e8f0; display: flex; align-items: center; gap: 8px; }}
  h2 .badge {{ font-size: 11px; font-weight: 600; background: #3b82f6; color: white; border-radius: 40px; padding: 1px 10px; line-height: 20px; margin-left: 6px; }}
  h2 .badge.green {{ background: #22c55e; }}
  h2 .badge.orange {{ background: #f59e0b; }}
  ul {{ columns: 3; column-gap: 30px; list-style: none; padding: 0; }}
  ul li {{ break-inside: avoid; padding: 3px 0; font-size: 13px; color: #334155; }}
  ul li::before {{ content: "▸"; color: #3b82f6; margin-right: 6px; font-weight: 700; }}
  .params {{ columns: 2; }}
  .params li {{ break-inside: avoid; }}
  .params li::before {{ content: "•"; color: #64748b; }}
  img {{ max-width: 100%; height: auto; margin: 16px 0; border-radius: 10px; border: 1px solid #e2e8f0; box-shadow: 0 2px 12px rgba(0,0,0,0.05); }}
  table {{ border-collapse: separate; border-spacing: 0; width: 100%; font-size: 11.5px; margin: 12px 0; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  th, td {{ border: none; padding: 5px 8px; text-align: right; }}
  th {{ background: #1e293b; color: #f1f5f9; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.3px; }}
  th:first-child {{ text-align: left; }}
  td {{ border-bottom: 1px solid #e2e8f0; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:nth-child(even) td {{ background: #f8fafc; }}
  tr:hover td {{ background: #eef2ff; }}
  .scroll {{ overflow-x: auto; margin: 0 -4px; padding: 0 4px; }}
  .footer {{ margin-top: 28px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; }}
</style>
</head>
<body>
<div class="container">
<h1>📊 GMPE Spectra Report</h1>
<div class="subtitle">Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ·  {len(results)} GMPEs</div>

<div class="section-grid">
  <div class="card">
    <h3>🔧 Scenario Parameters</h3>
    <ul class="params">{_params_list}</ul>
  </div>
  <div class="card">
    <h3>📐 Frequency Range</h3>
    <ul>{_freq_info}</ul>
  </div>
</div>

<h2>Selected GMPEs <span class="badge">{len(gmpe_list)}</span></h2>
<ul>{_gmpe_list}</ul>

{_error_list}

<h2>📈 GMPE Spectra</h2>
<img src="data:image/png;base64,{_img_b64}" alt="GMPE Spectra">

<h2>📋 Spectral Values <span class="badge green">{n_common} pts</span></h2>
<div class="scroll"><table>{"".join(_html_rows)}</table></div>

<div class="footer">RESPMAtch — GMPE Selection Report</div>
</div>
</body>
</html>"""
                    with open(_html_path, "w", encoding="utf-8") as _fh:
                        _fh.write(_html)
                    print(f"  ✅ HTML report: {_html_path}")
                    self.status_var.set(f"✅ {len(results)} GMPEs — report saved")
                except Exception as _html_err:
                    print(f"  ⚠ HTML report generation failed: {_html_err}")

            except Exception as e:
                err_var.set(f"Error: {e}")
                import traceback
                traceback.print_exc()

        def _show_plot():
            if plot_data["fig"] is None:
                _compute()
                if plot_data["fig"] is None:
                    return
            # Bring the interactive figure window to the front
            plot_data["fig"].canvas.draw_idle()
            plot_data["fig"].show()

        def _save_figure():
            if plot_data["fig"] is None:
                _compute()
                if plot_data["fig"] is None:
                    return
            from tkinter import filedialog
            _json_name = os.path.splitext(os.path.basename(self.selection_path))[0]
            _proj_name = p["name"].replace(" ", "_").replace("/", "_")
            path = filedialog.asksaveasfilename(
                title="Save GMPE Spectra Figure",
                initialdir=".",
                initialfile=f"{_proj_name}_{_json_name}.pdf",
                defaultextension=".pdf",
                filetypes=[
                    ("PDF files", "*.pdf"),
                    ("PNG files", "*.png"),
                    ("SVG files", "*.svg"),
                    ("All files", "*.*")
                ]
            )
            if not path:
                return
            try:
                show_q = show_quantiles_var.get()
                plot_data["q16_line"].set_visible(show_q)
                plot_data["q84_line"].set_visible(show_q)
                plot_data["median_line"].set_visible(show_q)
                plot_data["fill"].set_visible(show_q)
                plot_data["fig"].savefig(path, bbox_inches='tight', dpi=150)
                err_var.set(f"✓ Saved: {os.path.basename(path)}")
                self.status_var.set(f"💾 Figure saved: {path}")
            except Exception as e:
                err_var.set(f"Save error: {e}")

        # ── Buttons ──
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=(8, 12))
        ttk.Button(btn_frame, text="📊  Plot", command=_compute).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="💾  Save Figure As…", command=_save_figure).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=4)

    # ── Run ───────────────────────────────────────────────────

    def _quit_app(self):
        """Close all windows and quit the application cleanly."""
        self.root.quit()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="GMPE Selection GUI")
    parser.add_argument("--catalogue", default=DEFAULT_CATALOGUE,
                        help=f"Path to GMPE catalogue CSV (default: {DEFAULT_CATALOGUE})")
    args = parser.parse_args()

    # Auto‑generate catalogue if missing (silent in OpenQuake env)
    _ensure_catalogue(args.catalogue)

    app = GMPESelectionGUI(args.catalogue)
    app.run()


if __name__ == "__main__":
    main()
