from Pyxis.ModSupport import *

register_pyxis_module(superglobals="MS LSM DESTDIR");
v.define("LSM","lsm.lsm.html","""current local sky model""");

# external tools  
define('IMAGER','lwimager','Imager to user. Default is lwimager.');
define('LWIMAGER_PATH','lwimager','path to lwimager binary. Default is to look in the system PATH.');
define('WSCLEAN_PATH','{im.WSCLEAN_PATH}','path to lwimager binary. Default is to look in the system PATH.');
define('MORESANE_PATH','{im.MORESANE_PATH}','path to lwimager binary. Default is to look in the system PATH.');

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
                fullrest_image='${FULLREST_IMAGE}',
                restoring_options='${RESTORING_OPTIONS}',
                channelize=None,lsm="$LSM",**kw0):
    """Makes image(s) from MS. Set dirty and restore to True or False to make the appropriate images. You can also
    set either to a dict of options to be passed to the imager. If restore=True and restore_lsm is True and 'lsm' is set, 
    it will also make a full-restored image (i.e. will restore the LSM into the image) with tigger-restore. Use this when 
    deconvolving residual images. Note that RESTORING_OPTIONS are passed to tigger-restore.
  
    'channelize', if set, overrides the IMAGE_CHANNELIZE setting. If both are None, the options in the 'imager' module take effect.
  
    'algorithm' is the deconvolution algorithm to use (hogbom, clark, csclean, multiscale, entropy) 
  
    'dirty_image', etc. sets the image names, with defaults determined by the globals DIRTY_IMAGE, etc.
    """

    global IMAGER
    IMAGER =  II(imager)
    imager,msname,column,lsm,dirty_image,psf_image,restored_image,residual_image,model_image,algorithm,fullrest_image,restoring_options = \
interpolate_locals("imager msname column lsm dirty_image psf_image \
restored_image residual_image model_image algorithm fullrest_image restoring_options")
    

    makedir('$DESTDIR')
    if imager in ['lwimager','wsclean']:
        __import__('im.%s'%imager.lower());
        call_imager = eval( 'im.%s.make_image'%(imager.lower()) )
    else: 

        abort('Uknown imager: $imager')
    if MORESANE_PATH != '{im.MORESANE_PATH}':
       im.MORESANE_PATH = MORESANE_PATH
    if WSCLEAN_PATH != '{im.WSCLEAN_PATH}':
       im.WSCLEAN_PATH = WSCLEAN_PATH
    # make dict of imager arguments that have been specified globally or locally
    args_to_parse = 'npix weight robust stokes field no_weight_fov ifrs gain niter cachesize mode wprojplanes threshold cellsize'.split()
    kw = dict([ (arg,globals()[arg]) for arg in args_to_parse if arg in globals() and globals()[arg] is not None ])
    kw.update( pol=stokes,scale=im.argo.toDeg(cellsize),size='%d %d'%(npix,npix) )
    if imager == 'wsclean':
        kw.update(weight='%s %.2f'%(weight,robust) if weight=='briggs' else weight)
        if isinstance(threshold,str):
            kw.update(threshold=im.argo.toJy(threshold))
    kw.update([ (arg,kw[arg]) for arg in args_to_parse if arg in kw0 ])
    kw.update(**kw0)

    call_imager(msname,column=column,dirty=dirty,restore_lsm=restore_lsm,restore=restore,
                psf=psf,dirty_image=dirty_image,restored_image=restored_image,
                psf_image=psf_image,model_image=model_image,algorithm=algorithm,
                channelize=channelize,lsm=lsm,fullrest_image=fullrest_image,
                restoring_options=restoring_options,**kw)
    
document_globals(make_image,"*_IMAGE IMAGER COLUMN IMAGE_CHANNELIZE MS RESTORING_OPTIONS CLEAN_ALGORITHM ms.IFRS ms.DDID ms.FIELD ms.CHANRANGE")

def make_threshold_mask (input="$RESTORED_IMAGE",threshold=0,output="$MASK_IMAGE",high=1,low=0):
    """Makes a mask image by thresholding the input image at a given value. The output image is a copy of the input image,
    with pixel values of 'high' (1 by default) where input pixels are >= threshold, and 'low' (0 default) where pixels are <threshold.
    """
    input,output = interpolate_locals("input output");
    im.argo.make_threshold_mask(input=input,threshold=threshold,output=output,high=high,low=low)

document_globals(make_threshold_mask,"RESTORED_IMAGE MASK_IMAGE")

def predict_vis (msname="$MS",image="$MODEL_IMAGE",column="MODEL_DATA",channelize=None,
  copy=False,copyto="$COPY_IMAGE_TO",**kw0):
    """Converts image into predicted visibilities"""
    
    import im.lwimager

    msname,image,column,copyto = interpolate_locals("msname image column copyto")

    im.lwimager.predict_vis(msname=msname,image=image,column=column,channelize=channelize,
                            copy=copy,copyto=copyto,**kw0)

document_globals(predict_vis,"MS MODEL_IMAGE COPY_IMAGE_TO ms.IFRS ms.DDID ms.FIELD ms.CHANRANGE");

define("COPY_IMAGE_TO_Template", "${MS:BASE}.imagecopy.fits","container for image copy")
def make_empty_image (msname="$MS",image="${COPY_IMAGE_TO}",channelize=None,**kw0):
    msname,image = interpolate_locals("msname image")
    im.argo.make_empty_image(msname=msname,imagename=image,channelize=channelize,**kw0)

def make_psf (msname="$MS",**kw):
    """Makes an image of the PSF. All other arguments as per make_image()."""

    make_image(msname,dirty=False,psf=True,**kw)
