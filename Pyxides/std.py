from Pyxis.ModSupport import *

import tempfile,glob,os.path,time,os

# register ourselves with Pyxis, and define the superglobals
register_pyxis_module();

v.define("OUTDIR","",
  """base output directory""");
v.define("SUFFIX_Template",'${spw<ms.DDID}',
  """suffix added to filenames, default is "-spwX""");
v.define("DESTDIR_Template",'${OUTDIR>/}plots-${MS:BASE>-}${spw<ms.DDID}',
  """destination directory for plots, images, etc.""");
v.define("OUTFILE_Template",'${DESTDIR>/}${MS:BASE>-}${SUFFIX>-}${s<STEP>-}${LABEL}',
  """base output filename for plots, images, etc.""");
v.define("STEP",1,
  """step counter, automatically incremented. Useful for decorating filenames.""")
v.define("LABEL","",
  """decorative label, mainly used for decorating filenames.""")
  
remove          = xo.rm.args("-fr");
copy            = x.cp.args("-a");
plotparms       = x("plot-parms.py").args("$PLOTPARMS_ARGS");
fitstool        = x("fitstool.py");

CASAPY_AUTO = xro.which("casapy").strip() or xro.which("casa").strip()

v.define("CASAPY_ZAPLOGS",True,"clean casapy*log and ipython*log files after successful execution of runcasapy")
v.define("CASAPY_ZAPLOGS_ALWAYS",False,"clean casapy*log and ipython*log files after any execution of runcasapy")
v.define("CASAPY_PATH",None,"explicit path to casapy/casa executable")

def runcasapy (command,content=None,zap=None,zap_always=None):
  """Runs the specified casapy command (which can be a multi-line script including newlines).
  'cleanlogs': cleanup casapy*log and ipython*log files after the run. If 0, never clean up.
    If 1, clean up if successful but not on errors. If 2, clean up always.
  'content': if not None, this is what's reported in the log. Otherwise the command itself is reported.
  """;
  command = interpolate_locals("command");
  zap = zap if zap is not None else CASAPY_ZAPLOGS;
  zap_always = zap_always if zap_always is not None else CASAPY_ZAPLOGS_ALWAYS; 
  
  casapy = CASAPY_PATH or CASAPY_AUTO
  if not casapy:
      abort("casapy/casa executable not found. Is CASA installed? You can also try setting std.CASAPY explicitly")

  # write command to script file
  tf = tempfile.NamedTemporaryFile(suffix=".py");
  # Call casapy from temp. directory to avoid conflicts when running parallel jobs
  td = tempfile.mkdtemp(dir='.')
  # we want get back to the working directory once casapy is launched
  cdir = os.path.realpath('.')

  command = "\nimport os\nos.chdir('%s')\n%s"%(cdir, command) 
  tf.write(command+"\nexit\n");
  tf.flush();
  tfname = tf.name;
  # run casapy
  if content:
    content = II(" ($content)");
  else:
    content = II(". Content:\n$command\n")
  info("Running casapy $tfname$content")
  t0 = time.time()
  retcode = x.sh("cd $td && $casapy --nologger --log2term -c $tfname")
  tf.close();
  # move content of temp. directory to working dir, then delete temp. directory
  x.sh("mv ${td}/* $cdir && rm -fr $td")
  # zap logs
  if zap_always or ( zap and not retcode ):
    logs = glob.glob("ipython-*.log") + glob.glob("casapy-*.log") + glob.glob("casa-*.log")
    logs = [ log for log in logs if os.path.getmtime(log) > t0 ];
    info("zapping CASA logfiles",*logs);
    for log in logs:
      if exists(log):
        os.unlink(log);
  if retcode:
    abort("casapy failed with return code %d. Check the logs for errors.");

document_globals(runcasapy,"CASAPY*");

def printpaths ():
  info("OUTDIR=$OUTDIR, DESTDIR=$DESTDIR, OUTFILE=$OUTFILE");

