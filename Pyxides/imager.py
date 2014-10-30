import ms  
import im 

from Pyxis.ModSupport import *

register_pyxis_module(superglobals="MS LSM DESTDIR");
v.define("LSM","lsm.lsm.html","""current local sky model""");

# external tools  
define('IMAGER','lwimager','Imager to user. Default is lwimager.');
define('LWIMAGER_PATH','lwimager','path to lwimager binary. Default is to look in the system PATH.');

define('COLUMN','CORRECTED_DATA','default column to image');

# standard imaging options 
ifrs=""
npix=2048
cellsize="8arcsec"
mode="channel"
stokes="IQUV"
weight="briggs"
robust=0
wprojplanes=0
cachesize=4096
niter=1000
gain=.1
threshold=0
fixed=0

# rescale images by factor
flux_rescale=1

# use velocity rather than frequency
velocity = False;

no_weight_fov = False

# filenames for images
define("BASENAME_IMAGE_Template","${OUTFILE}${-<IMAGER}","default base name for all image filenames below");
define("DIRTY_IMAGE_Template", "${BASENAME_IMAGE}.dirty.fits","output filename for dirty image");
define("PSF_IMAGE_Template", "${BASENAME_IMAGE}.psf.fits","output filename for psf image");
define("RESTORED_IMAGE_Template", "${BASENAME_IMAGE}.restored.fits","output filename for restored image");
define("RESIDUAL_IMAGE_Template", "${BASENAME_IMAGE}.residual.fits","output filename for deconvolution residuals");
define("MODEL_IMAGE_Template", "${BASENAME_IMAGE}.model.fits","output filename for deconvolution model");
define("FULLREST_IMAGE_Template", "${BASENAME_IMAGE}.fullrest.fits","output filename for LSM-restored image");
define("MASK_IMAGE_Template", "${BASENAME_IMAGE}.mask.fits","output filename for CLEAN mask");

# How to channelize the output image. 0 for average all, 1 to include all, 2 to average with a step of 2, etc.
# None means defer to 'imager' module options
define("IMAGE_CHANNELIZE",0,"image channels selection: 0 for all, 1 for per-channel cube")
# passed to tigger-restore when restoring models into images. Use e.g. "-b 45" for a 45" restoring beam.
define("RESTORING_OPTIONS","","extra options to tigger-restore for LSM-restoring")
# default clean algorithm
define("CLEAN_ALGORITHM","clark","CLEAN algorithm (clark, hogbom, csclean, etc.)")

def fits2casa (input,output):
    """Converts FITS image to CASA image."""
    im.argo.fits2casa(input,output)

def make_image (msname="$MS",column="$COLUMN",imager='$IMAGER',
                dirty=True,restore=False,restore_lsm=True,psf=False,
                dirty_image="$DIRTY_IMAGE",
                restored_image="$RESTORED_IMAGE",
                residual_image="$RESIDUAL_IMAGE",
                psf_image="$PSF_IMAGE",
                model_image="$MODEL_IMAGE",
                algorithm="$CLEAN_ALGORITHM",
                channelize=None,lsm="$LSM",**kw0):
    """Makes image(s) from MS. Set dirty and restore to True or False to make the appropriate images. You can also
    set either to a dict of options to be passed to the imager. If restore=True and restore_lsm is True and 'lsm' is set, 
    it will also make a full-restored image (i.e. will restore the LSM into the image) with tigger-restore. Use this when 
    deconvolving residual images. Note that RESTORING_OPTIONS are passed to tigger-restore.
  
    'channelize', if set, overrides the IMAGE_CHANNELIZE setting. If both are None, the options in the 'imager' module take effect.
  
    'algorithm' is the deconvolution algorithm to use (hogbom, clark, csclean, multiscale, entropy) 
  
    'dirty_image', etc. sets the image names, with defaults determined by the globals DIRTY_IMAGE, etc.
    """

    imager,msname,column,lsm,dirty_image,psf_image,restored_image,residual_image,model_image,algorithm = \
interpolate_locals("imager msname column lsm dirty_image psf_image \
restored_image residual_image model_image algorithm")

    makedir('$DESTDIR')
    if imager in ['lwimager','wsclean']:
        call_imager = eval( 'im.%s.make_image'%(imager.lower()) )
    else: 

        abort('Uknown imager: $imager')
    call_imager(msname,column=column,dirty=dirty,restore_lsm=restore_lsm,
                psf=psf,dirty_image=dirty_image,restored_image=restored_image,
                psf_image=psf_image,model_image=model_image,algorithm=algorithm,
                channelize=channelize,lsm=lsm,**kw0)
    
document_globals(make_image,"*_IMAGE IMAGER COLUMN IMAGE_CHANNELIZE MS RESTORING_OPTIONS CLEAN_ALGORITHM ms.IFRS ms.DDID ms.FIELD ms.CHANRANGE")

def make_threshold_mask (input="$RESTORED_IMAGE",threshold=0,output="$MASK_IMAGE",high=1,low=0):
    """Makes a mask image by thresholding the input image at a given value. The output image is a copy of the input image,
    with pixel values of 'high' (1 by default) where input pixels are >= threshold, and 'low' (0 default) where pixels are <threshold.
    """
    input,output = interpolate_locals("input output");
    im.lwimager.make_threshold_mask(input=input,threshold=threshold,output=output,high=high,low=low)

document_globals(make_threshold_mask,"RESTORED_IMAGE MASK_IMAGE")

def predict_vis (msname="$MS",image="$MODEL_IMAGE",column="MODEL_DATA",channelize=None,
  copy=False,copyto="$COPY_IMAGE_TO",**kw0):
    """Converts image into predicted visibilities"""

    msname,image,column,copyto = interpolate_locals("msname image column copyto")

    im.lwimager.predict_vis(msname=msname,image=image,column=column,channelize=channelize,
                            copy=copy,copyto=copyto,**kw0)

document_globals(predict_vis,"MS MODEL_IMAGE COPY_IMAGE_TO ms.IFRS ms.DDID ms.FIELD ms.CHANRANGE");

def make_psf (msname="$MS",**kw):
    """Makes an image of the PSF. All other arguments as per make_image()."""

    make_image(msname,dirty=False,psf=True,**kw)
