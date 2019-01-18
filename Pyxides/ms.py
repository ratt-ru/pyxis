"""Pyxis module for MS-related operations""";
import pyrap.tables
from pyrap.tables import table
import os.path
from astropy.io import fits as pyfits
import numpy as np

from Pyxis.ModSupport import *

import std
from utils import casa_scripts


# register ourselves with Pyxis, and define the superglobals
register_pyxis_module();

v.define("MS","",
  """current measurement set""");
  
define("DDID",0,
  """current DATA_DESC_ID value""");
define("FIELD",0,
  """current FIELD value""");
define("IFRS","all",
  """interferometer subset""");
define("CHANRANGE",None,
  """channel range, as first,last[,step], or list of such tuples per DDID, or None for all""");
define("MS_TDL_Template",'ms_sel.msname=$MS ms_sel.ddid_index=$DDID ms_sel.field_index=$FIELD',
  """these options get passed to TDL scripts to specify an MS""");
  

lwimager = x.lwimager;
_flagms  	= x("flag-ms.py");
flagms          = _flagms.args("$MS ${-I <IFRS} $CHAN_OWLCAT");
downweigh_redundant = x("downweigh-redundant-baselines.py").args("$MS ${-I <IFRS}");
_aoflagger      = x.aoflagger;
addbitflagcol   = x.addbitflagcol.args("$MS");
wsrt_j2convert  = x.wsrt_j2convert.args("in=$MS");
mergems         = x("merge-ms.py");
taql		= x("taql");

define("PLOTVIS","CORRECTED_DATA:I",
  """passed to plot-ms to plot output visibilities. Set to None to skip plots.""");
define("PLOTMS_ARGS","",
  """extra plot-ms arguments""");
plotms = x("plot-ms.py").args("$MS $PLOTVIS $PLOTMS_ARGS ${-D <DDID} ${-F <FIELD} ${-I <IFRS} $CHAN_OWLCAT");

class _TableGuard (object):
  def __init__ (self,tab):
    self.tab = tab;
  def __enter__ (self):
    return self.tab;
  def __exit__ (self):
    self.tab.close();

def msw (msname="$MS",subtable=None):
  """Opens the MS or a subtable read-write, returns table object."""
  return ms(msname,subtable,write=True);

def ms (msname="$MS",subtable=None,write=False):
  """Opens the MS or a subtable (read-only by default), returns table object."""
  msname = interpolate_locals("msname");
  if not msname:
    raise ValueError("'msname' or global MS variable must be set and valid");
  if subtable:
    msname = table(msname,ack=False).getkeyword(subtable);
  tab = table(msname,readonly=not write,ack=False);
  return tab;

def _filename (base,newext):
  while base and base[-1] == "/":
    base = base[:-1];
  return os.path.splitext(base)[0]+"."+newext;

def prep (msname="$MS"):
  """Prepares MS for use with MeqTrees: adds imaging columns, adds BITFLAG columns, copies current flags
  to 'legacy' flagset"""
  msname = interpolate_locals("msname");
  verify_antpos(msname,fix=True);
  add_imaging_columns(msname);
  info("adding bitflag column");
  x.addbitflagcol("$msname");
  info("copying FLAG to bitflag 'legacy'");
  _flagms("$msname -Y +L -f legacy -c");
  info("flagging INFs/NANs in data");
  _flagms("$msname --nan -f legacy --data-column DATA -x");
  
  
def add_imaging_columns (msname="$MS"):
  msname = interpolate_locals("msname");
  tab = msw(msname);
  if "MODEL_DATA" in tab.colnames() and "CHANNEL_SELECTION" in tab.getcolkeywords("MODEL_DATA"):
    tab.removecolkeyword('MODEL_DATA','CHANNEL_SELECTION');
  tab.close();
  import im.lwimager;
  if not im.lwimager.add_imaging_columns(msname):
    warn("Using pyrap to add imaging columns to $msname. Beware of https://github.com/ska-sa/lwimager/issues/3")
    pyrap.tables.addImagingColumns(msname);
    # if DATA column is not fixed shape, the MODEL_DATA and CORRECTED_DATA columns need to be initialized
    try:
      tab = ms(v.MS);
      x1 = tab.getcol("MODEL_DATA",0,1);
      x2 = tab.getcol("CORRECTED_DATA",0,1);
      info("MODEL_DATA shape",x1.shape[1:],"CORRECTED_DATA shape",x2.shape[1:]);
      return;
    except:
      info("will try to init MODEL_DATA and CORRECTED_DATA from DATA");
    copycol("DATA","MODEL_DATA",msname=msname);
    copycol("DATA","CORRECTED_DATA",msname=msname);
  
  
def delcols (*columns):  
  """Deletes the given columns in the MS""";
  tab = msw(v.MS);
  columns = [ col for col in columns if col in tab.colnames() ];
  info("deleting columns $columns");
  tab.removecols(columns);
  
def listcols (*columns):
  """With no arguments, lists all columns of the MS. With column names as arguments, lists shapes of specified columns""";
  tab = ms(v.MS);
  if not columns:
    info("columns are",*(tab.colnames()));
  else:
    for col in columns:
      coldata = tab.getcol(col);
      info("column $col shape",coldata.shape);
    info("MS has %d rows"%tab.nrows());
    
def verifycol (column):
  """Verifies that a column has data by reading it""";
  nddid = ms(v.MS,subtable="DATA_DESCRIPTION").nrows();
  info("$MS has $nddid DDIDs");
  tab0 = ms(v.MS);
  for ddid in range(nddid):
    tab = tab0.query("DATA_DESC_ID == %d"%ddid);
    coldata = tab.getcol(column);
    info("DDID $ddid column $column shape",coldata.shape);
  tab0.close()
      
document_globals(delcols,"MS");
document_globals(listcols,"MS");

def zerocol (column,ddid="$DDID",field="$FIELD",msname="$MS"):  
  """Fills the given column in the MS with zeroes""";
  column,msname,ddid,field = interpolate_locals("column msname ddid field");
  subtable = msw(msname).query(II("DATA_DESC_ID==$ddid && FIELD_ID==$field"));
  col = subtable.getcol(column);
  info("ddid $ddid field $field: will zero column $column of shape %s"%str(col.shape));
  col[...] = 0;
  subtable.putcol(column,col);
  subtable.close();
document_globals(zerocol,"MS DDID FIELD");
  
def copycol (fromcol="DATA",tocol="CORRECTED_DATA",rowchunk=500000,msname="$MS",to_ms="$msname",ddid=None,to_ddid=None):
  """Copies data from one column of MS to another.
  Copies 'rowchunk' rows at a time; decrease the default if you have low RAM.
  """;
  msname,destms,fromcol,tocol = interpolate_locals("msname to_ms fromcol tocol");
  if ddid is None:
    ddids = list(range(ms(msname,subtable="DATA_DESCRIPTION").nrows()));
    info("copying $msname $fromcol to $destms $tocol");
    info("$msname has %d DDIDs"%len(ddids));
    to_ddid = None;
  else:
    ddids = [ddid];
    if to_ddid is None:
      to_ddid = ddid;
    info("copying from $msname DDID $ddid $fromcol to $destms DDID $to_ddid $tocol");
  maintab0 = ms(msname);
  maintab1 = msw(destms);
  for ddid in ddids:
    tab0 = maintab0.query("DATA_DESC_ID == %d"%ddid);
    tab1 = maintab1.query("DATA_DESC_ID == %d"%(to_ddid if to_ddid is not None else ddid));
    nrows = tab0.nrows();
    info("DDID $ddid has $nrows rows");
    if tab1.nrows() != nrows:
      abort("table size mismatch: destination has %d rows"%tab1.nrows());
    for row0 in range(0,nrows,rowchunk):
      nr = min(rowchunk,nrows-row0);
      info("copying rows $row0 to %d"%(row0+nr-1));
      tab1.putcol(tocol,tab0.getcol(fromcol,row0,nr),row0,nr)
  for t in tab0,tab1,maintab0,maintab1:
    tab0.close()

def sumcols (fromcol1="DATA",fromcol2="MODEL_DATA",tocol="CORRECTED_DATA",rowchunk=500000,msname="$MS",to_ms="$msname",ddid=None,to_ddid=None):
  """Sums data from two columns of MS into a third.
  Copies 'rowchunk' rows at a time; decrease the default if you have low RAM.
  """;
  msname,destms,fromcol1,fromcol2,tocol = interpolate_locals("msname to_ms fromcol1 fromcol2 tocol");
  if ddid is None:
      ddids = list(range(ms(msname,subtable="DATA_DESCRIPTION").nrows()));
      info("copying $msname $fromcol1+$fromcol2 to $destms $tocol");
      info("$msname has %d DDIDs"%len(ddids));
      to_ddid = None;
  else:
      ddids = [ddid];
      if to_ddid is None:
        to_ddid = ddid;
      info("copying from $msname DDID $ddid $fromcol1+$fromcol2 to $destms DDID $to_ddid $tocol");
  maintab0 = ms(msname);
  maintab1 = msw(destms);
  for ddid in ddids:
    tab0 = maintab0.query("DATA_DESC_ID == %d"%ddid);
    tab1 = maintab1.query("DATA_DESC_ID == %d"%(to_ddid if to_ddid is not None else ddid));
    nrows = tab0.nrows();
    info("DDID $ddid has $nrows rows");
    if tab1.nrows() != nrows:
      abort("table size mismatch: destination has %d rows"%tab1.nrows());
    for row0 in range(0,nrows,rowchunk):
      nr = min(rowchunk,nrows-row0);
      info("copying rows $row0 to %d"%(row0+nr-1));
      tab1.putcol(tocol,tab0.getcol(fromcol1,row0,nr)+tab0.getcol(fromcol2,row0,nr),row0,nr)
  for t in tab0,tab1,maintab0,maintab1:
    tab0.close()

    
document_globals(copycol,"MS");

def verify_antpos (msname="$MS",fix=False,hemisphere=None):
  """Verifies antenna Y positions in MS. If Y coordinate convention is wrong, either fixes the positions (fix=True) or
  raises an error. hemisphere=-1 makes it assume that the observatory is in the Western hemisphere, hemisphere=1
  in the Eastern, or else tries to find observatory name using MS and pyrap.measure."""
  msname = interpolate_locals("msname");
  if not hemisphere:
    obs = ms(msname,"OBSERVATION").getcol("TELESCOPE_NAME")[0];
    info("observatory is $obs");
    try:
      import pyrap.measures
      hemisphere = 1 if pyrap.measures.measures().observatory(obs)['m0']['value'] > 0 else -1;
    except:
      traceback.print_exc();
      warn("$obs is unknown, or pyrap.measures is missing. Will not verify antenna positions.")
      return 
  info("antenna Y positions should be of sign %+d"%hemisphere);
  
  anttab = msw(msname,"ANTENNA");
  pos = anttab.getcol("POSITION");
  wrong = pos[:,1]<0 if hemisphere>0 else pos[:,1]>0;
  nw = sum(wrong);
  if nw:
    if not fix:
      abort("$msname/ANTENNA has $nw incorrect Y antenna positions. Check your coordinate conversions (from UVFITS?), or run pyxis ms.verify_antpos[fix=True]")
    pos[wrong,1] *= -1;
    anttab.putcol("POSITION",pos);
    info("$msname/ANTENNA: $nw incorrect antenna positions were adjusted (Y sign flipped)");
  else:
    info("$msname/ANTENNA: all antenna positions appear to have correct Y sign")

define('FIGURE_WIDTH',8,'width of plots, in inches');
define('FIGURE_HEIGHT',6,'height of plots, in inches');
define('FIGURE_DPI',100,'resolution of plots, in DPI');
  
def plot_uvcov (msname="$MS",width=None,height=None,dpi=None,save=None,select=None,limit=None,use_flags=False,**kw):
  """Makes uv-coverage plot
  'msname' is superglobal MS by default.
  If 'save' is given, saves figure to file.
  Use width/height/dpi to override figure settings.
  Any additional keyword arguments are passed to plot(). Try e.g. ms=.1 to change the marker size.
  Return value is maximum baseline length.
  """
  msname,save = interpolate_locals("msname save");
  tab = ms(msname);
  if select:
    tab = tab.query(select);
  uv = tab.getcol("UVW")[:,:2];
  if use_flags:
    flag = tab.getcol("FLAG_ROW")
    uv = uv[~flag,:]
  import pylab
  
  pylab.figure(figsize=(width or FIGURE_WIDTH,height or FIGURE_HEIGHT));
  pylab.plot(-uv[:,0],-uv[:,1],'.r',**kw);
  pylab.plot(uv[:,0],uv[:,1],'.b',**kw);
  mb = np.sqrt((uv**2).sum(1)).max();
  info("max baseline is %.3f km"%(mb*1e-3));
  if limit is not None:
    pylab.xlim(-limit,limit);
    pylab.ylim(-limit,limit);
  if save:
    pylab.savefig(save,dpi=(dpi or FIGURE_DPI));
    info("saved UV coverage plot to $save");
  else:
    pylab.show();
  return mb
  
document_globals(plot_uvcov,"MS FIGURE_*");  

def swapfields (f1,f2,msname="$MS"):
  """Swaps two fields in an MS"""
  msname = interpolate_locals("msname")
  info("swapping FIELDs $f1 and $f2 in $msname");
  field = msw(msname=msname,subtable="FIELD");
  for name in field.colnames():
    info("swapping column $name");
    col = field.getcol(name);
    # arrays needs to be swapped with copy, else confusion ensues
    if hasattr(col,'shape') and len(col.shape) > 1:
        col[f1],col[f2] = col[f2].copy(),col[f1].copy();
    else:
        col[f1],col[f2] = col[f2],col[f1]
    field.putcol(name,col);
  field.close();
  tab = msw();
  fcol = tab.getcol("FIELD_ID");
  r1 = (fcol==f1)
  r2 = (fcol==f2)
  fcol[r1] = f2
  fcol[r2] = f1
  tab.putcol("FIELD_ID",fcol);
  tab.close();


##
## ARCHIVE/UNARCHIVE FUNCTIONS
##
def_global("TARBALL_DIR",".","directory where tarballs of MSs are kept");

def load_tarball (msname="$MS"):
  """Unpacks fresh copy of MS from .tgz in ms.TARBALL_DIR"""; 
  msname = interpolate_locals("msname");
  if exists(msname):
    info("$msname exists, removing and unpacking fresh MS from tarball");
    x.sh("rm -fr $msname")
  else:
    info("$msname does not exist, unpacking fresh MS from tarball");
  x.sh("cd ${msname:DIR}; tar zxvf ${TARBALL_DIR}/${msname:FILE}.tgz");

def save_tarball (msname="$MS"):
  """Saves MS to .tgz in ms.TARBALL_DIR""";
  msname = interpolate_locals("msname");
  x.sh("cd ${msname:DIR}; tar zcvf ${TARBALL_DIR}/${msname:FILE}.tgz ${msname:FILE}");
                                
document_globals(load_tarball,"TARBALL_DIR");
document_globals(save_tarball,"TARBALL_DIR");


##
## MERGE/SPLIT/VIEW FUNCTIONS
##
def merge (output="merged.MS",options=""):
  """Merges the MSs given by MS_List into the output MS. Options are passed to merge-ms."""
  if not v.MS_List:
    abort("MS_List must be set before calling ms.merge()");
  output,options = interpolate_locals("output options");
  mergems("-f",options,output,*v.MS_List);
document_globals(merge,"MS_List");


def split_views (msname="$MS",output="${MS:DIR}/${MS:BASE}-%s.MS",column="OBSERVATION_ID",values=None):
  """Splits MS into views according to unique values of the column. If values is not specified,
  looks in the column for the set of unique values. Makes a set of reference MSs, using 'output' as
  a template.""";
  msname,output,column = interpolate_locals("msname output column");
  if not values:
    values = set(ms(msname).getcol(column));
  info("splitting $msname by $column (%s)"%" ".join(map(str,values)));
  for val in values:
    subset = output%val;
    taql("SELECT FROM $msname where $column == $val giving $subset",split_args=False);

    
def virtconcat (output="concat.MS",thorough=False,subtables=False):
  """Virtually concatenates the MSs given by MS_List into an output MS."""
  output,options = interpolate_locals("output options");
  auxfile = II("${output}.dat");
  if not v.MS_List:
    abort("MS_List must be set before calling ms.virtconcat()");
  if len(v.MS_List) != len(set([os.path.basename(x) for x in v.MS_List])):
    abort("ms.virtconcat: MSs to be concatenated need to have unique basenames. Please rename your MSs accordingly.");
  cmd = "";
  if thorough:
    cmd = """ms.open("%s", nomodify=False)\n"""%v.MS_List[0];
    for msl in v.MS_List[1:]:
      cmd += II("""ms.virtconcatenate("$msl","$auxfile",'1GHz','1arcsec')\n""");  
    cmd += II("""ms.close()\nos.remove('$auxfile')\n""");
  cmd += """if not ms.createmultims('$output',["%s"],
  [],
  True, # nomodify  
  False,# lock  
  $subtables): # copysubtables from first to all other members  
  os._exit(1);
ms.close();
"""%'","'.join(v.MS_List); 
  std.runcasapy(cmd);
  info("virtually concatenated %d inputs MSs into $output"%len(v.MS_List));

document_globals(virtconcat,"MS_List");

def concat (output="concat.MS",thorough=False,subtables=False,freqtol='1MHz',dirtol='1arcsec'):
  """Concatenates the MSs given by MS_List into an output MS."""
  output,freqtol,dirtol = interpolate_locals("output freqtol dirtol");
  info("concatenating",v.MS_List,"into $output");
  if not v.MS_List:
    abort("MS_List must be set before calling ms.concat()");
  if len(v.MS_List) != len(set([os.path.basename(name) for name in v.MS_List])):
    abort("ms.virtconcat: MSs to be concatenated need to have unique basenames. Please rename your MSs accordingly.");
  x.sh("cp -a "+v.MS_List[0]+" "+output);
  cmd = """ms.open("%s", nomodify=False)\n"""%output;
  for msl in v.MS_List[1:]:
    cmd += II("""ms.concatenate("$msl",freqtol='$freqtol',dirtol='$dirtol')\n""");  
  cmd += II("""ms.close()\n""");
  std.runcasapy(cmd);
  info("concatenated %d inputs MSs into $output"%len(v.MS_List));

document_globals(virtconcat,"MS_List");


##
## CONVERSION
##
def from_uvfits (fitsfile,msname="$MS"):
  """Converts UVFITS file into MS""";
  fitsfile,msname = interpolate_locals("fitsfile msname");
  if not msname:
    msname = fitsfile+".MS";
  std.runcasapy("""ms.fromfits(msfile='$msname',fitsfile='$fitsfile')""");
  verify_antpos(msname,fix=True);
  
def fixuvw (msname="$MS",fix=True,rowstep=100000):
  """Fixes the UVW column of an MS by recomputing it from scratch. If fix=False, only prints differences with current 
  UVW column at every rowstep-th row"""
  # these are parameters for the CASA script given by 
  msname = interpolate_locals("msname");
  write_uvw = fix;
  std.runcasapy(_utils.casa_scripts.fixuvw_casa,content="_utils.casa_scripts.fixuvw_casa");
  if fix:
    info("updated UVWs have been written to $msname");
  else:
    info("fix=False, updated UVWs not written out");


##
## RESAMPLING FUNCTIONS
##
def split_rebin (msname="$MS",output="$MSOUT",chan=None,time=None,field=None,spw=None,column="DATA"):
  """Splits and/or resamples MS in frequency with the given channel stepping size, and/or in time
  with the give time bin size (e.g. '5s'), and/or breaks out the specified fields and spws""";
  msname,output = interpolate_locals("msname output");
  args = ""
  def list2str (arg):
    return ",".join(map(str,stg)) if isinstance(arg,(list,tuple)) else str(arg);
  if chan:
    args += II(",width=[$chan]");
  if time:
    args += II(",timebin='$time'");
  if field:
    args += II(",field='%s'"%list2str(field));
  if spw:
    args += II(",spw='%s'"%list2str(spw));
  column = column.lower();
  std.runcasapy("""split(vis='$msname',outputvis='$output',datacolumn='$column'$args);""");
  


##
## INFO FUNCTIONS
##

def summary (msname="$MS"):
  msname = interpolate_locals("msname");
  std.runcasapy("listobs('$msname')");

##
## FLAGGING FUNCTIONS
##
def aoflagger (msname="$MS",strategy=None):
  """Runs AOFlagger with the specified strategy"""
  msname,strategy = interpolate_locals("msname strategy");
  if strategy:
    _aoflagger("-strategy $strategy $msname");
  else:
    _aoflagger(msname);


def flag_ifrs (msname="$MS",ifrs="",flagset="badifr"):
  """Flags specified baselines""";
  msname,ifrs,flagset = interpolate_locals("msname ifrs flagset");
  _flagms(msname,"-I $ifrs -f $flagset -c");


def_global("FLAG_CHANNELS_MULTIPLIER",1,"multiply channel numbers given to flag_channels() by N");
def_global("FLAG_TIMESLOTS_MULTIPLIER",1,"multiply timeslot numbers given to flag_timeslots() by N");

def flag_channels (msname="$MS",begin=0,end=0,ifrs="all",flagset="badchan"):
  """Flags specified channel range in the specified baselines""";
  msname,ifrs,flagset = interpolate_locals("msname ifrs flagset");
  begin *= FLAG_CHANNELS_MULTIPLIER;
  end *= FLAG_CHANNELS_MULTIPLIER;
  _flagms(msname,"-I $ifrs -L $begin~$end -f $flagset -c");
document_globals(flag_channels,"FLAG_CHANNELS_*");
  

def flag_timeslots (msname="$MS",begin=0,end=0,ifrs="all",flagset="badts"):
  """Flags specified channel range in the specified baselines""";
  msname,ifrs,flagset = interpolate_locals("msname ifrs flagset");
  begin *= FLAG_TIMESLOTS_MULTIPLIER;
  end *= FLAG_TIMESLOTS_MULTIPLIER;
  _flagms(msname,"-I $ifrs -T $begin~$end -f $flagset -c");
document_globals(flag_channels,"FLAG_TIMESLOTS_*");

  
  

###
### Various MS-related settings, setup automatically from MS variable
###


## current spwid and number of channels. Note that these are set automatically from the MS by the _msddid_Template below
define('SPWID',0,'currently selected spectral window, set automatically from DDID');
define('TOTAL_CHANNELS',0,'total number of channels in current spectral window');
define('SPW_CENTRE_MHZ',0,"centre frequency of current spectral window, MHz");
define('SPW_BANDWIDTH_MHZ',0,"bandwidth of current spectral window, MHz");

## whenever the MS or DDID changes, look up the corresponding info on channels and spectral windows 
_msddid = None;
def _msddid_accessed_Template ():
  global SPWID,TOTAL_CHANNELS,SPW_CENTRE_MHZ,SPW_BANDWIDTH_MHZ,_msddid;
  msddid = II("$MS:$DDID");
  if msddid != _msddid and II("$MS") and DDID is not None:
    _msddid = msddid;
    if not exists('$MS'):
      warn("$MS doesn't exist"); 
      return None;
    try:
      ddtab = ms(subtable="DATA_DESCRIPTION");
      if ddtab.nrows() < DDID+1:
        warn("No DDID $DDID in $MS");
        return None;
      SPWID = ddtab.getcol("SPECTRAL_WINDOW_ID",DDID,1)[0];
      spwtab = ms(subtable="SPECTRAL_WINDOW");
      TOTAL_CHANNELS = spwtab.getcol("NUM_CHAN",SPWID,1)[0];
#      SPW_CENTRE_MHZ = spwtab.getcol("REF_FREQUENCY",SPWID,1)[0]*1e-6;
      chans = spwtab.getcol("CHAN_FREQ",SPWID,1)[0];
      SPW_CENTRE_MHZ = (chans[0]+chans[-1])*1e-6/2;
      SPW_BANDWIDTH_MHZ = spwtab.getcol("TOTAL_BANDWIDTH",SPWID,1)[0]*1e-6;
      # make sure this is reevaluated
      _chanspec_Template();
      info("$MS ddid $DDID is spwid $SPWID, $TOTAL_CHANNELS channels, centred on $SPW_CENTRE_MHZ MHz, bandwidth $SPW_BANDWIDTH_MHZ MHz"); 
    except:
      warn("Error accessing $MS");
      traceback.print_exc();
      return None;
  return II("$MS:$DDID");

## whenever the channel range changes, setup strings for TDL & Owlcat channel selection (CHAN_TDL and CHAN_OWLCAT),
## and also CHANSTART,CHANSTEP,NUMCHANS
_chanspec = None;
def _chanspec_Template ():
  global CHAN_TDL,CHAN_OWLCAT,CHANSTART,CHANSTEP,NUMCHANS;
  chans = CHANRANGE;
  if isinstance(CHANRANGE,(list,tuple)) and type(CHANRANGE[0]) is not int:
    chans = CHANRANGE[DDID];
  # process channel specification 
  if chans is None:
    CHAN_OWLCAT = '';
    CHANSTART,CHANSTEP,NUMCHANS = 0,1,TOTAL_CHANNELS;
    CHAN_TDL = 'ms_sel.select_channels=0';
  else:
    if type(chans) is int:
      ch0,ch1,dch = chans,chans,1;
#      CHANSTART,CHANSTEP,NUMCHANS = chans,1,1;
    elif len(chans) == 1:
      ch0,ch1,dch = chans[0],chans[0],1;
#      CHANSTART,CHANSTEP,NUMCHANS = chans[0],1,1;
    elif len(chans) == 2:
      ch0,ch1,dch = chans[0],chans[1],1;
#      CHANSTART,CHANSTEP,NUMCHANS = chans[0],1,chans[1]-chans[0]+1;
    elif len(chans) == 3:
      ch0,ch1,dch = chans;
    CHANSTART,CHANSTEP,NUMCHANS = ch0,dch,((ch1-ch0)//dch+1);
    CHAN_OWLCAT = "-L %d~%d:%d"%(ch0,ch1,dch);
    CHAN_TDL = 'ms_sel.select_channels=1 ms_sel.ms_channel_start=%d ms_sel.ms_channel_end=%d ms_sel.ms_channel_step=%d'%\
               (ch0,ch1,dch);
  return CHANSTART,CHANSTEP,NUMCHANS;

def set_default_spectral_info():
  tab = ms(subtable='SPECTRAL_WINDOW')
  global CHANSTART,CHANSTEP,NUMCHANS,CHANRANGE
  NUMCHANS = tab.getcol('NUM_CHAN')[0]
  CHANSTART = 0
  CHANSTEP = 1
  CHANRANGE = CHANSTART,NUMCHANS-1,CHANSTEP


def create_empty_ms(msname="$MS", tel=None, pos=None, pos_type='casa', coords="itrf",
            synthesis=4, dtime=10, freq0="1.4GHz", dfreq="10MHz", lon_lat=None, **kw):
    """
Uses simms to create an empty measurement set. Requires
either an antenna table (CASA table) or a list of ITRF or ENU positions. 

msname: MS name
tel: Telescope name (This name must be in the CASA Database (check in me.obslist() in casapy)
     If its not there, then you will need to specify the telescope coordinates via "lon_lat"
pos: Antenna positions. This can either a CASA table or an ASCII file. 
     (see simms --help for more on using an ascii file)
pos_type: Antenna position type. Choices are (casa, ascii)
coords: This is only applicable if you are using an ASCII file. Choices are (itrf, enu)
synthesis: Synthesis time in hours
dtime: Integration time in seconds
freq0: Start frequency 
dfreq: Channel width
nbands: Number of frequency bands
**kw: extra keyword arguments.

A standard file should have the format: pos1 pos2 pos3* dish_diameter station
mount. NOTE: In the case of ENU, the 3rd position (up) is not essential and
may not be specified; indicate that your file doesn't have this dimension by
enebaling the --noup (-nu) option.
    """

    try:
        from simms import simms
    except ImportError:
        abort("Import simms failed. Please make sure you simms intalled.\n"
              "Find simms at github.com/SpheMakh/simms or install it by running"
              "  pip install simms")
    
    simms.create_empty_ms(msname=II(msname), tel=tel, pos=pos, pos_type=pos_type, 
                coords=coords, synthesis=synthesis, dtime=dtime, freq0=freq0, 
                dfreq=dfreq, lon_lat=lon_lat, **kw)
