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
  PACKAGE_TEST_DIR = os.path.join(os.path.dirname(Pyxis.__file__), "recipes", "meqtrees-batch-test")
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

def testMeqtreesBatchJob():
  trace_sync = True;
#  sys.settrace(trace_lines);
  
  if len(sys.argv) > 1:
    newdir = PACKAGE_TEST_DIR;
    print("========== Changing working directory to",newdir);
    os.chdir(newdir);
    print("========== Making required symlinks");
    run("rm {0:s}/WSRT_ANTENNA ; ln -s {1:s}".format(PACKAGE_TEST_DIR, 
                                                     path(os.path.join(PACKAGE_TEST_DIR, "WSRT_ANTENNA"))));
    run("rm {0:s}/test-lsm.txt; ln -s {1:s}".format(PACKAGE_TEST_DIR,
                                                    path(os.path.join(path("test-lsm.txt")))));

  if not os.access(".",os.R_OK|os.W_OK):
    print("Directory",os.getcwd(),"not writable, can't run tests in here.")
    print("You may choose to run the tests in a different directory by giving it as an argument to this script.")
    sys.exit(1);

  ## check if we have owlcat or owlcat.sh
  owlcat = "";
  for dirname in os.environ['PATH'].split(':'):
    for binary in "owlcat","owlcat.sh":
      tmp = os.path.join(dirname,binary);
      if os.path.exists(tmp):
        owlcat = tmp;
        break;
    if owlcat:
      break;
  if not owlcat:
    raise RuntimeError("Can't locate owlcat or owlcat.sh");
    
    
  ## make simulated MS
  print("========== Removing files");
  
  run("rm -fr {0:s}/WSRT.MS* {0:s}/WSRT*img {0:s}/WSRT*fits".format(PACKAGE_TEST_DIR));
  print("========== Running makems");
  run("makems %s" % path(os.path.join(PACKAGE_TEST_DIR, "WSRT_makems.cfg")));
  run("mv {0:s}/WSRT.MS_p0 {0:s}/WSRT.MS".format(PACKAGE_TEST_DIR));
  os.environ["MEQTREES_CATTERY_PATH"] = Cattery.__path__[0]
  run("pyxis {0:s}/WSRT.MS ms.prep".format(PACKAGE_TEST_DIR)); #TODO: this is hacky, bug in CASAcore
  run("ls -ld {0:s}/WSRT.MS".format(PACKAGE_TEST_DIR));
  run("{0:s} downweigh-redundant-baselines {1:s}/WSRT.MS".format(owlcat, PACKAGE_TEST_DIR));
  run("lwimager ms={0:s}/WSRT.MS data=CORRECTED_DATA mode=channel weight=natural npix=10".format(PACKAGE_TEST_DIR));
  # make test LSMs
  run("""tigger-convert {0:s}/test-lsm.txt --rename --format "ra_d dec_d i q u v" --center 0.1deg,60.5deg -f""".format(PACKAGE_TEST_DIR));
  run("""tigger-convert {0:s}/test-lsm.lsm.html {0:s}/test-lsm1.txt --output-format "name ra_h dec_d i q u v freq0 spi rm tags..." -f""".format(PACKAGE_TEST_DIR));
  run("""cut -d " " -f 1-10 {0:s}/test-lsm1.txt >{0:s}/test-lsm1.txt.tmp""".format(PACKAGE_TEST_DIR));
  run("""diff {0:s}/test-lsm1.txt.tmp {1:s} || diff {0:s}/test-lsm1.txt.tmp {2:s}""".format(
      PACKAGE_TEST_DIR, 
      path(os.path.join(PACKAGE_TEST_DIR, 'test-lsm1.txt.reference')),
      path(os.path.join(PACKAGE_TEST_DIR, 'test-lsm2.txt.reference'))));
  run("""tigger-convert {0:s}/test-lsm1.txt --format "name ra_h dec_d i q u v freq0 spi rm tags..." -f""".format(PACKAGE_TEST_DIR));
  run("""{0:s} plot-ms {1:s}/WSRT.MS DATA:I -o data_i.png""".format(owlcat, PACKAGE_TEST_DIR));
  run("""{0:s} run-imager ms={1:s}/WSRT.MS name_dirty=tmp""".format(owlcat, PACKAGE_TEST_DIR));

  print("importing meqserver")
  from Timba.Apps import meqserver
  print("importing Compile")
  from Timba.TDL import Compile
  print("importing TDLOptions")
  from Timba.TDL import TDLOptions

  # This starts a meqserver. Note how we pass the "-mt 2" option to run two threads.
  # A proper pipeline script may want to get the value of "-mt" from its own arguments (sys.argv).
  print("Starting meqserver");
  mqs = meqserver.default_mqs(wait_init=10,extra=["-mt","2"]);

  try:
    ## make simulation with perfect MODEL_DATA
    script = path(os.path.join(PACKAGE_TEST_DIR, "sim.py"));
    print("========== Compiling",script);
    TDLOptions.config.read(path(os.path.join(PACKAGE_TEST_DIR, "testing.tdl.conf")));
    TDLOptions.config.set("calibrate", "ms_sel.msname", os.path.join(PACKAGE_TEST_DIR, TDLOptions.config.get("calibrate", "ms_sel.msname")))
    TDLOptions.config.set("calibrate", "tiggerlsm.filename", os.path.join(PACKAGE_TEST_DIR, TDLOptions.config.get("calibrate", "tiggerlsm.filename")))
    TDLOptions.config.set("calibrate", "lsm.filename", os.path.join(PACKAGE_TEST_DIR, TDLOptions.config.get("calibrate", "lsm.filename")))
    TDLOptions.config.set("calibrate", "cal_g_diag.g_diag.table_name", os.path.join(PACKAGE_TEST_DIR, TDLOptions.config.get("calibrate", "cal_g_diag.g_diag.table_name")))
    TDLOptions.config.set("calibrate", "cal_g_offdiag.g_offdiag.table_name", os.path.join(PACKAGE_TEST_DIR, TDLOptions.config.get("calibrate", "cal_g_offdiag.g_offdiag.table_name")))
    TDLOptions.config.set("simulate-model", "lsm.filename", os.path.join(PACKAGE_TEST_DIR, TDLOptions.config.get("simulate-model", "lsm.filename")))
    TDLOptions.config.set("simulate-model", "ms_sel.msname", os.path.join(PACKAGE_TEST_DIR, TDLOptions.config.get("simulate-model", "ms_sel.msname")))
    TDLOptions.config.set("simulate-model", "tiggerlsm.filename", os.path.join(PACKAGE_TEST_DIR, TDLOptions.config.get("simulate-model", "tiggerlsm.filename")))
    TDLOptions.config.set("calibrate", "img_sel.output_fitsname", os.path.join(PACKAGE_TEST_DIR, "WSRT.MS.CORRECTED_DATA.channel.1ch.fits"))
    TDLOptions.config.set("simulate-model", "img_sel.output_fitsname", os.path.join(PACKAGE_TEST_DIR, "WSRT.MS.MODEL_DATA.channel.1ch.fits"))
    with open(os.path.join(PACKAGE_TEST_DIR, "testing_tmp.tdl.conf"), "w") as f:
      TDLOptions.config.write(f)
    TDLOptions.config.read(path(os.path.join(PACKAGE_TEST_DIR, "testing_tmp.tdl.conf"))); # needs to re-read because of a Timba perculiarity
    mod,ns,msg = Compile.compile_file(mqs, script, config="simulate-model");
    print("========== Simulating MODEL_DATA ");
    mod._tdl_job_1_simulate_MS(mqs,None,wait=True);
    print("========== Imaging MODEL_DATA ");
    TDLOptions.get_job_func('make_dirty_image')(mqs,None,wait=True,run_viewer=False);

    ## compare against reference image
    print("========== Verifying test image ");
    if not os.path.exists(os.path.join(PACKAGE_TEST_DIR, "WSRT.MS.MODEL_DATA.channel.1ch.fits")): raise RuntimeError("Output FITS file does not exist")
    if not os.path.exists(os.path.join(PACKAGE_TEST_DIR, "test-refimage.fits")): raise RuntimeError("Reference FITS file does not exist")
    verify_image(os.path.join(PACKAGE_TEST_DIR, "WSRT.MS.MODEL_DATA.channel.1ch.fits"), 
                 path(os.path.join(PACKAGE_TEST_DIR, "test-refimage.fits")), 
                 maxdelta=1e-3);

    print("========== Compiling script with modified config");
    TDLOptions.init_options("simulate-model",save=False);
    TDLOptions.set_option("me.g_enable",True);
    mod,ns,msg = Compile.compile_file(mqs,script,config=None);
    print("========== Simulating DATA ");
    TDLOptions.set_option("ms_sel.output_column","DATA");
    mod._tdl_job_1_simulate_MS(mqs,None,wait=True);
    print("========== Imaging DATA ");
    TDLOptions.set_option("img_sel.imaging_column","DATA");
    TDLOptions.get_job_func('make_dirty_image')(mqs,None,wait=True,run_viewer=False);

    ## calibrate
    script = path(os.path.join(PACKAGE_TEST_DIR, "cal.py"));
    print("========== Compiling",script);
    mod,ns,msg = Compile.compile_file(mqs,script,config="calibrate");
    print("========== Calibrating ");
    TDLOptions.get_job_func('cal_G_diag')(mqs,None,wait=True);
    print("========== Imaging MODEL_DATA ");
    TDLOptions.get_job_func('make_dirty_image')(mqs,None,wait=True,run_viewer=False);
    
  finally:
    print("Stopping meqserver");
    # this halts the meqserver
    meqserver.stop_default_mqs();
    
  print("========== Making plots of solutions ");
  run("""{0:s} plot-ms {1:s}/WSRT.MS CORRECTED_DATA:I -I ">0" -o {1:s}/corrected_data_i.png""".format(owlcat, PACKAGE_TEST_DIR));
  run("""{0:s} plot-parms -l {1:s}/WSRT.MS/G_diag.fmep""".format(owlcat, PACKAGE_TEST_DIR));
  run("""{0:s} plot-parms {1:s}/WSRT.MS/G_diag.fmep G:*/norm -o {1:s}/parmplot.png""".format(owlcat, PACKAGE_TEST_DIR));
  run("""{0:s} downweigh-redundant-baselines {1:s}/WSRT.MS""".format(owlcat, PACKAGE_TEST_DIR));

  ## compare against reference image
  print("========== Verifying residual image ");
  if not os.path.exists(os.path.join(PACKAGE_TEST_DIR, "WSRT.MS.CORRECTED_DATA.channel.1ch.fits")): raise RuntimeError("Output FITS file does not exist")
  if not os.path.exists(os.path.join(PACKAGE_TEST_DIR, "test-refresidual.fits")): raise RuntimeError("Reference FITS file does not exist")
  verify_image(os.path.join(PACKAGE_TEST_DIR, "WSRT.MS.CORRECTED_DATA.channel.1ch.fits"),
               os.path.join(PACKAGE_TEST_DIR, "test-refresidual.fits"),
               maxdelta=1e-3);

  ## all tests succeeded
  print("========== Break out the bubbly, this hog is airborne!");

  # now we can exit
  print("Bye!");

if __name__ == "__main__":
  testMeqtreesBatchJob()