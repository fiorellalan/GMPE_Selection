# GMPE Selection — RESPMAtch

A collection of Python tools for selecting Ground Motion Prediction Equations (GMPEs) from the [OpenQuake](https://github.com/gem/oq-hazardlib) library and computing their response spectra for use with [RSPMatch](https://www.engr.unr.edu/people/kayen/software/).

## Project Structure

```
GMPE_selection/
├── src/
│   ├── gmpe.py                  # Core module: GMPE computation via OpenQuake
│   ├── gmpe_selection_gui.py    # Interactive Tkinter GUI for GMPE selection
│   └── compute_targetspectra.py # CLI script: compute target spectra in RSPMatch format
├── Manual/                      # HTML documentation & example images
└── README.md
```

## Modules

### 1. `src/gmpe.py` — GMPE Computation Engine

Core class `gmmtools` that wraps OpenQuake's `hazardlib` to compute ground-motion spectra.

**Key features:**

- Reads site, rupture, and distance parameters and prepares OpenQuake context objects
- Computes mean and ±1σ spectral accelerations for any GMPE available in OpenQuake
- Uses each GMPE's native frequency grid (from its `COEFFS` table) for maximum accuracy
- Auto-computes missing geometry: Rjb, Rrup, Ztor, rupture width
- Infers site parameters (z1.0, z2.5) from Vs30 when not provided
- Batch processing of multiple GMPEs with error isolation

**Main methods:**

| Method | Description |
|---|---|
| `read_gmpeinput()` | Builds OpenQuake `SitesContext`, `RuptureContext`, `DistancesContext` |
| `computegmpe(gmpe, freq, mag, depth, Epi, vs30, ...)` | Computes mean & ±1σ spectra for a single GMPE |
| `compute_batch(gmpe_list, freq, mag, depth, epi, vs30, ...)` | Batch‑computes multiple GMPEs, returns JSON‑serializable dict |

### 2. `src/gmpe_selection_gui.py` — Interactive GMPE Selector

A full-featured Tkinter graphical application for browsing, filtering, and selecting GMPEs from the OpenQuake catalogue.

**Key features:**

- **Startup wizard** — three modes:
  - *Load existing selection* — open a previously saved JSON file
  - *Interactive review* — guided questions (year range, region, distances, site parameters, IMTs, std devs) followed by country-specific and family-variant dialogs
  - *Start fresh* — empty selection with default filters
- **Filter panel** — narrow down the 200+ GMPEs by:
  - Publication year range
  - Tectonic region (Active Shallow Crust, Stable Shallow Crust, etc.)
  - Required distance metrics (Rjb, Rrup, Rhypo, Rx, …)
  - Required site parameters (Vs30, z1.0, z2.5, …)
  - Required rupture parameters (mag, rake, dip, Ztor, width, …)
  - Intensity Measure Types (SA, PGA, PGV, …)
  - Standard deviation types (Total, Inter‑event, Intra‑event, …)
- **Dual-pane transfer interface** — browse available GMPEs on the left, move selected ones to the right via buttons, double‑click, or right‑click context menu
- **Search** — quick substring filter within the available list
- **Add by name** — type a partial GMPE name to add it directly
- **GMPE details** — click any GMPE to see a human‑readable description of its parameters
- **Plot spectra** — enter event parameters (magnitude, depth, Vs30, distances, …) and generate an interactive Matplotlib figure with:
  - Individual GMPE spectra plotted at their native frequencies
  - Ensemble mean, median, and 16th/84th percentiles
  - Mouse hover labels identifying each curve
  - Toggle quantile visibility
- **HTML report** — each plot generates a self‑contained HTML page with the figure, parameter summary, and spectral value table
- **Save/Load** — JSON format with `[code, fullname]` pairs, supports multi-event and single-event files
- **Dark mode** — automatically adapts colours to macOS dark appearance
- **Auto‑generated catalogue** — if `gmpe_catalogue.csv` is missing, it is generated automatically by querying OpenQuake

**Usage:**

```bash
python src/gmpe_selection_gui.py
python src/gmpe_selection_gui.py --catalogue gmpe_catalogue.csv
```

### 3. `src/compute_targetspectra.py` — Target Spectrum Generator

Command-line script that reads a JSON configuration file and produces GMPE target spectra in the format required by RSPMatch.

**Key features:**

- Reads scenario parameters (events, Vs30, magnitude, depth, distances) from a JSON config
- Computes a BergeThierry et al. 2003 reference spectrum for each event
- Computes all user‑selected GMPEs via batch processing
- Automatically determines the common frequency range across all GMPEs
- Interpolates each GMPE onto its own 100‑point log‑spaced frequency grid
- Saves one `Input_<event>_<GMPEcode>/` directory per GMPE containing the `.tgt` file
- Generates a PDF figure comparing all spectra

**Usage:**

```bash
python src/compute_targetspectra.py <config.json>
python src/compute_targetspectra.py --show <config.json>   # show interactive plot
```

The script automatically switches to the OpenQuake Python environment (`~/openquake/bin/python`) if not already running in it.

**Config JSON structure:**

```json
{
  "SCENARIO": {
    "Vs30": 980,
    "rake": 0,
    "dip": 90,
    "Rx": -1,
    "events": {
      "HF_SMS": {
        "Epi": 0,
        "depth": 7,
        "mag": 5.6,
        "GMPElist": ["AbrahamsonEtAl2014", "BooreEtAl2014", ...],
        "GMPE_CODE": { "AbrahamsonEtAl2014": "ASB14", ... }
      },
      "LF_SMS": { ... }
    }
  },
  "BASE_DIR": "."
}
```

## Required Dependencies

| Library | Version | Notes |
|---|---|---|
| Python | ≥ 3.8 | |
| [NumPy](https://numpy.org/) | ≥ 1.20 | Numerical arrays |
| [SciPy](https://scipy.org/) | ≥ 1.7 | Signal processing utilities |
| [Matplotlib](https://matplotlib.org/) | ≥ 3.4 | Plotting (PDF, PNG, interactive figures) |
| [OpenQuake hazardlib](https://github.com/gem/oq-hazardlib) | ≥ 3.14 | GMPE implementations (`openquake.hazardlib`). **This is the essential dependency.** |
| Tkinter | (comes with Python) | GUI toolkit for `gmpe_selection_gui.py` |

### Installing OpenQuake

The recommended installation is via Conda (or Miniforge) in a dedicated environment:

```bash
conda create -n openquake python=3.11
conda activate openquake
conda install -c conda-forge openquake-engine
```

The scripts expect the OpenQuake environment at `~/openquake/bin/python`. If installed elsewhere, adjust the `_OQ_ENV` path in the source files, or simply run the scripts from within your `openquake` Conda environment.

### Installing other dependencies

```bash
pip install numpy scipy matplotlib
```

## Typical Workflow

1. **Select GMPEs** — run `gmpe_selection_gui.py`, use the wizard to filter and select the appropriate GMPEs for your project, then save the selection as a JSON file.

2. **Compute target spectra** — prepare a JSON config referencing the selected GMPEs, then run `compute_targetspectra.py` to generate `.tgt` files in RSPMatch format.

3. **Use with RSPMatch** — the `.tgt` files produced in `Input_*` directories can be used directly as target spectra for seismic matching.

## Output Formats

- **Selection JSON** (`*_selection.json`): lists selected GMPEs with short codes and full OpenQuake class names
- **Target spectra** (`target_<event>_<code>.tgt`): 100‑point frequency–acceleration files in RSPMatch format
- **PDF figures**: comparison plots of all selected GMPEs vs. the BergeThierry reference
- **HTML reports**: interactive, self‑contained reports with embedded spectra and spectral values (from the Plot dialog in the GUI)
- **PNG figures**: raster figure exports (from the Plot dialog)

## License

This project is distributed under the GNU General Public License v3 (GPLv3).  
See the `gmpe.py` header for copyright details.
