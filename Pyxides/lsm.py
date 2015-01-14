from Pyxis.ModSupport import *

import imager,std

import pyfits
import Tigger

register_pyxis_module(superglobals="OUTFILE");

tigger_restore  = x("tigger-restore")
tigger_convert  = x("tigger-convert")
tigger_tag      = x("tigger-tag")

v.define("LSM","lsm.lsm.html",
  """current local sky model""");

define("LSM_TDL_Template","tiggerlsm.filename=$LSM",
  """TDL option for selecting current lsm""");
define("LSMREF","",
  """reference LSM (for transferring tags, etc.)""");
  
define('PYBDSM_OUTPUT_Template',"${OUTFILE}_pybdsm.lsm.html","""output LSM file for pybdsm search""");    
define('PYBDSM_POLARIZED',None,"""set to True to run pybdsm in polarized mode""");
define('PYBDSM_OPTIONS',{},"Extra options given to pybdsm");
_pybdsm = x.pybdsm;

define('CLUSTER_DIST',0,
  """source clustering distance, arcsec. If 0, then CLUSTER_DIST_BEAMS is used instead.""");
define('CLUSTER_DIST_BEAMS',3,
  """source clustering distance, in units of PSF size (measured as (BMAJ+BMIN)/2). If BMAJ/BMIN is not defined,
  this falls back to 60 arcsec.""");
define('MIN_EXTENT',0,
  """minimum Gaussian source extent, arcsec; sources smaller than this will be converted to point sources""");

def pybdsm_search (image="${imager.RESTORED_IMAGE}",output="$PYBDSM_OUTPUT",pol='$PYBDSM_POLARIZED',
  select=None,
  threshold=None,pbexp=None,**kw):
  """Runs pybdsm on the specified 'image', converts the results into a Tigger model and writes it to 'output'.
  Use 'threshold' to specify a non-default threshold (thresh_isl and thresh_pix).
  Use 'pol' to force non-default polarized mode.
  Use 'pbexp' to supply a primary beam expression (passed to tigger-convert), in which case the output model will contain
  intrinsic fluxes.
  Use 'select' to apply a selection string on the new model (e.g. "I.gt.0.001")
  """
  image,output,pol = interpolate_locals("image output pol");
  makedir(v.DESTDIR);
  # setup parameters
  gaul = II("${output:BASEPATH}.gaul");
  # info("PyBDSM filenames are $output $gaul");
  # start with default PYBDSM options
  opts = PYBDSM_OPTIONS.copy();
  opts.update(kw);
  # override with explicit arguments
  if threshold:
    opts['thresh_pix'] = threshold;
  if pol is not None:
    opts['polarisation_do'] = is_true(pol);
  pol = opts.get('polarisation_do',False);
  opts['quiet'] = True;
  # run pybdsm
  info("running PyBDSM process_image($image,%s)"%",".join(sorted([ "%s=%s"%x for x in opts.iteritems() ])));
  from lofar import bdsm
  img = bdsm.process_image(image,**kw);
  info("writing PyBDSM gaul catalog");
  img.write_catalog(outfile=gaul,format='ascii',catalog_type='gaul',clobber=True);
  # add log to output
  logfile = II("${output:BASEPATH}.pybdsm.log");
  if exists(logfile):
    info("PyBDSM log output follows:");
    for line in file(logfile):
      print "     ",line;
  else:
    warn("PyBDSM log $logfile not found");
  # set clustering parameter from beam size
  cluster = CLUSTER_DIST;
  if not cluster:
    hdr = pyfits.open(image)[0].header;
    # BMAJ/BMIN is in degrees -- convert to seconds, or fall back to 60" if not set
    cluster = 1800*(hdr.get('BMAJ',0)+hdr.get('BMIN',0))*CLUSTER_DIST_BEAMS or 60;
  # convert catalog
  if pbexp:
    args = [ "--primary-beam",pbexp,"--app-to-int" ]
  else:
    args = []
  if select:
    args += [ "--select",select ];
  verifyGaulModel(gaul)
  
  #Dictionary for establishing correspondence between parameter names in gaul files produced by pybdsm, and pyxis parameter names
  dict_gaul2lsm = {'Gaus_id':'name', 'Isl_id':'Isl_id', 'Source_id':'Source_id', 'Wave_id':'Wave_id', 'RA':'ra_d', 'E_RA':'E_RA', 'DEC':'dec_d', 'E_DEC':'E_DEC', 'Total_flux':'i', 'E_Total_flux':'E_Total_flux', 'Peak_flux':'Peak_flux', 'E_Peak_flux':'E_Peak_flux', 'Xposn':'Xposn', 'E_Xposn':'E_Xposn', 'Yposn':'Yposn', 'E_Yposn':'E_Yposn', 'Maj':'Maj', 'E_Maj':'E_Maj', 'Min':'Min', 'E_Min':'E_Min', 'PA':'PA', 'E_PA':'E_PA', 'Maj_img_plane':'Maj_img_plane', 'E_Maj_img_plane':'E_Maj_img_plane', 'Min_img_plane':'Min_img_plane', 'E_Min_img_plane':'E_Min_img_plane', 'PA_img_plane':'PA_img_plane', 'E_PA_img_plane':'E_PA_img_plane', 'DC_Maj':'emaj_d', 'E_DC_Maj':'E_DC_Maj', 'DC_Min':'emin_d', 'E_DC_Min':'E_DC_Min', 'DC_PA':'pa_d', 'E_DC_PA':'E_DC_PA', 'DC_Maj_img_plane':'DC_Maj_img_plane', 'E_DC_Maj_img_plane':'E_DC_Maj_img_plane', 'DC_Min_img_plane':'DC_Min_img_plane', 'E_DC_Min_img_plane':'E_DC_Min_img_plane', 'DC_PA_img_plane':'DC_PA_img_plane', 'E_DC_PA_img_plane':'E_DC_PA_img_plane', 'Isl_Total_flux':'Isl_Total_flux', 'E_Isl_Total_flux':'E_Isl_Total_flux', 'Isl_rms':'Isl_rms', 'Isl_mean':'Isl_mean', 'Resid_Isl_rms':'Resid_Isl_rms', 'Resid_Isl_mean':'Resid_Isl_mean', 'S_Code':'S_Code', 'Total_Q':'q', 'E_Total_Q':'E_Total_Q', 'Total_U':'u', 'E_Total_U':'E_Total_U', 'Total_V':'v', 'E_Total_V':'E_Total_V', 'Linear_Pol_frac':'Linear_Pol_frac', 'Elow_Linear_Pol_frac':'Elow_Linear_Pol_frac', 'Ehigh_Linear_Pol_frac':'Ehigh_Linear_Pol_frac', 'Circ_Pol_Frac':'Circ_Pol_Frac', 'Elow_Circ_Pol_Frac':'Elow_Circ_Pol_Frac', 'Ehigh_Circ_Pol_Frac':'Ehigh_Circ_Pol_Frac', 'Total_Pol_Frac':'Total_Pol_Frac', 'Elow_Total_Pol_Frac':'Elow_Total_Pol_Frac', 'Ehigh_Total_Pol_Frac':'Ehigh_Total_Pol_Frac', 'Linear_Pol_Ang':'Linear_Pol_Ang', 'E_Linear_Pol_Ang':'E_Linear_Pol_Ang'}

  #Dictionary for classifying a parameter as a general parameter or a polarization-specific parameter
  dict_pol_flag = {'Gaus_id':0, 'Isl_id':0, 'Source_id':0, 'Wave_id':0, 'RA':0, 'E_RA':0, 'DEC':0, 'E_DEC':0, 'Total_flux':0, 'E_Total_flux':0, 'Peak_flux':0, 'E_Peak_flux':0, 'Xposn':0, 'E_Xposn':0, 'Yposn':0, 'E_Yposn':0, 'Maj':0, 'E_Maj':0, 'Min':0, 'E_Min':0, 'PA':0, 'E_PA':0, 'Maj_img_plane':0, 'E_Maj_img_plane':0, 'Min_img_plane':0, 'E_Min_img_plane':0, 'PA_img_plane':0, 'E_PA_img_plane':0, 'DC_Maj':0, 'E_DC_Maj':0, 'DC_Min':0, 'E_DC_Min':0, 'DC_PA':0, 'E_DC_PA':0, 'DC_Maj_img_plane':0, 'E_DC_Maj_img_plane':0, 'DC_Min_img_plane':0, 'E_DC_Min_img_plane':0, 'DC_PA_img_plane':0, 'E_DC_PA_img_plane':0, 'Isl_Total_flux':0, 'E_Isl_Total_flux':0, 'Isl_rms':0, 'Isl_mean':0, 'Resid_Isl_rms':0, 'Resid_Isl_mean':0, 'S_Code':0, 'Total_Q':1, 'E_Total_Q':1, 'Total_U':1, 'E_Total_U':1, 'Total_V':1, 'E_Total_V':1, 'Linear_Pol_frac':1, 'Elow_Linear_Pol_frac':1, 'Ehigh_Linear_Pol_frac':1, 'Circ_Pol_Frac':1, 'Elow_Circ_Pol_Frac':1, 'Ehigh_Circ_Pol_Frac':1, 'Total_Pol_Frac':1, 'Elow_Total_Pol_Frac':1, 'Ehigh_Total_Pol_Frac':1, 'Linear_Pol_Ang':1, 'E_Linear_Pol_Ang':1}

  lines = [line.strip() for line in open(gaul)]
  
  for line in range(len(lines)):
    if lines[line]:
      if lines[line].split()[0] is not '#': 
        gaul_params = lines[line-1].split()[1:] #Parameter list is last line in gaul file that begins with a '#'
        break
  
  # Initialize lists for general and polarization parameters 
  lsm_params_general = []
  lsm_params_polarization = []

  for param in gaul_params:
    if dict_pol_flag[param] is 0:
     lsm_params_general.append(dict_gaul2lsm[param])
    if dict_pol_flag[param] is 1:
     lsm_params_polarization.append(dict_gaul2lsm[param])
  
  general_params_string = ' '.join(lsm_params_general)
  pol_params_string = ' '.join(lsm_params_polarization)

  tigger_convert(gaul,output,"-t","ASCII","--format", general_params_string + (pol_params_string if pol else ""),
    "-f","--rename",
    "--cluster-dist",cluster,
    "--min-extent",MIN_EXTENT,
    split_args=False,
    *args);
    
document_globals(pybdsm_search,"PYBDSM_* imager.RESTORED_IMAGE CLUSTER_* MIN_EXTENT");

def verifyGaulModel(gaullsm):
  """Check all sources in a gaul file are in valid locations before running tigger
  convert. Useful when images are 'all-sky' and have undefined regions.
  """
  falseSources=0
  olsm=''
  fh=open(gaullsm,'r')
  for ll in fh.readlines():
    cll=' '.join(ll.split())
    if cll=='' or cll.startswith('#'):
      olsm+=ll
      continue
    lineArray=cll.split(' ')
    if math.isnan(float(lineArray[4])): falseSources+=1
    else: olsm+=ll
  fh.close()

  fh=open(gaullsm,'w')
  fh.write(olsm)
  fh.close()


def transfer_tags (fromlsm="$LSMREF",lsm="$LSM",output="$LSM",tags="dE",tolerance=60*ARCSEC):
  """Transfers tags from a reference LSM to the given LSM. That is, for every tag
  in the given list, finds all sources with those tags in 'fromlsm', then applies 
  these tags to all nearby sources in 'lsm' (within a radius of 'tolerance'). 
  Saves the result to an LSM file given by 'output'.
  """
  fromlsm,lsm,output,tags = interpolate_locals("fromlsm lsm output tags");
  # now, set dE tags on sources
  tagset = frozenset(tags.split());
  info("Transferring tags %s from %s to %s"%(",".join(tagset),fromlsm,lsm));
  import Tigger
  refmodel = Tigger.load(fromlsm);
  model = Tigger.load(lsm);
  # for each dE-tagged source in the reference model, find all nearby sources
  # in our LSM, and tag them
  for src0 in refmodel.getSourceSubset(",".join(["="+x for x in tagset])):
    for src in model.getSourcesNear(src0.pos.ra,src0.pos.dec,tolerance=tolerance):
      for tag in tagset:
        tagval = src0.getTag(tag,None);
        if tagval is not None:
          if src.getTag(tag,None) != tagval:
            src.setTag(tag,tagval);
            info("setting tag %s=%s on source %s (from reference source %s)"%(tag,tagval,src.name,src0.name))
  model.save(output);

  

CC_RESCALE = 1.  
CC_IMAGE_Template = "${OUTFILE}_ccmodel.fits"

def add_ccs (lsm="$LSM",filename="${imager.MODEL_IMAGE}",
             cc_image="$CC_IMAGE",srcname="ccmodel",output="$LSM",zeroneg=True,scale=None,pad=1):
  """Adds clean components from the specified FITS image 'filename' to the sky model given by 'lsm'.
  Saves the result to an LSM file given by 'output'.
  The CC image is copied to 'cc_image', optionally rescaled by 'scale', and optionally has negative pixels reset to zero (if zeroneg=True).
  'srcname' gives the name of the resulting LSM component.
  'pad' gives the padding attribute of the LSM component, use e.g. 2 if CC image has significant signal towards the edges.
  """;
  lsm,filename,cc_image,srcname,output = interpolate_locals("lsm filename cc_image srcname output");
  info("adding clean components from $filename ($cc_image), resulting in model $output");
  # rescale image
  ff = pyfits.open(filename);
  ff[0].data *= (scale if scale is not None else CC_RESCALE);
  if zeroneg:
    ff[0].data[ff[0].data<0] = 0;
  ff.writeto(cc_image,clobber=True);
  tigger_convert(lsm,output,"-f","--add-brick","$srcname:$cc_image:%f"%pad);

document_globals(add_ccs,"MODEL_CC_*");  


def pointify (lsm="$LSM",output="$LSM",name=""):
  """Replaces names sources with point sources""";
  lsm,output,name = interpolate_locals("lsm output name");
  model = Tigger.load(lsm);
  src = model.findSource(name);
  info("Setting source $name in model $lsm to point source, saving to $output");
  src.shape = None;
  model.save(output);

document_globals(add_ccs,"MODEL_CC_*");  

  
  
