# compute_targetspectra.py  —  Spectres GMM en format compatible RSPMatch
#
# Usage:
#   python compute_targetspectra.py <config.json>
#
# Input parameters (events, Vs30, GMPE list, …) are read from the config's
# SCENARIO block.
#
# Output: a PDF figure and one Input_<event>_<GMPEcode>/ directory per GMPE,
# each containing the target spectrum file.
# --------------------------------------------------------------------------

# ----- OpenQuake environment activation -----
import subprocess, sys, os
_OQ_ENV = os.path.expanduser("~/openquake/bin/python")
if not sys.executable.startswith(os.path.expanduser("~/openquake")):
    print("🔁 Switching to OpenQuake environment...")
    os.execv(_OQ_ENV, [_OQ_ENV] + sys.argv)
# --------------------------------------------

import numpy as np
import json
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib

import gmpe
from openquake.hazardlib import gsim
tool = gmpe.gmmtools()

AVAILABLE_GSIMS = gsim.get_available_gsims()

# --------------------------------------------------------------------------
# Load input parameters from JSON config (passed as terminal argument)
# --------------------------------------------------------------------------
show_plot = "--show" in sys.argv
if show_plot:
    sys.argv.remove("--show")
if len(sys.argv) < 2:
    print("Usage: python compute_targetspectra.py [--show] <config.json>")
    sys.exit(1)
with open(sys.argv[1]) as f:
    full_config = json.load(f)
    inp = full_config["SCENARIO"]
BASE_DIR = full_config.get("BASE_DIR", ".")

events = list(inp["events"].keys())
figname = 'Alea_' + '_'.join(events)

Vs30 = inp["Vs30"]
rake = inp["rake"]
dip = inp["dip"]
Rx = inp["Rx"]

Epi = {}; depth = {}; mag = {}; depthBT = {}; magBT = {}; GMPElist = {}; GMPE_CODE = {}

for ev in events:
    edata = inp["events"][ev]
    Epi[ev] = edata["Epi"]
    depth[ev] = edata["depth"]
    mag[ev] = edata["mag"]
    depthBT[ev] = edata.get("depthBT", edata["depth"])
    magBT[ev] = edata.get("magBT", edata["mag"])
    GMPElist[ev] = edata["GMPElist"]
    # Build a mapping from GMPE full name → short code
    # Uses per-event GMPE_CODE if present in config, otherwise identity
    for ngmpe in GMPElist[ev]:
        code = edata.get("GMPE_CODE", ngmpe)
        GMPE_CODE[ngmpe] = code

print(f"  ✓ Scenario: Vs30={Vs30}, rake={rake}, dip={dip}, Rx={Rx}")
for ev in events:
    print(f"  ✓ Event '{ev}': Epi={Epi[ev]}, depth={depth[ev]}, mag={mag[ev]}")

# ── User-requested frequency range ──
# Each GMPE is computed on its native frequencies clipped to this range.
FMIN = 0.25   # Hz
FMAX = 33.0   # Hz
NPTS = 100

# BergeThierry native frequencies (clipped to user range)
bt_inst = AVAILABLE_GSIMS['BergeThierryEtAl2003Ms']()
bt_native_periods = tool._get_gmpe_native_periods(bt_inst)
if bt_native_periods is not None:
    freq_BT = np.sort(1.0 / np.array(bt_native_periods))
    freq_BT = freq_BT[(freq_BT >= FMIN) & (freq_BT <= FMAX)]
else:
    freq_BT = np.logspace(np.log10(FMIN), np.log10(FMAX), NPTS)

# User reference grid — used only to define the min/max bounds for clipping
# each GMPE's native periods. Actual computation points come from COEFFS.
freq_user = np.logspace(np.log10(FMIN), np.log10(FMAX), NPTS)

print(f"  ℹ User frequency range: [{FMIN}, {FMAX}] Hz  ({NPTS} pts)")
print(f"  ℹ freq_BT range:        [{freq_BT.min():.4f}, {freq_BT.max():.4f}] Hz  ({len(freq_BT)} pts)")

BT2003_RP3 = {}
BT2003_freq = {}
for ev in events:
    res = tool.computegmpe(
        'BergeThierryEtAl2003Ms', freq_BT,
        magBT[ev], depthBT[ev], Epi[ev], Vs30)
    BT2003_RP3[ev] = res[0]  # mean spectrum
    BT2003_freq[ev] = np.array(res[5])  # actual native frequencies used
    print(res[4])  # tectonic zone

SMF_f = np.array([0.35, 3.5, 9, 30, 33])
SMF   = np.array([0.02, 0.21, 0.23, 0.1, 0.1])

# Compute all GMPEs via batch — geometry (Rjb/Rrup/ztor) is handled by gmpe.py
VarGMPE = {}       # event → GMPE name → mean spectrum array
VarFreq = {}       # event → GMPE name → native frequency array
for ev in events:
    VarGMPE[ev] = {}
    VarFreq[ev] = {}
    batch = tool.compute_batch(
        GMPElist[ev], freq_user,
        mag[ev], depth[ev], Epi[ev], Vs30,
        dip=dip, rake=rake, Rx=Rx)
    failed = {e["gmpe"] for e in batch.get("errors", [])}
    for ngmpe in GMPElist[ev]:
        if ngmpe in failed:
            continue
        mean, sig1m, sig1p, nat_freq = batch["results"][ngmpe]
        VarGMPE[ev][ngmpe] = np.array(mean)
        VarFreq[ev][ngmpe] = np.array(nat_freq)
    if batch.get("errors"):
        for e in batch["errors"]:
            print(f"  ✗ {e['gmpe']}: {e['error']}")

for ev in events:
    print(f"--- {ev} ---")
    for ngmpe in GMPElist[ev]:
        if ngmpe in VarGMPE[ev]:
            fmin = VarFreq[ev][ngmpe].min()
            fmax = VarFreq[ev][ngmpe].max()
            print(f"  {ngmpe}  freq range: [{fmin:.3f}, {fmax:.3f}] Hz")

# ── Interpolate each GMPE onto 100 points over its truncated range ──
# Each GMPE was computed at its native frequencies clipped to [FMIN, FMAX].
# The clipped native range (nat_freq.min() .. nat_freq.max()) may be shorter
# than [FMIN, FMAX] if the GMPE does not cover the full user range.
# We create a 100-point logspace grid over this *truncated* range, so that
# .tgt files always have exactly 100 points, each over its GMPE's valid range.
VarFreq_interp = {}   # event → GMPE name → 100-point frequency grid
VarGMPE_interp = {}   # event → GMPE name → spectrum on that grid
for ev in events:
    VarFreq_interp[ev] = {}
    VarGMPE_interp[ev] = {}
    for ngmpe in GMPElist[ev]:
        if ngmpe not in VarGMPE[ev]:
            continue
        nat_freq = VarFreq[ev][ngmpe]
        nat_spec = VarGMPE[ev][ngmpe]
        # Sort native data by ascending frequency (gmpe.py may return
        # decreasing frequencies since periods are sorted increasingly)
        idx = np.argsort(nat_freq)
        nat_freq_sorted = nat_freq[idx]
        nat_spec_sorted = nat_spec[idx]
        # Truncated range = intersection of [FMIN, FMAX] with native range
        fmin = max(nat_freq_sorted.min(), FMIN)
        fmax = min(nat_freq_sorted.max(), FMAX)
        # 100-point logspace grid over the truncated range
        grid = np.logspace(np.log10(fmin), np.log10(fmax), NPTS)
        VarFreq_interp[ev][ngmpe] = grid
        VarGMPE_interp[ev][ngmpe] = np.interp(
            grid, nat_freq_sorted, nat_spec_sorted)

# ---------- GMPE code (already loaded above) ----------

# ---------- Plot ----------
cmap = matplotlib.colormaps.get_cmap('Blues')
col = {}; colBT = {}
for eve in events:
    gradient = np.linspace(0.5, 1, len(GMPElist[eve]))
    print(eve, gradient)
    col[eve] = [matplotlib.colors.to_hex(cmap(i)) for i in gradient]
    colBT[eve] = 'k'

fig = plt.figure(1, figsize=(24, 8))
gs = gridspec.GridSpec(1, 2)
gs.update(left=0.05, right=0.95, bottom=0.05, top=0.95, hspace=0.3, wspace=0.4)
fsz = 18

for hh, eve in enumerate(events):
    ax50 = fig.add_subplot(gs[0, hh])
    ax50.set_xscale('log')
    ax50.set_yscale('log')
    ax50.set_ylabel(r'$SA [g]$', fontsize=fsz)
    ax50.set_xlabel(r'$Frequency [Hz]$', fontsize=fsz)
    ax50.set_ylim([0.002, 1.5])

    # Sort BT2003 by ascending frequency for clean line rendering
    b_idx = np.argsort(BT2003_freq[eve])
    ax50.plot(BT2003_freq[eve][b_idx], BT2003_RP3[eve][b_idx], color=colBT[eve], lw=3, label='BT2003', zorder=len(GMPElist[eve]))
    for dd, ngmpe in enumerate(GMPElist[eve]):
        if ngmpe not in VarGMPE_interp[eve]:
            continue
        gmpe_label = GMPE_CODE.get(ngmpe, ngmpe)
        ax50.plot(VarFreq_interp[eve][ngmpe], VarGMPE_interp[eve][ngmpe],
                  color=col[eve][dd], label=gmpe_label, lw=2)

    # Set x‑axis limits to the union of all plotted frequency ranges
    all_f = [BT2003_freq[eve].min(), BT2003_freq[eve].max()]
    for ngmpe in GMPElist[eve]:
        if ngmpe in VarFreq_interp[eve]:
            all_f.extend([VarFreq_interp[eve][ngmpe].min(),
                          VarFreq_interp[eve][ngmpe].max()])
    ax50.set_xlim([min(all_f), max(all_f)])

    ax50.legend(bbox_to_anchor=(0.95, 0.25), fontsize=16)
    ax50.grid(which='both')

fig_dir = os.path.join(BASE_DIR, "Figures")
os.makedirs(fig_dir, exist_ok=True)
pdf_path = os.path.join(fig_dir, figname + "events.pdf")
plt.savefig(pdf_path, bbox_inches='tight')
print(f"Figure saved: {pdf_path}")
if show_plot:
    plt.show(block=True)
else:
    plt.close(fig)

# ----------------------------------------------------------------------
# Save target spectrum files (100 points per GMPE, each over its own range)
# ----------------------------------------------------------------------
for ev in events:
    for ngmpe in GMPElist[ev]:
        if ngmpe not in VarGMPE_interp[ev]:
            continue
        gmpe_code = GMPE_CODE.get(ngmpe, ngmpe)
        suffix = f"_{ev}_{gmpe_code}"
        outdir = os.path.join(BASE_DIR, f"Input{suffix}")
        os.makedirs(outdir, exist_ok=True)

        tgt_filename = f"target{suffix}.tgt"
        tgt_file = os.path.join(outdir, tgt_filename)
        npts = len(VarFreq_interp[ev][ngmpe])
        with open(tgt_file, "w") as f:
            f.write(f"{tgt_filename}\n")
            f.write(f"\t{npts} 1\n")
            f.write("0.050000\n")
            for fi, vi in zip(VarFreq_interp[ev][ngmpe],
                              VarGMPE_interp[ev][ngmpe]):
                f.write(f"\t{fi:.6f} 0 1000\t{vi:.6e}\n")
        print(f"Target file saved: {tgt_file}")
