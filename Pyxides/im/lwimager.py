"""Pyxis module fo0r MS-related operations""";
from Pyxis.ModSupport import *

import pyrap.images
import os
import subprocess
import pyfits
import argo

import mqt
import ms
import std
import im
import numpy 
# register ourselves with Pyxis and define the superglobals
register_pyxis_module(superglobals="MS LSM DESTDIR");

v.define("LSM","lsm.lsm.html","""current local sky model""");
  
# external tools  
define('LWIMAGER_PATH','lwimager','path to lwimager binary. Default is to look in the system PATH.');

define('IMAGER','lwimager','Imager name')

# dict of known lwimager arguments, by version number
# this is to accommodate newer versions
_lwimager_known_args = {
  0:set(("ms spwid field prior image model restored residual data mode filter nscales weight weight_fov noise robust wprojplanes padding "+
    "cachesize stokes nfacets npix cellsize phasecenter field spwid chanmode nchan chanstart chanstep img_nchan img_chanstart img_chanstep "+
    "select operation niter gain threshold targetflux sigma fixed constrainflux prefervelocity mask maskblc masktrc uservector maskvalue").split(" ")),
  1003001:set(["fillmodel"])
};

# whenever the path changes, find out new version number, and build new set of arguments
_lwimager_path_version = None,None;
def LWIMAGER_VERSION_Template ():
  global _lwimager_path_version,_lwimager_args;
  if LWIMAGER_PATH != _lwimager_path_version[0]:
    _lwimager_path_version = LWIMAGER_PATH,lwimager_version();
    _lwimager_args = set();
    for version,args in _lwimager_known_args.iteritems():
      if version <= _lwimager_path_version[1][0]:
        _lwimager_args.update(args); 
  return _lwimager_path_version[1];

rm_fr = x.rm.args("-fr");
tigger_restore = x("tigger-restore");

imagecalc = x("imagecalc");

def STANDARD_IMAGING_OPTS_Template():
    global npix,cellsize,mode,stokes,weight,robust,niter,gain,threshold
    global wprojplanes,cachesize,ifrs,fixed,flux_rescale,velocity,no_weight_fov
    npix = im.npix
    cellsize = im.cellsize
    mode = im.mode
    stokes = im.stokes
    weight = im.weight
    robust = im.robust
    niter = im.niter
    gain = im.gain
    threshold = im.threshold
    wprojplanes = im.wprojplanes
    cachesize = im.cachesize
    ifrs = im.ifrs
    fixed = im.fixed
    # rescale images by factor
    flux_rescale= im.flux_rescale
    # use velocity rather than frequency
    velocity = im.velocity
    no_weight_fov = im.no_weight_fov

# known lwimager args -- these will be passed from keywords
_fileargs = set("image model restored residual".split(" ")); 


def _run (convert_output_to_fits=True,lwimager_path="$LWIMAGER_PATH",**kw):
  # look up lwimager
  lwimager_path = interpolate_locals("lwimager_path");
  lwimager_path = argo.findImager(lwimager_path)
  # make dict of imager arguments that have been specified globally or locally
  args = dict([ (arg,globals()[arg]) for arg in _lwimager_args if arg in globals() and globals()[arg] is not None ]);
  args.update([ (arg,kw[arg]) for arg in _lwimager_args if arg in kw ]);
  if no_weight_fov:
    args.pop('weight_fov',0);
  # add ifrs, spwid and field arguments
  ms.IFRS is not None and args.setdefault('ifrs',ms.IFRS);
  ms.DDID is not None and args.setdefault('spwid',ms.DDID);
  ms.FIELD is not None and args.setdefault('field',ms.FIELD);
  # have an IFR subset? Parse that too
  msname,ifrs = kw['ms'],args.pop('ifrs',None);
  if ifrs and ifrs.lower() != "all":
    import Meow.IfrSet
    subset = Meow.IfrSet.from_ms(msname).subset(ifrs).taql_string();
    args['select'] = "(%s)&&(%s)"%(args['select'],subset) if 'select' in args else subset;
  # make image names
  fitsfiles = {};
  for arg in _fileargs:
    if arg in args:
      if not args[arg].endswith(".img"):
        fitsfiles[arg] = args[arg];
        args[arg] = args[arg]+".img";
  # run the imager
  x.time("$lwimager_path",**args);
  # convert CASA images to FITS
  if convert_output_to_fits:
    fs = kw.get('flux_rescale') or flux_rescale;
    velo = kw.get('velocity') or velocity;
    for arg in _fileargs:
      if arg in fitsfiles:
        im = pyrap.images.image(args[arg]);
        if fs and fs != 1:
          im.putdata(fs*im.getdata());
        im.tofits(fitsfiles[arg],overwrite=True,velocity=velo);  
        subprocess.call("rm -fr "+args[arg],shell=True);

def lwimager_version (path="$LWIMAGER_PATH"):
  """Determines lwimager version, returns tuple of xxxyyyzzz,tail, where 
  xxx,yyy,zzz is major, minor, patch numbers, while tail is the rest of 
  the version string. Takes into account idiosyncarsies of older lwimager
  version strings, so for example:
            1003001,"" (for 1.3.1)
            1002001,"20120223-OMS" (for 1.2.1-20120223-OMS)
            1003000,"20130816-OMS" (for 20130816-OMS which is really 1.3.0)
  """
  path = interpolate_locals("path");
  try:
    vstr = subprocess.Popen([path,"--version"],stderr=subprocess.PIPE).stderr.read().strip().split()[-1];
  except:
    return 0,"";
  if '.' in vstr:
    major,minor,patch = vstr.split('.')
    patch,tail = patch.split("-",1) if "-" in patch else (patch,"");
  else:
    major,minor,patch,tail = 1,3,0,vstr;
  try:
    major,minor,patch = map(int,[major,minor,patch]);
  except:
    major,minor,patch,tail = 0,0,0,vstr;
  info("$path version is $major.$minor.$patch${-<tail}")
  return major*1000000+minor*1000+patch,tail;

def make_image (msname="$MS",column="${im.COLUMN}",imager='$IMAGER',
                dirty=True,restore=False,restore_lsm=True,psf=False,
                dirty_image="${im.DIRTY_IMAGE}",
                restored_image="${im.RESTORED_IMAGE}",
                residual_image="${im.RESIDUAL_IMAGE}",
                psf_image="${im.PSF_IMAGE}",
                model_image="${im.MODEL_IMAGE}",
                fullrest_image="${im.FULLREST_IMAGE}",
                restoring_options="${im.RESTORING_OPTIONS}",
                algorithm="${im.CLEAN_ALGORITHM}",
                channelize=None,lsm="$LSM",
                double_psf=None,**kw0):
  """Makes image(s) from MS. Set dirty and restore to True or False to make the appropriate images. You can also
  set either to a dict of options to be passed to the imager. If restore=True and restore_lsm is True and 'lsm' is set, 
  it will also make a full-restored image (i.e. will restore the LSM into the image) with tigger-restore. Use this when 
  deconvolving residual images. Note that RESTORING_OPTIONS are passed to tigger-restore.
  
  'channelize', if set, overrides the IMAGE_CHANNELIZE setting. If both are None, the options in the 'imager' module take effect.
  
  'algorithm' is the deconvolution algorithm to use (hogbom, clark, csclean, multiscale, entropy) 
  
  'dirty_image', etc. sets the image names, with defaults determined by the globals DIRTY_IMAGE, etc.
  """;
  
  im.IMAGER = II(imager)
  # retain lwimager label for dirty maps and psf_maps
  #Add algorithm label if required
  if im.DECONV_LABEL and restore:
    if isinstance(im.DECONV_LABEL,bool):
      if im.DECONV_LABEL:
        im.DECONV_LABEL = algorithm
  elif im.DECONV_LABEL is False:
    im.DECONV_LABEL = None

  do_moresane = False
  if algorithm.lower() in ['moresane','pymoresane']:
      from im import moresane
      do_moresane = True

  imager,msname,column,lsm,dirty_image,psf_image,restored_image,residual_image,model_image,algorithm,\
     fullrest_image,restoring_options,double_psf = \
     interpolate_locals("imager msname column lsm dirty_image psf_image restored_image "
                        "residual_image model_image algorithm fullrest_image restoring_options double_psf");
  makedir('$DESTDIR');
  if restore and column != "CORRECTED_DATA":
    abort("Due to imager limitations, restored images can only be made from the CORRECTED_DATA column.");

  # setup imager options
  kw0.update(dict(chanstart=ms.CHANSTART,chanstep=ms.CHANSTEP,nchan=ms.NUMCHANS));
  if 'img_nchan' not in kw0 or 'img_chanstart' not in kw0:
    if channelize is None:
      channelize = im.IMAGE_CHANNELIZE;
    if channelize == 0:
      kw0.update(img_nchan=1,img_chanstart=ms.CHANSTART,img_chanstep=ms.NUMCHANS);
    elif channelize > 0:
      kw0.update(img_nchan=ms.NUMCHANS//channelize,img_chanstart=ms.CHANSTART,img_chanstep=channelize);
  
  kw0.update(ms=msname,data=column);

  def make_dirty(**kw1):
    info("im.lwimager.make_image: making dirty image $dirty_image");
    kw = kw0.copy();
    if type(dirty) is dict:
      kw.update(dirty);
    kw.update(kw1)
    kw['operation'] = 'image';
    _run(image=dirty_image,**kw);

  if dirty: make_dirty()

  def make_psf(**kw1):
    info("im.lwimager.make_image: making PSF image $psf_image");
    kw = kw0.copy();
    if type(psf) is dict:
      kw.update(psf);
    kw['operation'] = 'image';
    kw['data'] = 'psf';
    kw['stokes'] = "I";
    kw.update(kw1)
    _run(image=psf_image,**kw);
  if psf: make_psf()

  if do_moresane and restore:
    # Moresane does better with a double sized PSF
    double_psf = double_psf or im.DOUBLE_PSF
    if double_psf: 
        _npix = int(npix)*2 if 'npix' not in kw0.keys() else (kw0['npix'])*2
        make_psf(npix=_npix)
    elif not psf: 
         make_psf()
    if not dirty: make_dirty()  
    opts = restore if isinstance(restore,dict) else {}
    moresane.deconv(dirty_image,psf_image,model_image=model_image,
                       residual_image=residual_image,restored_image=restored_image,**opts)
  elif restore:
    info("im.lwimager.make_image: making restored image $restored_image");
    info("                   (model is $model_image, residual is $residual_image)");
    kw = kw0.copy();
    if type(restore) is dict:
      kw.update(restore);
    kw.setdefault("operation",algorithm or "clark");
    temp_images = [];
    ## if fixed model was specified as a fits image, convert to CASA image
    if kw.pop('fixed',None):
      kw['fixed'] = 1;
      if not os.path.exists(model_image):
        warn("fixed=1 (use prior model) specified, but $model_image does not exist, ignoring"); 
      elif not os.path.isdir(model_image):
        info("converting prior model $model_image into CASA image");
        modimg = model_image+".img";
        temp_images.append(modimg);
        argo.fits2casa(model_image,modimg);
        model_image = modimg;
    ## if mask was specified as a fits image, convert to CASA image
    mask = kw.get("mask");
    if mask and not isinstance(mask,str):
      kw['mask'] = mask = MASK_IMAGE; 
    imgmask = None;
    if mask and os.path.exists(mask) and not os.path.isdir(mask):
      info("converting clean mask $mask into CASA image");
      kw['mask'] = imgmask = mask+".img";
      argo.fits2casa(mask,imgmask);
      temp_images.append(imgmask);
    ## run the imager
    _run(restored=restored_image,model=model_image,residual=residual_image,**kw)
    ## delete CASA temp images if created above
    for img in temp_images:
      rm_fr(img);
  if restore:
    if lsm and restore_lsm:
      info("Restoring LSM into FULLREST_IMAGE=$fullrest_image");
      opts = restore_lsm if isinstance(restore_lsm,dict) else {};
      tigger_restore(restoring_options,"-f",restored_image,lsm,fullrest_image,kwopt_to_command_line(**opts));
      
document_globals(make_image,"im.*_IMAGE COLUMN im.IMAGE_CHANNELIZE MS im.RESTORING_OPTIONS im.CLEAN_ALGORITHM ms.IFRS ms.DDID ms.FIELD ms.CHANRANGE");      

def predict_vis (msname="$MS",image="${im.MODEL_IMAGE}",column="MODEL_DATA",channelize=None,
  copy=False,copyto="$COPY_IMAGE_TO",**kw0):
  """Converts image into predicted visibilities"""
  msname,image,column,copyto = interpolate_locals("msname image column copyto");
  
  if LWIMAGER_VERSION[0] in (1003000,1003001):
    abort("lwimager 1.3.%d cannot be used to predict visibilities. Try lwimager-1.2, or upgrade to 1.3.2 or higher"%(LWIMAGER_VERSION[0]%1000))
  
#  # copy data into template, if specified
#  if copy:
#    ff0 = pyfits.open(image);
#    info("copying image data from $image to $copyto");
#    npix = ff0[0].header['NAXIS1'];
#    cell = "%fdeg"%abs(ff0[0].header['CDELT1']);
#    make_empty_image(msname,copyto,channelize=channelize,npix=npix,cellsize=cell);
#    data = ff0[0].data;
#    ff1 = pyfits.open(copyto);
#    ff1[0].data[0:data.shape[0],...] = data;
#    ff1.writeto(copyto,clobber=True);
  
  # convert to CASA image
  casaimage = II("${MS:BASE}.predict_vis.img");
  argo.fits2casa(image,casaimage);
  
  # setup channelize options
  if 'img_nchan' not in kw0 or 'img_chanstart' not in kw0:
    if channelize is None:
      channelize = im.IMAGE_CHANNELIZE
    if channelize == 0:
      kw0.update(img_nchan=1,img_chanstart=ms.CHANSTART,img_chanstep=ms.NUMCHANS);
    elif channelize > 0:
      kw0.update(img_nchan=ms.NUMCHANS//channelize,img_chanstart=ms.CHANSTART,img_chanstep=channelize);

  # setup imager options
  kw0.setdefault("weight","natural");
  kw0.update(ms=msname,niter=0,fixed=1,mode="channel",operation="csclean",model=casaimage,
             chanstart=ms.CHANSTART,chanstep=ms.CHANSTEP,nchan=ms.NUMCHANS);
  if LWIMAGER_VERSION[0] >= 1003001:
    kw0['fillmodel'] = 1;
  info("Predicting visibilities from $image into MODEL_DATA");
  _run(**kw0);
  rm_fr(casaimage);
  
  if column != "MODEL_DATA":
    ms.copycol(msname=msname,fromcol="MODEL_DATA",tocol=column);

document_globals(predict_vis,"MS im.MODEL_IMAGE COPY_IMAGE_TO ms.IFRS ms.DDID ms.FIELD ms.CHANRANGE");      

def make_psf (msname="$MS",**kw):
  """Makes an image of the PSF. All other arguments as per make_image()."""
  make_image(msname,dirty=False,psf=True,**kw);
