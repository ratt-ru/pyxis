from Pyxis.ModSupport import *

import ms
import mqt
import imager
import std

from astropy.io import fits as pyfits

# register ourselves with Pyxis, and define what superglobals we use (these come from ms)
register_pyxis_module(superglobals="MS LSM DESTDIR OUTFILE");
  