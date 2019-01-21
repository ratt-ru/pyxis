import inspect
import os.path
import math
import numpy
import imp
np = numpy

# some useful constants
DEG = math.pi/180
ARCMIN = DEG/60
ARCSEC = DEG/3600

#from Pyxis.Commands import *

import Pyxis.Internals 

_initialized = False;

if not _initialized:
  """Initializes Pyxis with a global context dict.""";
  # initialize Pyxis using the globals of whoever imported the module
  ## OMS: this was enough in Python2. Not in Py3
  #_context = inspect.currentframe().f_back.f_globals;
  ## in Py3:
  frame = inspect.currentframe().f_back
  while frame:
    _context = frame.f_globals
    if "PYXIS_ROOT_NAMESPACE" in _context:
      print("root namespace is",_context.get("__name__"),_context.get("__path__"))
      break
    frame = frame.f_back

  if not frame:
    raise RuntimeError("Unable to find root namespace. Set PYXIS_ROOT_NAMESPACE=True before importing pyxis.")

  Pyxis.Internals.init(_context);  
  from Pyxis.Commands import *
 
  verbose(1,"===[ Pyxis: Python eXtensions for Inteferometry Scripting (C) 2013 by Oleg Smirnov <oms@ska.ac.za> ]===");
  if Pyxis.Internals._verbose_startup_message:
    verbose(*Pyxis.Internals._verbose_startup_message);

  # import basic Pyxis commands into the context
  verbose(1,"loading Pyxis into context '%s'"%_context.get('__name__'));
  exec('from Pyxis.Commands import *',_context);
  exec('from Pyxis.Commands import _I,_II',_context);
  
  pyxides_path = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "Pyxides"))
  verbose(2,"importing Pyxides from",pyxides_path)

  Pyxides = imp.load_source('Pyxides',os.path.join(pyxides_path, "__init__.py"))
  # add Pyxides path to module includes (so we can do stuff like "import ms" instead of "from Pyxides import ms"
  if _context.get("ADD_PYXIDES_PATH",True):
    verbose(2,"added %s to import path. Set ADD_PYXIDES_PATH=False to disable"%pyxides_path);
    sys.path.append(pyxides_path)

  ## import standard modules, unless a specific other set is given
  #if not context.get("pyxis_preload"):
    #import StandardModules
    #for mod in StandardModules.pyxis_preload:
      #filename = os.path.join(os.path.dirname(StandardModules.__file__),mod)+".py";
      #if os.path.exists(filename):
        #verbose(1,"loading standard package '%s' from %s"%(mod,filename));
        #Pyxis.Internals.load_package(mod,filename);        
      #else:
        #warn("can't find standard package %s"%filename);
  
  Pyxis.Internals.initconf();
  
