

import sys
import traceback
import inspect
import os
import os.path
import time
import math
import multiprocessing
import queue

import Pyxis
import Pyxis.Internals
from Pyxis.Internals import _int_or_str,interpolate,assign


DEG = math.pi/180
ARCMIN = DEG/60
ARCSEC = ARCMIN/60

def _init (context):
  global x,xo,xz,xr,xro,v,E;
  # add some standard objects
  # the 'x' object is a shortcut for executing shell commands. E.g. x.ls('.')
  # the 'xo' object is a shortcut for executing shell commands that are allowed to fail. E.g. x.ls('.')
  x = Pyxis.Internals.ShellExecutorFactory(allow_fail=False);
  x.__name__ = 'x';
  x.__doc__ = x.doc_proto%dict(name='x') + """Shell commands launched via 'x' must succeed for the script 
to continue. Upon error, the current script is aborted.""";

  xo = Pyxis.Internals.ShellExecutorFactory(allow_fail=True);
  xo.__name__ = 'xo';
  xo.__doc__ = xo.doc_proto%dict(name='xo') + """Shell commands launched via 'xo' are allowed to fail, with
the script continuing regardless.""";

  xr = Pyxis.Internals.ShellExecutorFactory(get_output=True,verbose=3);
  xr.__name__ = 'xr';
  xr.__doc__ = xr.doc_proto%dict(name='xr') + """Shell commands launched via 'xr' return their output as
a Python string.""";

  xro = Pyxis.Internals.ShellExecutorFactory(get_output=True,allow_fail=True,verbose=0);
  xro.__name__ = 'xr';
  xro.__doc__ = xro.doc_proto%dict(name='xro') + """Shell commands launched via 'xro' return their output as
a Python string, and are allowed to fail.""";

  xz = Pyxis.Internals.ShellExecutorFactory(allow_fail=True,bg=True);
  xz.__name__ = 'xz';
  xz.__doc__ = xz.doc_proto%dict(name='xz') + """Shell commands launched via 'xz' are run in the background,
in parallel with the rest of the script. They are allowed to fail, with the script continuing regardless.""";

  v = Pyxis.Internals.GlobalVariableSpace(context);
  object.__setattr__(v,'__name__','v');
  
  E = Pyxis.Internals.ShellVariableSpace();
  object.__setattr__(E,'__name__','E');


def _I (string,level=1):
  """_I(string): interpolates (i.e. replaces by value) $VAR and ${VAR} occurrences of local and 
  global variables. Local variables are interpreted as those in the context of the caller (i.e. 1 level away).
  
  _i(string,level): change the number of caller levels for lookup of locals, e.g. 2 means caller of caller
  _i(string,-1): interpolate across all callers
  """;
  frame = inspect.currentframe();
  for i in range(level):
    frame = frame and frame.f_back;
  return interpolate(string,frame);
  
def _II (*strings):
  """_II(string): interpolates multiple strings. Does an implicit assign_templates call beforehand. Useful as
  the opening line of a function, as e.g. arg1,arg2 = _II(arg1,arg2);
  """;
  Pyxis.Internals.assign_templates();
  frame = inspect.currentframe().f_back;
  ret = [ x and interpolate(x,frame) for x in strings ];
  return ret[0] if len(strings)<2 else ret;

II = _II;  
  
_subprocess_id = None;  
  
def _timestamp ():
  ts = time.strftime("%Y/%m/%d %H:%M:%S");
  if _subprocess_id is not None:
    ts += " [%d]"%_subprocess_id;
  return ts;

def _message (*msg,**kw):
  output = " ".join(map(str,msg));
  sync = kw.get("sync");
  quiet = ( Pyxis.Context.get('QUIET') or kw.get("quiet") ) and not kw.get('critical'); 
  if sys.stdout is not sys.__stdout__:
    if sync:
      fcntl.lockf(sys.stdout,fcntl.LOCK_EX);
      sys.stdout.seek(0,2);
    print(output);
    if sync:
      sys.stdout.flush();
      fcntl.lockf(sys.stdout,fcntl.LOCK_UN);
    if not quiet:
      sys.__stdout__.write(output+"\n");
  else:
    if not quiet:
      print(output);
  
def _debug (*msg,**kw):
  """Prints debug message(s) without interpolation""";
  _message(_timestamp(),"DEBUG:",*msg,**kw);

def _verbose (level,*msg,**kw):
  """Prints verbosity message(s), if verbosity level is >= Context.pyxis_verbosity""";
  try:
    verb = int(Pyxis.Context['VERBOSE']);
  except:
    verb = 1;
  try:
    level = int(level)
  except:
    level = 1;
  if level <= verb:
    _message(_timestamp(),"PYXIS:",*msg,**kw);

def _info (*msg,**kw):
  """Prints info message(s) without interpolation""";
  _message(_timestamp(),"INFO:",*msg,**kw);

def _warn (*msg,**kw):
  """Prints warning message(s) without interpolation""";
  _message(_timestamp(),"WARNING:",*msg,**kw);

def _error (*msg,**kw):
  """Prints error message(s) without interpolation""";
  _message(_timestamp(),"ERROR:",*msg,**kw);

def _abort (*msg,**kw):
  """Prints error message(s) without interpolation and aborts""";
  _message(_timestamp(),"ABORT:",console=True,critical=True,*msg,**kw);
  Pyxis.Internals.flush_log();
  sys.exit(1);
  
def debug (*msg):
  """Prints debug message(s)""";
  _debug(*[ _I(x,2) for x in msg ]);

def verbose (level,*msg):
  """Prints verbosity message(s), if verbosity level is >= Context.pyxis_verbosity""";
  _verbose(level,*[ _I(x,2) for x in msg ]);

def info (*msg):
  """Prints info message(s)""";
  _info(*[ _I(x,2) for x in msg ]);

def warn (*msg):
  """Prints warning message(s)""";
  _warn(*[ _I(x,2) for x in msg ]);

def error (*msg):
  """Prints error message(s)""";
  _error(*[ _I(x,2) for x in msg ]);

def abort (*msg):
  """Prints error message(s) and aborts""";
  _abort(*[ _I(x,2) for x in msg ]);
  
def pyxreload ():
  from Pyxis.Internals import _modules
  for m in 'Pyxis.Internals','Pyxis.Commands','Pyxis.ModSupport':
    info("Reloading",m);
    reload(sys.modules[m]);
  for m in _modules.values():
    info("Reloading",m.__name__);
    reload(m);

def pyxlf (mod=None):
  """Prints all functions defined by module""";
  pyxls(mod,what="F");

def pyxlv (mod=None):
  """Prints all global variables defined by module""";
  pyxls(mod,what="V");

def pyxls (mod=None,what="FVTB"):
  import Pyxis.ModSupport
  """Prints symbols defined by module. 'what' is a combination of characters specifying what to print.""";
  # make sorted list of globals (excepting those starting with underscore)
  globs = Pyxis.Context if mod is None else vars(mod);
  globs = [ (name,value) for name,value in sorted(globs.items()) 
            if name[0]!="_" and name not in Pyxis._predefined_names ];
  # from this, extract the non-callables
  varlist = [ (name,value) for name,value in globs if not callable(value)  ];
  if "V" in what:
    print("Globals:");
    for var,val in varlist:
      if not var.endswith("_List") and not var.endswith("_Template") and isinstance(val,(str,int)):
        print("  %s=%s"%(var,val));
    print("Lists:");
    for var,val in varlist:
      if var.endswith("_List"):
        print("  %s=%s"%(var,val));
    print("Templates:");
    for var,val in globs:
      if var.endswith("_Template"):
        print("  %s=%s"%(var,val));
  # now deal with the callables
  if "F" in what:
    print("Functions:");
    print(" ",", ".join([ name for name,value in globs 
        if callable(value) and not isinstance(value,Pyxis.Internals.ShellExecutor) and not name.endswith("_Template") 
          and not name in globals() 
          and not name in Pyxis.ModSupport.__dict__
      ]));
  if "T" in what:
    print("External tools:");
    for name,value in globs:
      if isinstance(value,Pyxis.Internals.ShellExecutor):
        print("  %s=%s"%(name,value.path));
  if "B" in what:
    print("Pyxis built-ins:");
    print(" ",", ".join([ name for name,value in globs 
      if callable(value) and not isinstance(value,Pyxis.Internals.ShellExecutor) and not name.endswith("_Template") and name in globals() ]));

def exists (filename):
  """Returns True if filename exists, interpolating the filename""";
  return filename and os.path.exists(_I(filename,2));

def _per (varname,parallel,*commands):
  # default frame to look for vars is caller of caller
  frame = inspect.currentframe().f_back.f_back;
  namespace,vname = Pyxis.Internals._resolve_namespace(varname,frame=frame,default_namespace=Pyxis.Context);
  _verbose(2,"per(%s.%s)",namespace.get('__name__',"???") if namespace is not Pyxis.Context else "v",vname);
  saveval = namespace.get(vname,None);
  def _restore ():
#    if saveval is not None:
    _verbose(2,"restoring %s=%s"%(varname,saveval),sync=True);
    assign(varname,saveval,namespace=namespace,interpolate=False);
  varlist = namespace.get(vname+"_List",None);
  cmdlist = ",".join([ x if isinstance(x,str) else getattr(x,"__name__","?") for x in commands ]);
  persist = Pyxis.Context.get("PERSIST");
  fail_list = [];
  if varlist is None:
    _verbose(1,"per(%s,%s): %s_List is empty"%(varname,cmdlist,varname));
    return;
  try:
    if type(varlist) is str:
      varlist = list(map(_int_or_str,varlist.split(",")));
    elif not isinstance(varlist,(list,tuple)):
      _abort("PYXIS: per(%s,%s): %s_List has invalid type %s"%(varname,cmdlist,str(type(varlist))));
    nforks = Pyxis.Context.get("JOBS",0);
    stagger = Pyxis.Context.get("JOB_STAGGER",0);
    # unforked case
    _verbose(1,"per(%s,%s,persist=%d): iterating over %s=%s"%(varname,cmdlist,1 if persist else 0,varname," ".join(map(str,varlist))));
    global _subprocess_id;
    if not parallel or nforks < 2 or len(varlist) < 2 or _subprocess_id is not None:
      # do the actual iteration
      for value in varlist:
        _verbose(1,"per-loop, setting %s=%s"%(varname,value));
        assign(vname,value,namespace=namespace,interpolate=False); 
        try:
          Pyxis.Internals.run(*commands);
        except (Exception,SystemExit,KeyboardInterrupt) as exc:
          if persist:
            _warn("exception raised for %s=%s:\n"%(vname,value),
                *traceback.format_exception(*sys.exc_info()));
            _warn("persistent mode is on (PERSIST=1), so continuing to end of %s_List"%vname)
            fail_list.append((value,str(exc)));
          else:
            raise;
      # any fails?
      if fail_list:
        _restore();
        _abort("per-loop failed for %s"%(",".join([f[0] for f in fail_list])));
    else:
      # else split varlist into forked subprocesses
      nforks = min(nforks,len(varlist));
      # create a queue for all variable values
      varqueue = multiprocessing.Queue(len(varlist))
      for x in varlist:
        varqueue.put(x)
      # distribute N values per each fork
      _verbose(1,"splitting into %d jobs by %s, staggered by %ds"%(nforks,varname,stagger));
      Pyxis.Internals.flush_log();
      forked_pids = {};
      try:
        for job_id in range(nforks):
          if job_id and stagger:
            time.sleep(stagger);
          # subvals is range of values to be iterated over by this subjob
          pid = os.fork();
          if not pid:
            # child fork: run commands while something is on queue
            _subprocess_id = job_id;
            _verbose(1,"started job %d"%job_id,sync=True);
            try:
              fail_list = []
              success_list = []
              while True:
                try:
                  value = varqueue.get(False)
                except queue.Empty:
                  break
                _verbose(1,"per-loop, setting %s=%s"%(varname,value),sync=True);
                assign(vname,value,namespace=namespace,interpolate=False);
                try:
                  Pyxis.Internals.run(*commands);
                  success_list.append(value)
                except (Exception,SystemExit,KeyboardInterrupt) as exc:
                  if persist:
                    _warn("exception raised for %s=%s:\n"%(vname,value),
                        sync=True,*traceback.format_exception(*sys.exc_info()));
                    _warn("persistent mode is on (PERSIST=1), so continuing to end of %s_List"%vname,sync=True)
                    fail_list.append((value,str(exc)));
                  else:
                    raise;
              # any successes?
              if success_list:
                _verbose(1,"job #%d (pid %d): per-loop succeeded for %s"%(_subprocess_id,pid,
                    ", ".join([str(f) for f in success_list])),sync=True)
              # any fails?
              if fail_list:
                _restore();
                _abort("job #%d (pid %d): per-loop failed for %s"%(_subprocess_id,pid,
                    ", ".join([str(f[0]) for f in fail_list])),sync=True)
            except:
              traceback.print_exc();
              _verbose(1,"job #%d (pid %d) aborted at %s=%s, exiting with error code 1"%(_subprocess_id,pid,varname,value),sync=True);
              _restore();
              _verbose(2,"logfile is",Pyxis.Context.get('LOG'),sync=True);
              _error("per-loop failed for %s"%value,sync=True);
              sys.exit(1);
            _verbose(2,"job #%d (pid %d) exiting normally"%(_subprocess_id,os.getpid()),sync=True);
            sys.exit(0);
          else: # parent pid: append to list
            _verbose(2,"launched job #%d with pid %d"%(job_id,pid),sync=True);
            forked_pids[pid] = job_id
        njobs = len(forked_pids);
        _verbose(1,"%d jobs launched, waiting for finish"%len(forked_pids),sync=True);
        failed = [];
        while forked_pids:
          pid,status = os.waitpid(-1,0);
          if pid in forked_pids:
            job_id = forked_pids.pop(pid);
            status >>= 8;
            if status:
              failed.append(job_id);
  #            success = False;
              _error("job #%d exited with error status %d, waiting for %d more jobs to complete"%(job_id,status,len(forked_pids)),sync=True);
            else:
              _verbose(1,"job #%d finished, waiting for %d more jobs to complete"%(job_id,len(forked_pids)),sync=True);
        if failed:
          _abort("%d of %d jobs have failed"%(len(failed),njobs),sync=True);
        else:     
          _verbose(1,"all jobs finished ok",sync=True);
      except KeyboardInterrupt:
        if _subprocess_id is None:
          _restore();
          _error("Caught Ctrl+C, waiting for %d jobs to exit"%len(forked_pids),sync=True);
          import signal;
          for pid in list(forked_pids.keys()):
            os.kill(pid,signal.SIGINT);
          while forked_pids:
            pid,status = os.waitpid(-1,0);
            if pid in forked_pids:
              job_id = forked_pids.pop(pid);
              _verbose(1,"job #%d exited with error status %d, waiting for %d more"%
                  (job_id,status>>8,len(forked_pids)),sync=True);
        raise;
  finally:
    # note that children also execute this block with sys.exit()
    if _subprocess_id is None:
      _restore();
    Pyxis.Internals.flush_log();

def per (varname,*commands):
  """Iterates over variable 'varname', and executes commands. That is, for every value
  in varname_List, sets varname to that value, then calls the commands.
  Uses non-parallel mode."""
  _per(varname,False,*commands);

def pper (varname,*commands):
  """Iterates over variable 'varname', and executes commands. That is, for every value
  in varname_List, sets varname to that value, then calls the commands.
  Uses parallel mode."""
  _per(varname,True,*commands);

def per_ms (*commands):
  """Iterates over variable 'MS', and executes commands. That is, for every value
  in MS_List, sets MS to that value, then calls the commands. Default mode is parallel."""
  _per("MS",True,*commands);

def per_ddid (*commands):
  """Iterates over variable 'DDID', and executes commands. That is, for every value
  in DDID_List, sets MS to that value, then calls the commands. Default mode is serial"""
  _per("ms.DDID",False,*commands);

def is_true (arg):
  """Returns True if argument evaluates to boolean truth, possibly as a string.
  is_true('False') == is_true('0') == is_true(0) == False
  is_true('True') == is_true('1') == is_true(1) == True
  """;
  arg = _I(arg,2);
  if isinstance(arg,str):
    if not arg:
      return False;
    try:
      return bool(eval(arg));
    except:
      raise TypeError("is_true('%s'): invalid string argument"%arg);
  try:
    return bool(arg);
  except:
    raise TypeError("is_true(%s): invalid argument %s"%(str(arg),str(type(arg))));

def makedir (dirname,no_interpolate=False):
  """Makes sure the supplied directory exists, by creating parents as necessary. Interpolates the dirname.""";
  if not no_interpolate:
    dirname = interpolate(dirname,inspect.currentframe().f_back);
  parent = dirname;
  while parent and parent[-1] == '/':
    parent = parent[:-1]
  # go back and accumulate list of dirs to be created
  parents = [];
  while parent and not os.path.exists(parent):
    parents.append(parent);
    parent = os.path.dirname(parent);
  # create in reverse
  for parent in parents[::-1]:
    verbose(1,"creating directory %s"%parent);
    os.mkdir(parent);
    
    
import tempfile   
import pickle
import fcntl
    
class Safelist (object):
  """A Safelist provides a list of objects that is shared among parallel processes. Multiple jobs launched
  by pyxis can append to a Safelist in a multiprocess-safe manner: write locks are enforced""";
  def __init__ (self,filename=None):
    """Creates a safelist, associated with the given filename. If not supplied, a filename is
    chosen randomly"""
    if filename:
      filename = _I(filename,2);
      if os.path.exists(filename):
        os.remove(filename);
      self.filename = filename;
    else:
      self.filename = tempfile.NamedTemporaryFile(delete=False).name;

  def reset (self):
    """Resets safelist to empty (by deleting the associated file)""";
    if os.path.exists(self.filename):
      os.remove(self.filename);
      
  def add (self,obj):
    """Adds an object to the safelist, in an MP-safe manner""";
    if isinstance(obj,str):
      obj = _I(obj,2);
    ff = open(self.filename,"ab");
    fcntl.flock(ff,fcntl.LOCK_EX);
    try:
      pickle.dump(obj,ff);
    finally:
      fcntl.flock(ff,fcntl.LOCK_UN);
    
  def read (self):
    """Reads all objects accumulated in the safelist, in an MP-safe manner""";
    ret = [];
    if os.path.exists(self.filename):
      ff = open(self.filename,"rb");
      fcntl.flock(ff,fcntl.LOCK_EX);
      try:
        while True:
          ret.append(pickle.load(ff));
      except EOFError:
        pass;
      finally:
        fcntl.flock(ff,fcntl.LOCK_UN);
    return ret;
    