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
define('IMAGER','lwimager','Imager to user. Default is lwimager.');
define('LWIMAGER_PATH','lwimager','path to lwimager binary. Default is to look in the system PATH.');

define('COLUMN','CORRECTED_DATA','default column to image');

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

# known lwimager args -- these will be passed from keywords
_fileargs = set("image model restored residual".split(" ")); 


def _run (convert_output_to_fits=True,lwimager_path="$LWIMAGER_PATH",**kw):
  # look up lwimager
  lwimager_path = interpolate_locals("lwimager_path");
  lwimager_path = findImager(lwimager_path)
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
  info("$path version is $major.$minor.$patch-$tail")
  return major*1000000+minor*1000+patch,tail;

      
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
  """Converts FITS image to CASA image.""";
  for char in "/-*+().":
    input = input.replace(char,"\\"+char);
  if exists(output):
    rm_fr(output);
  imagecalc("in=$input out=$output");



def findImager(path,imager_name=None):
  """ Find imager"""
  ispath = len(path.split('/'))>1
  if ispath : 
    if os.path.exists(path): return path
    else : abort('Could not find imager $imager_name at $path')
  # Look in system path
  check_path = subprocess.Popen(['which',path],stderr=subprocess.PIPE,stdout=subprocess.PIPE)
  stdout = check_path.stdout.read().strip()
  if stdout : return stdout
  # Check aliases
  stdout = os.popen('grep %s $HOME/.bash_aliases'%imager_name).read().strip()
  if stdout: return stdout.split('=')[-1].strip("'")
  # Don't know where else to look
  abort('Could not find imager $imager_name at $path')

#----------------------------- MORESANE WRAP ---------------------------
define('MORESANE_PATH_Template','moresane','Path to PyMORESANE')
_moresane_args = {'outputname': None,\
'model-image': None,\
'residual-image': None,\
'restored-image':None,\
'singlerun': False,\
'subregion': None,\
'scalecount': None,\
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

def run_moresane(dirty_image,psf_image,
                 model_image='$MODEL_IMAGE',
                 residual_image='$RESIDUAL_IMAGE',
                 restored_image='$RESTORED_IMAGE',
                 threshold=3.0,
                 image_prefix=None,
                 path='$MORESANE_PATH',**kw):
  """ Runs PyMORESANE """
  # Check if PyMORESANE is where it is said to be
  model_image,residual_image,restored_image,path = interpolate_locals('model_image residual_image restored_image path')
  #path = path or MORESANE_PATH
  path = findImager(path,imager_name='PyMORESANE') 
  if image_prefix: _moresane_args.update['outputname']=image_prefix+'.moresane.fits'
  # Update options set via this this function
  if 'sigmalevel' not in kw: _moresane_args['sigmalevel'] = threshold
  # Make sure that all options passed into moresane are known
  unknown = []
  if len(kw)>0:
    for arg in kw.keys():
      if arg not in _moresane_args.keys(): unknown.append(arg)
      else: _moresane_args[arg] = kw[arg]
    if len(unknown)>0: warn('Ignoring unknown options passed into PyMORESANE :\n $unknown \n')
  import types 
  _moresane_args.update({'model-image': model_image,'residual-image': residual_image,'restored-image': restored_image})
  # Construct PyMORESANE run command
  run_cmd = '%s '%path
  for key,val in _moresane_args.iteritems():
   if val is not None:
    if type(val) is bool:
      if val: run_cmd+='--%s '%(key)
    else: run_cmd+='--%s=%s '%(key,val)
  run_cmd += '%s %s'%(dirty_image,psf_image)
  #abort('>>> $run_cmd')
  x.sh(run_cmd)
  
#------------------------------- WRAP WSCLEAN ---------------------------------
def toDeg(val):
  """Convert angle to Deg. returns a float. val must be in form: 2arcsec, 2arcmin, or 2rad"""
  import math
  _convert = {'arcsec':3600.,'arcmin':60.,'rad':180/math.pi,'deg':1.}
  val = val or cellsize
  ind = 1
  if type(val) is not str: raise ValueError('Angle must be a string, e.g 10arcmin')
  for i,char in enumerate(val): 
   if char is not '.':
    try: int(char)
    except ValueError: 
      ind = i
      break
  a,b = val[:ind],val[ind:]
  try: return float(a)/_convert[b]
  except KeyError: abort('Could not recognise unit [$b]. Please use either arcsec, arcmin, deg or rad')
  
define('WSCLEAN_PATH_Template','wsclean','Path to WSCLEAN')
_wsclean_args = {'name': None,\
'predict': None,\
'size': '2048 2048',\
'scale': 0.01,\
'nwlayers': None,\
'minuvw': None,\
'maxuvw': None,\
'maxw': None,\
'pol': 'I',\
'joinpolarizations': False,\
'multiscale': False,\
'multiscale-threshold-bias': 0.7,\
'multiscale-scale-bias': 0.6,\
'cleanborder': 5,\
'niter': 0,\
'threshold': 0,\
'gain': 0.1,\
'mgain': 1.0,\
'smallinversion': True,\
'nosmallinversion': False,\
'smallpsf': False,\
'gridmode': 'kb',\
'nonegative': None,\
'negative': True,
'stopnegative': False,\
'interval': None,\
'channelrange': None,\
'channelsout': 1,\
'join-channels': False,\
'field': 0,\
'weight': 'natural',\
'mfsweighting': False,\
'superweight': 1,\
'beamsize': None,\
'makepsf': False,\
'imaginarypart': False,\
'datacolumn': 'CORRECTED_DATA',\
'gkernelsize': 7,\
'oversampling': 63,\
'reorder': None,\
'no-reorder': None,\
'addmodel': None,\
'addmodelapp': None,\
'savemodel': None,\
'wlimit': None,\
'mem': 100,\
'absmem': None,\
'j': None}

def combine_fits(fitslist,outname='combined.fits',keep_old=False):
  """ Combine a list of fits files into a single cube """
  import pyfits
  freqIndex = 0
  nchan = 0
  hdu = pyfits.open(fitslist[0])[0]
  hdr = hdu.header
  naxis = hdr['NAXIS']
  shape = list(hdu.data.shape)
  for key,val in hdr.iteritems():
    if key.startswith('CTYPE'):
      if val.upper().startswith('FREQ'): freqIndex = int(key[5:])
  if freqIndex ==0: abort('At least one of the fits files has frequency information in the header. Cannot combine fits images.')
  crval = hdr['CRVAL%d'%freqIndex]
  images = []
  import pylab
  for fits in fitslist:
    hdu = pyfits.open(fits)[0]
    hdr = hdu.header
    temp_crval = hdr['CRVAL%d'%freqIndex]
    nchan += hdr['NAXIS%d'%freqIndex]
    if temp_crval < crval : crval = temp_crval
    images.append(hdu.data)
  ind = naxis - freqIndex # numpy array indexing differnt from FITS
  hdr['CRVAL%d'%freqIndex] = crval
  shape[ind] = nchan
  new_data = numpy.reshape(np.array(images),shape)
  pyfits.writeto(outname,new_data,hdr,clobber=True)
  if keep_old is False:
    for fits in fitslist: 
      rm_fr(fits)
 
# wsclean work around
def add_weight_spectrum(msname='$MS'):
 msname = interpolate_locals('msname')
 tab = pyrap.tables.table(msname,readonly=False)
 try: tab.getcol('WEIGHT_SPECTRUM')
 except RuntimeError:
  warn('Did not find WEIGHT_SPECTRUM column in $msname')
  from pyrap.tables import maketabdesc
  from pyrap.tables import makearrcoldesc
  coldmi = tab.getdminfo('DATA')
  dshape = tab.getcol('DATA').shape
  coldmi['NAME'] = 'weight_spec'
  info('adding WEIGHT_SPECTRUM column to $msname')
  shape = tab.getcol('DATA')[0].shape
  tab.addcols(maketabdesc(makearrcoldesc('WEIGHT_SPECTRUM',0,shape=shape,valuetype='float')),coldmi)
  ones = np.ndarray(dshape)
  info('Filling WEIGHT_SPECTRUM with unity')
  ones[...] = 1
  tab.putcol('WEIGHT_SPECTRUM',ones)
 tab.close()

 
def run_wsclean(msname='$MS',image_prefix='$BASENAME_IMAGE',column='$COLUMN',
                path=None,
                npix=0,cellsize=None,
                niter=None,
                dirty=True,
                channelize=None,
                psf_image='$PSF_IMAGE',
                dirty_image='$DIRTY_IMAGE',
                model_image='$MODEL_IMAGE',
                residual_image='$RESIDUAL_IMAGE',
                restored_image='$RESTORED_IMAGE',**kw):
  """ run WSCLEAN """
  
  msname,image_prefix,column,model_image,residual_image,restored_image =\
 interpolate_locals('msname image_prefix column model_image residual_image restored_image')
  # Check if WSCLEAN is where it is said to be
  path = path or WSCLEAN_PATH
  path = findImager(path,imager_name='WSCLEAN')
  add_weight_spectrum(msname) # wsclean requires a WEIGHT_SPECTRUM column in the MS
  _wsclean_args['name'] = image_prefix
  npix = npix or globals()['npix']
  cellsize = cellsize or globals()['cellsize']
  _wsclean_args['threshold'] = globals()['threshold']
  ms.set_default_spectral_info()
  weight = globals()['weight']
  robust = globals()['robust']
  if weight == 'briggs': 
    _wsclean_args['weight'] = 'briggs %d'%robust
  else: _wsclean_args['weight'] = weight
  stokes = repr(list(globals()['stokes'])).strip('[]').replace('\'','')
  if niter is None: niter = globals()['niter']
  _wsclean_args['niter'] = niter 
  # Update options set via this this function
  if 'datacolumn' not in kw: _wsclean_args['datacolumn'] = column
  if 'size' not in kw: _wsclean_args['size'] = '%d %d'%(npix,npix)
  if 'cellsize' not in kw: _wsclean_args['scale'] = toDeg(cellsize)
  # Check if extra arguments are valid
  unknown = []
  if len(kw)>0:
    for arg in kw.keys():
      if arg not in _wsclean_args.keys(): unknown.append(arg)
    if len(unknown)>0: warn('Ignoring unkown options passed into WSCLEAN :\n $unknown \n')
  if column: _wsclean_args['datacolumn'] = column
  if image_prefix: _wsclean_args['name'] = image_prefix
  import types 
  if channelize is None:
    channelize = IMAGE_CHANNELIZE
  if channelize == 0:
    _wsclean_args['channelrange'] = '%d %d'%(ms.CHANSTART,ms.NUMCHANS)
  elif channelize > 0:
    nr = ms.NUMCHANS//channelize
    _wsclean_args['channelsout'] = nr
  _wsclean_args.update(kw) # extra options get preference
  # Construct WSCLEAN run command
  run_cmd = '%s '%path
  for key,val in _wsclean_args.iteritems():
   if val is not None:
    if type(val) is bool:
      if val: run_cmd+='-%s '%(key)
    else: run_cmd+='-%s %s '%(key,val)
  run_cmd += msname
#  abort('>>> $run_cmd')
  x.sh(run_cmd)
  # Combine images if needed
  if channelize in [0,None]:
    if dirty: 
      x.mv('${image_prefix}-dirty.fits $dirty_image')
      #if niter==0: x.mv('${image_prefix}-psf.fits $psf_image')
    else: rm_fr('${image_prefix}-dirty.fits')
    if niter>0: 
      x.mv('${image_prefix}-model.fits $model_image')
      x.mv('${image_prefix}-residual.fits $residual_image')
      x.mv('${image_prefix}-image.fits $restored_image')
      x.mv('${image_prefix}-psf.fits $psf_image')
    elif niter==0: rm_fr('${image_prefix}-image.fits')
  elif channelize>0:
    restored_images = []
    residual_images = []
    model_images = []
    dirty_images = []
    psf_images = []
    for i in range(nr):
      label = str(i).zfill(4)
      restored_images.append('%s-%s-image.fits'%(image_prefix,label))
      if _wsclean_args['makepsf'] or niter>0 : psf_images.append('%s-%s-psf.fits'%(image_prefix,label))
      if niter>0: 
        model_images.append('%s-%s-model.fits'%(image_prefix,label))
        residual_images.append('%s-%s-residual.fits'%(image_prefix,label))
      if dirty: dirty_images.append('%s-%s-dirty.fits'%(image_prefix,label))
    if niter==0: 
      rm_fr('${image_prefix}-MFS-image.fits')
      for fits in model_images+residual_images+restored_images: rm_fr(fits)
    else:
      combine_fits(model_images,outname=model_image,keep_old=False)
      combine_fits(residual_images,outname=residual_image,keep_old=False)
      combine_fits(restored_images,outname=restored_image,keep_old=False)
      x.mv('${image_prefix}-MFS-image.fits ${image_prefix}-MFS-restored.fits')
    if dirty is False:
      for fits in dirty_images: rm_fr(fits)
    else: combine_fits(dirty_images,outname=dirty_image,keep_old=False)
    if len(psf_images)>0: combine_fits(psf_images,outname=psf_image,keep_old=False)
#--------------------------------------------------------------------------------

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
  """;
  global IMAGER
  IMAGER = II(imager)
  if algorithm.lower() in ['moresane','pymoresane']: IMAGER = 'moresane'
  imager,msname,column,lsm,dirty_image,psf_image,restored_image,residual_image,model_image,algorithm = \
    interpolate_locals("imager msname column lsm dirty_image psf_image restored_image residual_image model_image algorithm"); 
  makedir(DESTDIR);
  if imager.lower() == 'lwimager':
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

    def make_dirty():
      info("imager.make_image: making dirty image $dirty_image");
      kw = kw0.copy();
      if type(dirty) is dict:
        kw.update(dirty);
      kw['operation'] = 'image';
      _run(image=dirty_image,**kw);

    if dirty: make_dirty()

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
      if not os.path.exists(dirty_image): make_dirty()  
      if type(restore) is dict:
        run_moresane(dirty_image,psf_image,model=model_image,residual=residual_image,restored=restored_image,**restore)
      elif restore==True: 
        run_moresane(dirty_image,psf_image,model_image=model_image,residual_image=residual_image,restored_image=restored_image)
      else: abort('restore has to be either a dictionary or a boolean')
    elif restore:
      info("imager.make_image: making restored image $restored_image");
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
  elif imager.lower() == 'wsclean':
    kw = kw0.copy()
    use_moresane = False
    if restore:
      info("imager.make_image: making restored image $restored_image");
      info("                   (model is $model_image, residual is $residual_image)");
      if algorithm.lower() in ['moresane','pymoresane']: 
        kw['niter'] = 0
        use_moresane = True
        kw['makepsf'] = True
      else:
        info("imager.make_image: making dirty image $dirty_image");
        if type(restore) is dict: kw.update(restore)
    else: kw['niter'] = 0
    run_wsclean(channelize=channelize,psf_image=psf_image,model_image=model_image,residual_image=residual_image,dirty_image=dirty_image,**kw)
    if use_moresane: 
      if type(restore) is dict: run_moresane(dirty_image=dirty_image,psf_image=psf_image,**restore)
      elif type(restore) is bool: run_moresane(dirty_image=dirty_image,psf_image=psf_image)
      else: abort('restore has to be either a boolean or a python dictionary')
  if restore:
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
