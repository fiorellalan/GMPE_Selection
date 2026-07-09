#!/usr/bin/env python -W ignore::Warning
# gmpe.py
# GMPE computation engine for RESPMAtch — wraps OpenQuake hazardlib.
#
# Copyright (C) 2010-2022 Maria LANCIERI

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


import scipy as sp
import numpy as np
import sys

class Object(object):
    pass

class gmmtools:


    #### GMPE computing ####


    def read_gmpeinput (self):
        from openquake.hazardlib import gsim, imt
        from openquake.hazardlib.contexts import SitesContext, RuptureContext, DistancesContext
        from openquake.hazardlib.site import SiteCollection
        from openquake.hazardlib.source.rupture import BaseRupture
        import math

        sites = SitesContext()
        rupture = RuptureContext()
        distances = DistancesContext()   

        # Use user-provided values if given, otherwise infer from vs30
        if self.z1pt0 is not None:
            z1pt0 = float(self.z1pt0)
        else:
            if self.vs30<180:
                z1pt0 = np.exp(6.745)*0.001
            elif self.vs30<500:
                z1pt0 = np.exp(6.745-1.35*np.log(self.vs30/180))*0.001
            else:
                z1pt0 = np.exp(5.394-4.48*np.log(self.vs30/500))*0.001

        if self.z2pt5 is not None:
            z2pt5 = float(self.z2pt5)
        else:
            if z1pt0 >0:
                z2pt5 = (519 + 3.595*(z1pt0*1000.))*0.001
            else: 
                z2pt5 = (519 + 3.595*(self.vs30*1000.))*0.001
        Rhypo = np.sqrt(self.Epi**2+self.depth**2)
        print (Rhypo)
        
        setattr(sites,'vs30', np.array([float(self.vs30)]))
        setattr(sites,'region',np.array([self.region]))
        setattr(sites,'z2pt5',np.array([float(z2pt5)]))
        setattr(sites,'z1pt0',np.array([float(z1pt0)]))
        if self.vs30measured is not None:
            setattr(sites,'vs30measured', np.array([float(self.vs30measured)]))
        else:
            setattr(sites,'vs30measured', np.array([float(self.vs30)]))
        if self.z1pt4 is not None:
            setattr(sites,'z1pt4', np.array([float(self.z1pt4)]))
        if self.backarc is not None:
            setattr(sites,'backarc', np.array([float(self.backarc)]))
        setattr(sites,'sids',np.arange(1))
        if self.rake is not None: setattr(rupture,'rake',self.rake)
        if self.dip is not None:  setattr(rupture,'dip',float(self.dip))
        setattr(rupture,'mag',       np.array([float(self.mag)]))
        setattr(rupture,'hypo_depth', np.array([float(self.depth)]))
        if self.width is not None: setattr(rupture,'width',np.array([float(self.width)]))
        if self.ztor is not None: setattr(rupture,'ztor',      np.array([float(self.ztor)]))
        setattr(distances,'rhypo',np.array([float(Rhypo)]))
        if self.Rjb is not None: setattr(distances,'rjb',  np.array([float(self.Rjb)]))
        if self.Rrup is not None:  setattr(distances,'rrup', np.array([float(self.Rrup)]))
        if self.Rx   is not None: setattr(distances,'rx',   np.array([float(self.Rx)]))
        if self.Ry0  is not None: setattr(distances,'ry0',  np.array([float(self.Ry0)]))
        if self.repi is not None: setattr(distances,'repi', np.array([float(self.repi)]))
        if self.rvolc is not None: setattr(distances,'rvolc', np.array([float(self.rvolc)]))
        if self.rcdpp is not None: setattr(distances,'rcdpp', np.array([float(self.rcdpp)]))
        if self.clat is not None: setattr(distances,'clat', np.array([float(self.clat)]))
        if self.clon is not None: setattr(distances,'clon', np.array([float(self.clon)]))
        if self.azimuth is not None: setattr(distances,'azimuth', np.array([float(self.azimuth)]))
        #decomment to check in input
        #print ("Vs30",sites.vs30, "Z2500",sites.z2pt5, "Z1000", sites.z1pt0, "FlagVs30",sites.vs30measured)
        #print ("rake",rupture.rake, "dip", rupture.dip,"mag", rupture.mag, "ztor", rupture.ztor, "depth", rupture.hypo_depth)
        #print ("rhypo", distances.rhypo, "rjb", distances.rjb, "rrup", distances.rrup, "rx", distances.rx)

        return sites,rupture,distances


    def _get_gmpe_period_range(self, gmpe_inst):
        """Read the supported SA period range from the GMPE's COEFFS table."""
        coeffs = getattr(gmpe_inst, 'COEFFS', None)
        if coeffs is None:
            return 0.01, 10.0  # safe default if no COEFFS
        periods = []
        for key in coeffs:
            s = str(key)
            if s in ('PGA', 'PGV', 'PGD', 'CAV', 'IA', 'MMI'):
                continue
            if s.startswith('SA('):
                p = s.replace('SA(', '').replace(')', '')
                try:
                    periods.append(float(p))
                except ValueError:
                    pass
        if not periods:
            return 0.01, 10.0
        return min(periods), max(periods)


    def _get_gmpe_native_periods(self, gmpe_inst):
        """Read all SA periods the GMPE defines coefficients for (its native grid)."""
        coeffs = getattr(gmpe_inst, 'COEFFS', None)
        if coeffs is None:
            return None  # no COEFFS → cannot use native periods
        periods = []
        for key in coeffs:
            s = str(key)
            if s in ('PGA', 'PGV', 'PGD', 'CAV', 'IA', 'MMI'):
                continue
            if s.startswith('SA('):
                p = s.replace('SA(', '').replace(')', '')
                try:
                    periods.append(float(p))
                except ValueError:
                    pass
        if not periods:
            return None
        return np.array(sorted(periods))


    def computegmpe(self, gmpe, freq, mag, depth, Epi, vs30, **kwargs):
        from openquake.hazardlib import gsim, imt

        """
        :param gmpe : name of the GMPE on the bases of OQ GSIM list, type=str
        :param freq : target frequency array (Hz) — results are interpolated to this grid
        :param mag : event magnitude, type=float
        :param depth : event depth, type=float
        :param dip : fault dip, type=float
        :param rake : fault rake, type = float
        :param Rrup : distance from the rupture, type = float 
        :param Rjb : Joyner and Boore distance, type = float
        :param Epi : epicentral distance, type = float
        :param Vs30: velocity of S waves in first 30 meters, type =float

        Returns spectra interpolated to *freq* grid.
        """
        self.rake = None
        self.dip = None
        self.Rx = None
        self.Rjb = None
        self.Ry0 = None
        self.width = None
        self.ztor = None
        self.Rrup = None
        self.z1pt0 = None
        self.z2pt5 = None
        self.repi = None
        self.rvolc = None
        self.rcdpp = None
        self.clat = None
        self.clon = None
        self.azimuth = None
        self.vs30measured = None
        self.z1pt4 = None
        self.backarc = None
        self.region = 0
        for key in kwargs:
            if key == 'dip'        : self.dip        = kwargs[key]
            if key == 'rake'       : self.rake       = kwargs[key]
            if key == 'Rx'         : self.Rx         = kwargs[key]
            if key == 'Rjb'        : self.Rjb        = kwargs[key]
            if key == 'Ry0'        : self.Ry0        = kwargs[key]
            if key == 'width'      : self.width      = kwargs[key]
            if key == 'ztor'       : self.ztor       = kwargs[key]
            if key == 'Rrup'       : self.Rrup       = kwargs[key]
            if key == 'z1pt0'      : self.z1pt0      = kwargs[key]
            if key == 'z2pt5'      : self.z2pt5      = kwargs[key]
            if key == 'repi'       : self.repi       = kwargs[key]
            if key == 'rvolc'      : self.rvolc      = kwargs[key]
            if key == 'rcdpp'      : self.rcdpp      = kwargs[key]
            if key == 'clat'       : self.clat       = kwargs[key]
            if key == 'clon'       : self.clon       = kwargs[key]
            if key == 'azimuth'    : self.azimuth    = kwargs[key]
            if key == 'vs30measured': self.vs30measured = kwargs[key]
            if key == 'z1pt4'      : self.z1pt4      = kwargs[key]
            if key == 'backarc'    : self.backarc    = kwargs[key]
            if key == 'region'     : self.region     = kwargs[key]

        self.mag = mag
        self.depth = depth
        self.Epi = Epi
        self.vs30 = vs30

        AVAILABLE_GSIMS = gsim.get_available_gsims()
        gmpe_inst = AVAILABLE_GSIMS[gmpe]()

        # Use the GMPE's native periods (its COEFFS table) for computation,
        # then interpolate to the user's frequency grid.
        native_periods = self._get_gmpe_native_periods(gmpe_inst)
        if native_periods is None:
            # Fallback: use the user's frequency grid directly (no COEFFS)
            compute_periods = 1.0 / freq
        else:
            # Only keep periods within the user's requested range
            user_periods = 1.0 / freq
            p_min_user = user_periods.min()
            p_max_user = user_periods.max()
            mask = (native_periods >= p_min_user) & (native_periods <= p_max_user)
            compute_periods = native_periods[mask]
            if len(compute_periods) == 0:
                raise ValueError(
                    "GMPE '%s' native periods [%.4f, %.4f] s don't overlap "
                    "with user range [%.4f, %.4f] s"
                    % (gmpe, native_periods.min(), native_periods.max(),
                       p_min_user, p_max_user))

        pardist = gmpe_inst.REQUIRES_DISTANCES
        parzone = gmpe_inst.DEFINED_FOR_TECTONIC_REGION_TYPE
        zone = parzone.value

        sites, rupture, distances = self.read_gmpeinput()
        periods_entry = ["SA(%s)" % p for p in compute_periods]
        stddev = ['Total']

        output_mean = []
        output_sigma1m = []
        output_sigma1p = []
        for i_m in periods_entry:
            means, sigma = gmpe_inst.get_mean_and_stddevs(
                sites, rupture, distances, imt.from_string(i_m), stddev)
            output_mean.append(np.exp(means[0]))
            output_sigma1p.append(np.exp(means[0] + sigma[0][0]))
            output_sigma1m.append(np.exp(means[0] - sigma[0][0]))

        output_mean    = np.array(output_mean)
        output_sigma1p = np.array(output_sigma1p)
        output_sigma1m = np.array(output_sigma1m)

        # Return results at the native computation frequencies only —
        # each GMPE defines its own valid range, no extrapolation, no NaN.
        compute_freq = 1.0 / compute_periods
        # Ensure frequencies are in increasing order (native periods are
        # sorted increasingly, so 1/periods would be decreasing).
        if len(compute_freq) > 1 and compute_freq[0] > compute_freq[-1]:
            compute_freq = compute_freq[::-1]
            output_mean = output_mean[::-1]
            output_sigma1p = output_sigma1p[::-1]
            output_sigma1m = output_sigma1m[::-1]
        # Warn if user range extends beyond GMPE's native range
        f_min_gmpe = compute_freq.min()
        f_max_gmpe = compute_freq.max()
        if freq[0] < f_min_gmpe - 1e-6 or freq[-1] > f_max_gmpe + 1e-6:
            print("  ⚠ '%s' native range [%.4f, %.4f] Hz does not cover "
                  "user range [%.4f, %.4f] Hz — truncated to native range"
                  % (gmpe, f_min_gmpe, f_max_gmpe, freq[0], freq[-1]),
                  file=sys.stderr)
        return output_mean, output_sigma1m, output_sigma1p, pardist, zone, \
               compute_freq.tolist()

    def compute_batch(self, gmpe_list, freq, mag, depth, epi, vs30,
                      dip=90.0, rake=0.0, Rx=0.0, Rjb=None, Rrup=None, ztor=None,
                      width=None, z1pt0=None, z2pt5=None,
                      repi=None, rvolc=None, rcdpp=None,
                      clat=None, clon=None, azimuth=None,
                      vs30measured=None, z1pt4=None, backarc=None):
        """Compute multiple GMPEs and return JSON-serializable dict.

        Parameters
        ----------
        gmpe_list : list of str  — GMPE names (OQ GSIM keys)
        freq : np.ndarray — target frequency grid (Hz)
        mag, depth, epi, vs30 : float — event & site parameters
        dip, rake, Rx : float — fault parameters
        Rjb, Rrup, ztor : float or None — auto-computed if None
        width : float or None — rupture width, auto-computed if None
        z1pt0 : float or None — depth to 1.0 km/s (km), inferred from vs30 if None
        z2pt5 : float or None — depth to 2.5 km/s (km), inferred from z1pt0 if None
        repi : float or None — epicentral distance (km)
        rvolc, rcdpp, clat, clon, azimuth : float or None — distance metrics
        vs30measured : float or None — measured Vs30 flag (default 0)
        z1pt4 : float or None — depth to 1.4 km/s (km)
        backarc : float or None — back-arc flag (0/1)

        Returns
        -------
        dict with keys "results" and "errors".
        results[gname] = [mean_list, sig1m_list, sig1p_list, nat_freq_list]
        errors = [{"gmpe": gname, "error": str}, ...]
        """
        import math as _math
        import numpy as _np
        import sys as _sys

        # Auto-compute geometry if not provided
        if Rjb is None:
            Rjb = epi
        if width is None:
            if rake >= 30.0 and rake <= 150.0:
                width = 10 ** (-1.61 + 0.41 * mag)
            elif rake >= -120.0 and rake <= -60.0:
                width = 10 ** (-1.14 + 0.35 * mag)
            else:
                width = 10 ** (-0.76 + 0.27 * mag)
        if ztor is None or Rrup is None:
            if ztor is None:
                ztor = max(depth - 0.6 * width * _math.sin(_math.pi / 180 * dip), 0)
            if Rrup is None:
                Rrup = _np.sqrt(ztor ** 2 + Rjb ** 2)

        results = {}
        errors = []
        for gname in gmpe_list:
            try:
                mean, sig1m, sig1p, dist, zone, nat_freq = self.computegmpe(
                    gname, freq, mag, depth, epi, vs30,
                    dip=dip, rake=rake, Rx=Rx,
                    Rjb=Rjb, Rrup=Rrup, ztor=ztor,
                    width=width, z1pt0=z1pt0, z2pt5=z2pt5,
                    repi=repi, rvolc=rvolc, rcdpp=rcdpp,
                    clat=clat, clon=clon, azimuth=azimuth,
                    vs30measured=vs30measured, z1pt4=z1pt4,
                    backarc=backarc,
                )
                results[gname] = [mean.tolist(), sig1m.tolist(), sig1p.tolist(),
                                  nat_freq]
            except Exception as e:
                errors.append({"gmpe": gname, "error": str(e)})
                print("  \u2717 %s: %s" % (gname, e), file=_sys.stderr)
        if errors:
            print("  \u26a0 %d GMPE(s) failed" % len(errors), file=_sys.stderr)
        return {"results": results, "errors": errors}
