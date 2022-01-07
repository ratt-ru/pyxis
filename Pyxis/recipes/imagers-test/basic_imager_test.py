#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import os.path
import sys
import subprocess
import Cattery

# check installation
try:
  PYXIS_ROOT_NAMESPACE = True  # must set this before import!
  import Pyxis
  import Pyxides
  PACKAGE_TEST_DIR = os.path.join(os.path.dirname(Pyxis.__file__), "recipes", "imagers-test")
  if not os.path.exists(PACKAGE_TEST_DIR):
    raise RuntimeError("Installation excludes {}".format(PACKAGE_TEST_DIR))
except:
  sys.stderr.write("Broken pyxis installation\n")
  sys.stderr.write("Exiting with:\n")
  import traceback
  sys.stderr.write(traceback.format_exc())
  sys.exit(1)

from astropy.io import fits as pyfits

dir0 = os.getcwd();

def path (filename):
  return os.path.join(dir0,filename);

global owlcat;  
os.environ['LWIMAGER_PATH'] = 'lwimager'
  
def run (*commands):
  cmd = " ".join(commands);
  # replace 'owlcat' with actual owlcat scipt
  if cmd.startswith("owlcat"):
    cmd = owlcat+cmd[6:];
  print("========== $",cmd);
  code = subprocess.call(cmd,shell=True, cwd=PACKAGE_TEST_DIR);
  if code:
    raise RuntimeError("failed with exit code %x"%code);
  
def verify_image (file1,file2,maxdelta=1e-6):
  im1 = pyfits.open(file1)[0].data;
  im2 = pyfits.open(file2)[0].data;
  # trim corners, as these may have differences due to modifications of the tapering scheme
  im1 = im1[...,20:-20,20:-20];
  im2 = im2[...,20:-20,20:-20];
  delta = abs(im1-im2).max();
  if delta > maxdelta:
    raise RuntimeError("%s and %s differ by %g"%(file1,file2,delta));
  print("%s and %s differ by %g, this is within tolerance"%(file1,file2,delta));
  
trace_sync = None;

def trace_lines (frame,event, arg):
  global trace_file;
  global trace_sync;
  print("%s %s:%d"%(event,frame.f_code.co_filename,frame.f_lineno));
  if trace_sync:
    sys.stdout.flush();
  return trace_lines;

def testWSClean():
  trace_sync = True;
  
  if len(sys.argv) > 1:
    newdir = PACKAGE_TEST_DIR;
    print("========== Changing working directory to",newdir);
    os.chdir(newdir);
    print("========== Making required symlinks");
    run("rm {0:s}/WSRT_ANTENNA ; ln -s {1:s}".format(PACKAGE_TEST_DIR, 
                                                     path(os.path.join(PACKAGE_TEST_DIR, "WSRT_ANTENNA"))));
  if not os.access(".",os.R_OK|os.W_OK):
    print("Directory",os.getcwd(),"not writable, can't run tests in here.")
    print("You may choose to run the tests in a different directory by giving it as an argument to this script.")
    sys.exit(1);
    
  ## make simulated MS
  print("========== Removing files");
  run("rm -fr {0:s}/WSRT.MS* {0:s}/WSRT*img {0:s}/*fits".format(PACKAGE_TEST_DIR));
  print("========== Running makems");
  run("makems %s" % path(os.path.join(PACKAGE_TEST_DIR, "WSRT_makems.cfg")));
  run("mv {0:s}/WSRT.MS_p0 {0:s}/WSRT.MS".format(PACKAGE_TEST_DIR));
  run("pyxis {0:s}/WSRT.MS ms.prep".format(PACKAGE_TEST_DIR));
  run("pyxis {0:s}/WSRT.MS im.IMAGER=wsclean im.make_image".format(PACKAGE_TEST_DIR))

if __name__ == "__main__":
  testWSClean()