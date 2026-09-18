#!/usr/bin/env python3
"""
gmpe_args.py — Extra constructor arguments required by some OpenQuake GMPEs.

The OpenQuake registry contains ~970 GMPEs.  Most can be instantiated with
no arguments, but some classes require constructor arguments that have no
default value, e.g.::

    Douglas_Et_Al_2024Rjb_3branch(branch=1)          # branch: 1..3
    CanadaSHM6_StableCrust_AA13(submodel='central')  # low / central / high
    BA08SiteTerm(gmpe_name='BooreAtkinson2008')      # wraps another GMPE
    GMPETable(gmpe_table='my_table.hdf5')            # coefficient file

This module maps GMPE class name -> [(argument, default, kind), ...] for
every argument that MUST be supplied.  The GUI uses it to create one input
field per required argument, pre-filled with `default` (an empty string
means "no default in OpenQuake — the user must provide a value").

`kind` selects the input widget / value parsing:
    "text"        plain text
    "int"         integer
    "float"       float
    "gmpe"        name of another GMPE (editable combo box)
    "list_float"  comma-separated floats  -> list of floats
    "list_str"    comma-separated tokens  -> list of strings
    "int_list"    comma-separated ints / ranges ("1,2,3" or "1-5") -> list
                  of ints; one GMPE instance (curve) is computed per value
    "kwargs_json" a JSON object merged as **kwargs into the constructor
    ("a","b",…)   one of these fixed choices (combo box)

Derived from the OpenQuake engine 3.26.2 sources.
"""

GMPE_CTOR_ARGS = {
    # ── Douglas et al. (2024), UK: branch selection ────────────────────
    #   1..162 (full model), 1..5 (5-branch model), 1..3 (3-branch model).
    #   Several values can be given (comma-separated or a range, e.g.
    #   "1,2,3" or "1-5"): one curve is plotted per branch. The 3-/5-branch
    #   models default to all their branches; the 162-branch models default
    #   to branch 1 (like the OpenQuake default of the Rrup class).
    "Douglas_Et_Al_2024Rjb":          [("branch", "1", "int_list")],
    "Douglas_Et_Al_2024Rjb_5branch":  [("branch", "1,2,3,4,5", "int_list")],
    "Douglas_Et_Al_2024Rjb_3branch":  [("branch", "1,2,3", "int_list")],
    "Douglas_Et_Al_2024Rrup":         [("branch", "1", "int_list")],
    "Douglas_Et_Al_2024Rrup_5branch": [("branch", "1,2,3,4,5", "int_list")],
    "Douglas_Et_Al_2024Rrup_3branch": [("branch", "1,2,3", "int_list")],

    # ── Canada SHM6, stable crust ──────────────────────────────────────
    #   AA13 model: submodel is low / central / high.
    #   NGA-East model: submodel is "01" … "13" (the 13 PEER models).
    "CanadaSHM6_StableCrust_AA13":
        [("submodel", "central", ("low", "central", "high"))],
    "CanadaSHM6_StableCrust_NGAEast":
        [("submodel", "01", ("01", "02", "03", "04", "05", "06",
                              "07", "08", "09", "10", "11", "12",
                              "13"))],

    # ── GMPEs wrapping another GMPE ('gmpe_name') ──────────────────────
    #    Pre-filled only where the wrapper name identifies its base GMPE.
    "BA08SiteTerm":                   [("gmpe_name", "BooreAtkinson2008", "gmpe")],
    "BSSA14SiteTerm":                 [("gmpe_name", "BooreEtAl2014", "gmpe")],
    "CB14BasinTerm":                  [("gmpe_name", "CampbellBozorgnia2014", "gmpe")],
    "CY14SiteTerm":                   [("gmpe_name", "ChiouYoungs2014", "gmpe")],
    "AlAtikSigmaModel":               [("gmpe_name", "", "gmpe")],
    "GulerceAbrahamson2011":          [("gmpe_name", "", "gmpe")],
    "M9BasinTerm":                    [("gmpe_name", "", "gmpe")],
    "NRCan15SiteTerm":                [("gmpe_name", "", "gmpe")],
    "NRCan15SiteTermLinear":          [("gmpe_name", "", "gmpe")],
    "SplitSigmaGMPE":                 [("gmpe_name", "", "gmpe")],
    "TromansEtAl2019":                [("gmpe_name", "", "gmpe")],
    "TromansEtAl2019SigmaMu":         [("gmpe_name", "", "gmpe")],
    "Eurocode8Amplification":         [("gmpe_name", "", "gmpe")],
    "Eurocode8AmplificationDefault":  [("gmpe_name", "", "gmpe")],
    "PitilakisEtAl2018":              [("gmpe_name", "", "gmpe")],
    "PitilakisEtAl2020":              [("gmpe_name", "", "gmpe")],
    "SandikkayaDinsever2018":         [("gmpe_name", "", "gmpe")],
    "GenericGmpeAvgSA":               [("gmpe_name", "", "gmpe"),
                                       ("avg_periods", "", "list_float")],
    "GmpeIndirectAvgSA":              [("gmpe_name", "", "gmpe"),
                                       ("corr_func", "baker_jayaram",
                                        ("baker_jayaram", "akkar", "eshm20",
                                         "clemett_asc", "clemett_sinter",
                                         "clemett_sslab", "clemett_vrancea",
                                         "none"))],
    "GridAdjustedGMPE":               [("gmpe_name", "", "gmpe"),
                                       ("grid_hdf5_file", "", "text")],

    # NSHMP2014: sgn +1 = Upper, 0 = Mean, -1 = Lower (see OQ aliases)
    "NSHMP2014":                      [("gmpe_name", "", "gmpe"),
                                       ("sgn", "0", "int")],

    # ── Coefficient-table GMPEs ────────────────────────────────────────
    #    A file name shipped with OpenQuake is pre-filled as an example.
    "NGAEastGMPE":
        [("gmpe_table", "NGAEast_BOORE_A04_J15.hdf5", "text")],
    "NGAEastGMPETotalSigma":
        [("gmpe_table", "NGAEast_BOORE_A04_J15.hdf5", "text")],
    "NGAEastUSGSGMPE":
        [("gmpe_table", "nga_east_1CCSP.hdf5", "text")],
    "NGAEastAUS2023GMPE":
        [("table_relpath", "NGA-East_Backbone_Model.geometric.3000.mps.hdf5",
          "text")],
    "NBCC2015_AA13":
        [("gmpe_table", "ENA_med_clC.hdf5", "text"),
         ("REQUIRES_DISTANCES", "rhypo", "list_str"),
         ("DEFINED_FOR_TECTONIC_REGION_TYPE", "Stable Crust",
          ("Stable Crust", "Active Crust", "Active Crust Fault",
           "Subduction Inslab 30", "Subduction Inslab 50",
           "Subduction Interface", "Offshore"))],
    "GMPETable":                      [("gmpe_table", "", "text")],

    # ── Generic adjustable GMPE ────────────────────────────────────────
    #    No defaults in OpenQuake: d_sigma = stress drop [bar], kappa0 [s].
    "HassaniAtkinson2018":            [("d_sigma", "", "float"),
                                       ("kappa0", "", "float")],

    # ── Composite GMPEs: constructed with keyword arguments (JSON) ─────
    #    AvgGMPE/AvgPoeGMPE: {branch: {gmpe_name: {params…, weight: w}}}
    #    ModifiableGMPE:     {gmpe: {gmpe_name: {params…}}, …adjustments}
    "AvgGMPE":     [("*",
                     '{"b1": {"BooreEtAl2014": {"weight": 0.5}}, '
                     '"b2": {"ChiouYoungs2014": {"weight": 0.5}}}',
                     "kwargs_json")],
    "AvgPoeGMPE":  [("*",
                     '{"b1": {"BooreEtAl2014": {"weight": 0.5}}, '
                     '"b2": {"ChiouYoungs2014": {"weight": 0.5}}}',
                     "kwargs_json")],
    "ModifiableGMPE": [("*", '{"gmpe": {"BooreEtAl2014": {}}}',
                        "kwargs_json")],
}


# ── Allowed ranges / expected values ─────────────────────────────────────
# Shown in the GUI next to the input field of each argument. Only entries
# documented by the OpenQuake implementation are listed here.
GMPE_ARG_HINTS = {
    # Douglas et al. (2024): branch ranges depend on the model
    "Douglas_Et_Al_2024Rjb":          {"branch": "1\u2013162"},
    "Douglas_Et_Al_2024Rjb_5branch":  {"branch": "1\u20135"},
    "Douglas_Et_Al_2024Rjb_3branch":  {"branch": "1\u20133"},
    "Douglas_Et_Al_2024Rrup":         {"branch": "1\u2013162"},
    "Douglas_Et_Al_2024Rrup_5branch": {"branch": "1\u20135"},
    "Douglas_Et_Al_2024Rrup_3branch": {"branch": "1\u20133"},

    # NSHMP2014: sign of the adjustment
    "NSHMP2014": {"sgn": "\u22121 = Lower, 0 = Mean, +1 = Upper"},

    # Coefficient table / grid file locations
    "NGAEastGMPE":           {"gmpe_table": "file in OQ gsim/nga_east_tables/"},
    "NGAEastGMPETotalSigma": {"gmpe_table": "file in OQ gsim/nga_east_tables/"},
    "NGAEastUSGSGMPE":       {"gmpe_table": "file in OQ gsim/usgs_nga_east_tables/"},
    "NGAEastAUS2023GMPE":    {"table_relpath": "file in OQ gsim/aus23/"},
    "NBCC2015_AA13":         {"gmpe_table": "file in OQ gsim/can15/nbcc2015_tables/"},
    "GMPETable":             {"gmpe_table": "path to your coefficient .hdf5"},
    "GridAdjustedGMPE":      {"grid_hdf5_file": "path to your grid .hdf5"},

    # Units from the class docstrings
    "HassaniAtkinson2018": {"d_sigma": "stress drop [bar]",
                            "kappa0": "kappa0 [s]"},
    "GenericGmpeAvgSA":    {"avg_periods": "periods [s], e.g. 0.5, 1.0"},
}
