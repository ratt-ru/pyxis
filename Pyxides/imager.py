"""Pyxis module for MS-related operations""";
from Pyxis.ModSupport import *

import pyrap.images
import os
import subprocess
import pyfits

import mqt,ms,std
 
# register ourselves with Pyxis and define the superglobals
register_pyxis_module(superglobals="MS LSM DESTDIR");

v.define("LSM","lsm.lsm.html","""current local sky model""");
  
# external tools  
define('LWIMAGER_PATH','lwimager','path to lwimager binary. Default is to look in the system PATH.');

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

# standard imaging options 
ifrs=""
npix=2048
cellsize="8arcsec"
mode="channel"
stokes="IQUV"
weight="briggs"
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

# known lwimager args -- these will be passed from keywords
_fileargs = set("image model restored residual".split(" ")); 


def _run (convert_output_to_fits=True,lwimager_path="$LWIMAGER_PATH",**kw):
  # look up lwimager
  lwimager_path = interpolate_locals("lwimager_path");
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
  vstr = subprocess.Popen([path,"--version"],stderr=subprocess.PIPE).stderr.read().strip().split()[-1];
  if '.' in vstr:
    major,minor,patch = vstr.split('.')
    patch,tail = patch.split("-",1) if "-" in patch else (patch,"");
  else:
    major,minor,patch,tail = 1,3,0,vstr;
  try:
    major,minor,patch = map(int,[major,minor,patch]);
  except:
    major,minor,patch,tail = 0,0,0,vstr;
  info("$path version is $major.$minor.$patch-$tail")
  return major*1000000+minor*1000+patch,tail;

      
# filenames for images
define("BASENAME_IMAGE_Template","${OUTFILE}","default base name for all image filenames below");
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
  """Converts FITS image to CASA image.""";
  for char in "/-*+().":
    input = input.replace(char,"\\"+char);
  if exists(output):
    rm_fr(output);
  imagecalc("in=$input out=$output");

#----------------------------- MORESANE WRAP ---------------------------
define('MORESANE_PATH_Template','${MORESANE_PATH}','Path to PyMORESANE')
_moresane_args = {'singlerun': False,\
'subregion': 0,\
'scalecount': 0,\
'startscale': 1,\
'stopscale': 20,\
'sigmalevel': 4,\
'loopgain': 0.2,\
'tolerance': 0.75,\
'accuracy': 1e-6,\
'majorloopmiter': 100,\
'minorloopmiter': 50,\
'allongpu': False,\
'decommode': 'ser',\
'corecount': 1,\
'convdevice': 'cpu',\
'convmode': 'circular',\
'extractionmode': 'cpu',\
'enforcepositivity': False,\
'edgesupression': False,\
'edgeoffset': 0}

def run_moresane(dirty_image,psf_image,threshold=3.0,image_prefix='${OUTFILE}',moresane_path='$MORESANE_PATH',**kw):
  """ Runs PyMORESANE """
  outfile,moresane_path = interpolate_locals('image_prefix moresane_path') 
  # Check if PyMORESANE exists
  if not os.path.exists(MORESANE_PATH): abort('Could not find PyMORESANE at $moresane_path')
  # Make sure that all options passed into moresane are known
  unknown = []
  if len(kw)>0:
    for arg in kw.keys():
      if arg not in _moresane_args.keys(): uknown.append(arg)
    if len(unknown)>0: abort('The follwing options passed into PyMORESANE could not be recognised:\n $unknown \n')
  # Update deconvolution threshold
  if 'sigmalevel' not in kw: _moresane_args['sigmalevel'] = threshold
  else: _moresane_args['sigmalevel'] = kw['sigmalevel']
   
  # Construct PyMORESANE run command
  run_cmd = 'python %s '%moresane_path
  for key,val in _moresane_args .iteritems():
    if type(val) is bool:
      if val: run_cmd+='--%s=%s '%(key,val)
    else: run_cmd+='--%s=%s '%(key,val)
  run_cmd += '%s %s %s'%(dirty_image,psf_image,outfile+'.fits')
  x.sh(run_cmd)
  #abort('>>> $run_cmd')
  
#--------------------------------------------------------------------------------
def make_image (msname="$MS",column="$COLUMN",
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
  """;
  msname,column,lsm,dirty_image,psf_image,restored_image,residual_image,model_image,algorithm = \
    interpolate_locals("msname column lsm dirty_image psf_image restored_image residual_image model_image algorithm"); 
  makedir(DESTDIR);
  
  if restore and column != "CORRECTED_DATA":
    abort("Due to imager limitations, restored images can only be made from the CORRECTED_DATA column.");
  
  # setup imager options
  kw0.update(dict(chanstart=ms.CHANSTART,chanstep=ms.CHANSTEP,nchan=ms.NUMCHANS));
  if 'img_nchan' not in kw0 or 'img_chanstart' not in kw0:
    if channelize is None:
      channelize = IMAGE_CHANNELIZE;
    if channelize == 0:
      kw0.update(img_nchan=1,img_chanstart=ms.CHANSTART,img_chanstep=ms.NUMCHANS);
    elif channelize > 0:
      kw0.update(img_nchan=ms.NUMCHANS//channelize,img_chanstart=ms.CHANSTART,img_chanstep=channelize);
    
  kw0.update(ms=msname,data=column);

  def make_dirty_image():
    info("imager.make_image: making dirty image $dirty_image");
    kw = kw0.copy();
    if type(dirty) is dict:
      kw.update(dirty);
    kw['operation'] = 'image';
    _run(image=dirty_image,**kw);

  if dirty: make_dirty_image()

  def make_psf():
    info("imager.make_image: making PSF image $psf_image");
    kw = kw0.copy();
    if type(psf) is dict:
      kw.update(psf);
    kw['operation'] = 'image';
    kw['data'] = 'psf';
    kw['stokes'] = "I";
    _run(image=psf_image,**kw);

  if psf: make_psf()

  if algorithm=='moresane' and restore:
    if not os.path.exists(psf_image): make_psf()
    if not os.path.exists(dirty_image): make_dirty_image()  
    if type(restore) is dict:
      run_moresane(dirty_image,psf_image,**restore)
    elif restore==True: 
      run_moresane(dirty_image,psf_image)
    else: abort('restore has to be either a dictionary or a boolean')
  elif restore:
    info("imager.make_image: making restored image $RESTORED_IMAGE");
    info("                   (model is $MODEL_IMAGE, residual is $RESIDUAL_IMAGE)");
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
        fits2casa(model_image,modimg);
        model_image = modimg;
    ## if mask was specified as a fits image, convert to CASA image
    mask = kw.get("mask");
    if mask and not isinstance(mask,str):
      kw['mask'] = mask = MASK_IMAGE; 
    imgmask = None;
    if mask and os.path.exists(mask) and not os.path.isdir(mask):
      info("converting clean mask $mask into CASA image");
      kw['mask'] = imgmask = mask+".img";
      fits2casa(mask,imgmask);
      temp_images.append(imgmask);
    ## run the imager
    _run(restored=restored_image,model=model_image,residual=residual_image,**kw)
    ## delete CASA temp images if created above
    for img in temp_images:
      rm_fr(img);
    if lsm and restore_lsm:
      info("Restoring LSM into FULLREST_IMAGE=$FULLREST_IMAGE");
      opts = restore_lsm if isinstance(restore_lsm,dict) else {};
      tigger_restore("$RESTORING_OPTIONS","-f",RESTORED_IMAGE,lsm,FULLREST_IMAGE,kwopt_to_command_line(**opts));
      
document_globals(make_image,"*_IMAGE COLUMN IMAGE_CHANNELIZE MS RESTORING_OPTIONS CLEAN_ALGORITHM ms.IFRS ms.DDID ms.FIELD ms.CHANRANGE");      

def make_threshold_mask (input="$RESTORED_IMAGE",threshold=0,output="$MASK_IMAGE",high=1,low=0):
  """Makes a mask image by thresholding the input image at a given value. The output image is a copy of the input image,
  with pixel values of 'high' (1 by default) where input pixels are >= threshold, and 'low' (0 default) where pixels are <threshold.
  """
  input,output = interpolate_locals("input output");
  ff = pyfits.open(input);
  d = ff[0].data;
  d[d<threshold] = low;
  d[d>threshold] = high;
  ff.writeto(output,clobber=True);
  info("made mask image $output by thresholding $input at %g"%threshold);
  
document_globals(make_threshold_mask,"RESTORED_IMAGE MASK_IMAGE");

def make_empty_image (msname="$MS",image="$COPY_IMAGE_TO",channelize=None,**kw0):
  msname,image = interpolate_locals("msname image");
  
  # setup imager options
  kw0.update(dict(ms=msname,channelize=channelize,dirty=True,dirty_image=image,restore=False,
                   select="ANTENNA1==0 && ANTENNA2==1"));
  make_image(**kw0);
  info("created empty image $image");

define("COPY_IMAGE_TO_Template", "${MS:BASE}.imagecopy.fits","container for image copy");

def predict_vis (msname="$MS",image="$MODEL_IMAGE",column="MODEL_DATA",channelize=None,
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
  fits2casa(image,casaimage);
  
  # setup channelize options
  if 'img_nchan' not in kw0 or 'img_chanstart' not in kw0:
    if channelize is None:
      channelize = IMAGE_CHANNELIZE;
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

document_globals(predict_vis,"MS MODEL_IMAGE COPY_IMAGE_TO ms.IFRS ms.DDID ms.FIELD ms.CHANRANGE");      

def make_psf (msname="$MS",**kw):
  """Makes an image of the PSF. All other arguments as per make_image()."""
  make_image(msname,dirty=False,psf=True,**kw);
