from Pyxis.ModSupport import *

# register ourselves with Pyxis and define the superglobals
#register_pyxis_module(superglobals="MS LSM OUTDIR DESTDIR")

register_pyxis_module('im')

# external tools  
define('IMAGER','lwimager','imager to use. Default is lwimager.')
define('LWIMAGER_PATH','lwimager','path to lwimager binary. Default is to look in the system PATH.')
define('WSCLEAN_PATH','wsclean','path to wsclean binary.')
define('MORESANE_PATH','runsane','path to PyMORESANE')
define('CASA_PATH','casapy','path to casapy')

# default clean algorithm
define("CLEAN_ALGORITHM","clark","CLEAN algorithm (clark, hogbom, csclean, etc.)")
define('DECONV_LABEL',None,'Label to identify images from different deconvolution algorithms. If set to True, name of algorithm will be used.')
# Default imaging colun
define('COLUMN','CORRECTED_DATA','default column to image')

# filenames for images
define("BASENAME_IMAGE_Template","${OUTFILE}${-<IMAGER}","default base name for all image filenames below")
define("DIRTY_IMAGE_Template", "${BASENAME_IMAGE}.dirty.fits","output filename for dirty image")
define("PSF_IMAGE_Template", "${BASENAME_IMAGE}.psf.fits","output filename for psf image")
define("RESTORED_IMAGE_Template", "${BASENAME_IMAGE}${-<DECONV_LABEL}.restored.fits","output filename for restored image")
define("RESIDUAL_IMAGE_Template", "${BASENAME_IMAGE}${-<DECONV_LABEL}.residual.fits","output filename for deconvolution residuals")
define("MODEL_IMAGE_Template", "${BASENAME_IMAGE}${-<DECONV_LABEL}.model.fits","output filename for deconvolution model")
define("FULLREST_IMAGE_Template", "${BASENAME_IMAGE}${-<DECONV_LABEL}.fullrest.fits","output filename for LSM-restored image")
define("MASK_IMAGE_Template", "${BASENAME_IMAGE}.mask.fits","output filename for CLEAN mask")

# How to channelize the output image. 0 for average all, 1 to include all, 2 to average with a step of 2, etc.
# None means defer to 'imager' module options
define("IMAGE_CHANNELIZE",0,"image channels selection: 0 for all, 1 for per-channel cube")
# passed to tigger-restore when restoring models into images. Use e.g. "-b 45" for a 45" restoring beam.
define("RESTORING_OPTIONS","","extra options to tigger-restore for LSM-restoring")

# Standard imaging options
DOUBLE_PSF = True
ifrs = ""
npix = 1024
cellsize = "2arcsec"
mode = "channel"
stokes = "IQUV"
weight = "briggs"
robust = 0
niter = 1000
gain = .1
threshold = 0
wprojplanes = 0
cachesize = 4096
fixed = 0
# rescale images by factor
flux_rescale=1
# use velocity rather than frequency
velocity = False 
no_weight_fov = False

# import wsclean
# import lwimager
# import casa
# import moresane

def make_image (*args,**kw):
  imager = kw.get('imager', IMAGER).lower();
  imgmod = "im."+imager;
  try:
    mod = getattr(__import__(imgmod),imager);
  except:
    traceback.print_exc();
    abort("import $imgmod failed")
  call_imager = getattr(mod,'make_image',None);
  if not callable(call_imager):
    abort("$imgmod does not provide a make_image() function");
  call_imager(*args,**kw);

