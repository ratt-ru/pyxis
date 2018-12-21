from Pyxis.ModSupport import *

from . import ms
from . import mqt
from . import imager
from . import std

from astropy.io import fits as pyfits

# register ourselves with Pyxis, and define what superglobals we use (these come from ms)
register_pyxis_module(superglobals="MS LSM DESTDIR OUTFILE");
  