# compute_targetspectra.py  —  Spectres GMM en format compatible RSPMatch
#
# Copyright (C) 2024  Maria Lancieri
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
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

# ── Frequency grids based on each GMPE's native (COEFFS) frequency range ──
# BergeThierry native frequencies
bt_inst = AVAILABLE_GSIMS['BergeThierryEtAl2003Ms']()
bt_native_periods = tool._get_gmpe_native_periods(bt_inst)
if bt_native_periods is not None:
    freq_BT = np.sort(1.0 / np.array(bt_native_periods))
    # Keep only within [0.25, 33] Hz
    freq_BT = freq_BT[(freq_BT >= 0.25) & (freq_BT <= 33)]
else:
    freq_BT = np.logspace(np.log10(0.25), np.log10(33), 100)

# Common native range across all other GMPEs in the config
all_gmpe_names = set()
for ev in events:
    all_gmpe_names.update(GMPElist[ev])

f_min_list, f_max_list = [], []
for ngmpe in all_gmpe_names:
    try:
        inst = AVAILABLE_GSIMS[ngmpe]()
        periods = tool._get_gmpe_native_periods(inst)
        if periods is not None:
            freqs = 1.0 / np.array(periods)
            f_min_list.append(freqs.min())
            f_max_list.append(freqs.max())
    except Exception:
        pass

if f_min_list and f_max_list:
    # Intersection of all GMPE ranges — highest low bound, lowest high bound
    common_fmin = max(max(f_min_list), 0.5)
    common_fmax = min(min(f_max_list), 33)
else:
    common_fmin, common_fmax = 0.5, 33

if common_fmin >= common_fmax:
    # Fallback if intersection is empty
    common_fmin, common_fmax = 0.5, 33

freq_range = np.logspace(np.log10(common_fmin), np.log10(common_fmax), 100)

print(f"  ℹ freq_BT range:    [{freq_BT.min():.4f}, {freq_BT.max():.4f}] Hz  ({len(freq_BT)} pts)")
print(f"  ℹ freq_range range: [{freq_range.min():.4f}, {freq_range.max():.4f}] Hz  ({len(freq_range)} pts)")

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
        GMPElist[ev], freq_range,
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

# ── Interpolate each GMPE onto its own 100-point grid ──
# The grid covers that GMPE's native frequency range so that .tgt files
# always have exactly 100 points, each over its specific range.
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
        # Sort native data by ascending frequency for np.interp
        idx = np.argsort(nat_freq)
        fmin = nat_freq[idx][0]
        fmax = nat_freq[idx][-1]
        # 100-point logspace grid over this GMPE's native range
        grid = np.logspace(np.log10(fmin), np.log10(fmax), 100)
        VarFreq_interp[ev][ngmpe] = grid
        VarGMPE_interp[ev][ngmpe] = np.interp(
            grid, nat_freq[idx], nat_spec[idx])

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
