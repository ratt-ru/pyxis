"""mqt: Pyxides module for MeqTrees-related functionality (running MeqTrees scripts, etc.)"""

import os.path

# register ourselves with Pyxis
from Pyxis.ModSupport import *
register_pyxis_module();

## find the Cattery
import Timba
import os.path
import ms

_cattery_path = Timba.packages()['Cattery'][0]
sys.path.append(_cattery_path);
if v("ADD_PYXIDES_PATH",True):
  path = os.path.join(_cattery_path,"Pyxides");
  verbose(2,"adding %s to import path. Set ADD_PYXIDES_PATH=False to disable"%path);
  sys.path.append(path);

def_global('CATTERY',_cattery_path,"default path to Cattery scripts");

## default multithread setting
def_global('MULTITHREAD',2,"max number of meqserver threads");

## default TDL config file

## extra TDL options applied to all scripts
def_global('EXTRA_TDLOPTS',"","extra options passed to all TDL scripts");

## pipeliner tool
pipeliner = x.time.args("meqtree-pipeliner.py");
pipeliner_mprof = x.mprof.args("run --python meqtree-pipeliner.py");
def_global("SCRIPT",None,"default TDL script");
def_global("JOB",None,"default TDL job to run");
def_global("SECTION",None,"default section to use in TDL config file");
def_global("TDLCONFIG","tdlconf.profiles","default TDL config file",config=True);
def_global("SAVECONFIG",None,"save effective config to file[:section]")

def_global("MEMPROF",False,"if True, runs python memory profiling");

def run (script="$SCRIPT",job="$JOB",config="$TDLCONFIG",section="$SECTION",saveconfig="$SAVECONFIG",args=[],options={}):
  """Uses meqtree-pipeliner to compile the specified MeqTrees 'script', using 'config' file and config 'section',
  then runs the specified 'job'. 

  If you want to run a script on a given MS, then see mqt.msrun() for a convenient alternative.

  Use a list of 'args' to pass extra arguments to meqtree-pipeliner. Use a dict of 'options' to
  pass extra arguments as key=value.""";
  script,job,config,section,saveconfig = interpolate_locals("script job config section saveconfig");
  section = section or os.path.splitext(os.path.basename(script))[0];
  args = [ "-c $config [$section]" ] + list(args)
  if MULTITHREAD > 1:
      args = [ "--mt $MULTITHREAD" ] + args
  if saveconfig:
      args = [ "--save-config $saveconfig"  ] + args
  if isinstance(options, list):
    for dictionary in options:
      args += [ "%s=%s"%(a,b) for a,b in dictionary.items() ] + \
          [ "$EXTRA_TDLOPTS $script =$job "]
  else:
    args += [ "%s=%s"%(a,b) for a,b in options.items() ] + \
        [ "$EXTRA_TDLOPTS $script =$job" ]; 

 # run pipeliner
  if MEMPROF:
    args.append("--memprof");
    pipeliner_mprof(*args);
  else:
    pipeliner(*args);

document_globals(run,"MULTITHREAD EXTRA_TDLOPTS SCRIPT JOB SECTION TDLCONFIG SAVECONFIG");


def msrun (script="$SCRIPT",job="$JOB",section="$SECTION",config="$TDLCONFIG",args=[],options={}):
  """Like run(), but automatically adds TDL options for the currently selected MS/channels/etc
  (according to what is defined in the 'ms' Pyxides module).""";
  script,job,config,section = interpolate_locals("script job config section");
  return run(script=script,job=job,config=config,section=section,
    args = [ """${ms.MS_TDL} ${ms.CHAN_TDL} ms_sel.ms_ifr_subset_str=${ms.IFRS}""" ] + list(args),
    options=options); 

document_globals(msrun,"MULTITHREAD EXTRA_TDLOPTS SCRIPT JOB SECTION TDLCONFIG");

MSSIM_SCRIPT_Template = "$CATTERY/Siamese/turbo-sim.py" 

def mssim (section="$SECTION",config="$TDLCONFIG",script="$MSSIM_SCRIPT",job="simulate",
           column=None,args=[],options={}):
  """Like runms(), but by default runs the turb-sim.py simulations script from the Cattery.
  Common usage is mssim("simulation_section")
  """;
  script,job,config,section,column = interpolate_locals("script job config section column");
  args = [ """${ms.MS_TDL} ${ms.CHAN_TDL} ms_sel.ms_ifr_subset_str=${ms.IFRS}""" ] + list(args)
  if column is not None:
    args += [ II("ms_sel.output_column=$column") ] 
  return msrun(script=script,job=job,config=config,section=section,
    args=args, options=options); 

document_globals(mssim,"MULTITHREAD EXTRA_TDLOPTS SECTION TDLCONFIG MSSIM*");
