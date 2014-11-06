from Pyxis.ModSupport import *

register_pyxis_module();

import socket
import glob
import time
import os.path

define('PROJECT',"meerkat-7-gazing","default GCE project name")
define('ZONE',"europe-west1-b","default GCE compute zone")

# gcloud executable
# includes PROJECT and ZONE in the command line
gc = x.gcloud.args(before="compute --project $PROJECT",after="--zone $ZONE");
gc1 = x.gcloud.args(before="compute --project $PROJECT");
gco = xo.gcloud.args(before="compute --project $PROJECT",after="--zone $ZONE");
gcr = xr.gcloud.args(before="compute --project $PROJECT",after="--zone $ZONE");
gcr1 = xr.gcloud.args(before="compute --project $PROJECT");
gcro = xro.gcloud.args(before="compute --project $PROJECT",after="--zone $ZONE");

# gsutil cp executables
gcp = x.gsutil.args("cp");
gcpo = xo.gsutil.args("cp");

define('SNAPSHOT',"oms-papino-*","snapshot on which boot disk is to be based")
define('DATADISKSIZE',200,"default data disk size (in Gb) for VM instances")
define('VMTYPE',"n1-standard-1","default VM type")

define('USER',E.USER,"default username to be used on remote machine")

define('VMNUM',1,"VM serial number")
define('VMNAME_Template',"${USER}-"+socket.gethostname().replace(".","-").lower()+"-$VMNUM","default VM instance name");
define('OUTPUT_BUCKET_Template',"gs://$USER/outputs/$VMNAME-$OUTDIR","default cloud storage destination for output products"); 

define('PROVISION_SCRIPT','./pyxis-provision.sh','provisioning script to run on remote VM')

def provision_vm (vmname="VMNAME"):
  """Waits for specified VM to come up and runs provisioning script""";
  name = interpolate_locals("vmname");
  for attempt in range(1,11):
    if gco("ssh $name --command 'if [ -x $PROVISION_SCRIPT ]; then $PROVISION_SCRIPT; fi'") is 0:
      break;
    if attempt is 1 and name not in get_vms():
      abort("no such VM $name")
    warn("VM $name is not up yet (attempt #$attempt), waiting for 5 seconds to retry");
    time.sleep(5);
  else:
    abort("failed to connect to VM $name after $attempt tries")
  info("VM $name has been provisioned ")
  return True;
  
def _version_suffix (x,sep='-'):
  """Helper function: given a string such as "foo-N", returns N as integer, or 0 if string does not match.""";
  try:
    return int(x.rsplit(sep,1)[-1]);
  except:
    return 0;

## create VM
def init_vm (vmname="$VMNAME",vmtype="$VMTYPE",
             autodelete=True,reuse_boot=True,autodelete_boot=None,wait=False,propagate=True,**kw):
  """Creates a GCE VM instance""";
  name,vmtype = interpolate_locals("vmname vmtype");
  # check if VM exists and needs to be deleted
  if autodelete and name in get_vms():
    warn("deleting existing VM $name");
    delete_vm(name,disks=False);
  # check if a boot disk needs to be created
  disks = get_disks();
  if name in disks:
    if reuse_boot:
      info("boot disk $name already exists, reusing (disable with reuse_boot=False)")
      if autodelete_boot is None:
        info("boot disk $name will not be auto-deleted when VM is destroyed")
        autodelete_boot = False;
    else:
      gc("disks delete $name --quiet")
      del disks[name];
  if name not in disks:
    snapshot = SNAPSHOT;
    if '*' in snapshot:
      matching = sorted(get_snapshots(snapshot).keys(),
        lambda a,b:-cmp(_version_suffix(a),_version_suffix(b)));
      snapshot = matching[0];
      info("using latest snapshot $snapshot");
    gc("disks create $name --source-snapshot $snapshot")
    if autodelete_boot is None:
      info("boot disk $name will be auto-deleted when VM is destroyed")
      autodelete_boot = True;
  # create VM
  scopes = "--scopes storage-rw"
  gc("instances create $name --machine-type $vmtype --disk name=$name mode=rw boot=yes auto-delete=%s $scopes"%("yes" if autodelete_boot else "no"));
  info("created VM instance $name, type $vmtype")
  # run provisioning script
  provision_vm(name);
  # attach disks
  for key,value in kw.iteritems():
    if key.startswith("attach_"):
      if isinstance(value,dict):
        attach_disk(key[len("attach_"):],**value);
      elif isinstance(value,int):
        attach_disk(key[len("attach_"):],size=value);
      else:
      	raise TypeError,"unknown data type for %s"%key;
  # provision with pyxis scripts in specified directory
  if propagate:
    propagate_scripts(name,dir=propagate if isinstance(propagate,str) else "");

def rsh (command,vmname='$VMNAME',bg=False):
  command,vmname = interpolate_locals("command vmname");
  if bg:
    gc("ssh $vmname --command 'screen -L -md $command'")
  else:
    gc("ssh $vmname --command '$command'")

def rpyxis (command,vmname='$VMNAME',dir=None,bg=False,wrapup=False):
  command,vmname = interpolate_locals("command vmname");
  cd = II("cd $dir;") if dir else "";
  wrap = II("--wrapup gce.wrapup") if wrapup else "";
  if bg:
    gc("ssh $vmname --command 'screen -L -md bash -i -c \"$cd pyxis gce.VMNAME=$vmname $command $wrap\"'")
  else:
    gc("ssh $vmname --command 'bash -i -c \"$cd pyxis gce.VMNAME=$vmname $command $wrap\"'")


def propagate_scripts (vmname="$VMNAME",dir=""):
  name,dir = interpolate_locals("vmname dir");
  # make sure the machine is ready -- retry the file copy until we succeed
  files = " ".join(list(glob.glob("pyxis-*py")) + list(glob.glob("pyxis-*.conf")));
  gc("copy-files $files $name:$dir");
  info("propagated $files to VM");


def _remote_attach_disk (diskname,mount,clear):
  if not os.path.exists(mount):
    x.sh("sudo mkdir $mount");
  x.sh("sudo /usr/share/google/safe_format_and_mount -m 'mkfs.ext4 -F' /dev/disk/by-id/google-$diskname $mount");
  x.sh("sudo chown $USER.$USER $mount");
  if clear:
    x.sh("sudo rm -fr $mount/*");
  # make symlink, if mounting at root level 
  mm = os.path.realpath(mount).split("/");
  if len(mm) < 3 and not os.path.exists(mm[-1]):
    gc("ln -s $mount");

def attach_disk (mount="data",diskname="${vmname}-$mount",vmname="$VMNAME",
                 size=None,snapshot=None,ssd=False,
                 init=False,clear=False,mode="rw",autodelete=False):
  name,diskname,disksize,mount = interpolate_locals("vmname diskname size mount")
  diskname = diskname.lower().replace("/","");
  disks = get_disks();
  if diskname in disks and init:
    info("disk $diskname exists and init=True, recreating")
    gc("disks delete $diskname");
    del disks[diskname];
  if diskname not in disks:
    disktype = "pd-ssd" if ssd else "pd-standard";
    info("disk $diskname does not exist, creating type $disktype${ size <disksize> Gb}${ from snapshot <snapshot}")
    if not snapshot:
      size = DATADISKSIZE;
    gc("disks create $diskname ${--size <disksize} --type $disktype ${--source-snapshot <snapshot}");
    clear = False;
  # attach disk to VM
  gc("instances attach-disk $name --disk $diskname --mode $mode --device-name $diskname")
  if autodelete:
    gc("instances set-disk-auto-delete --auto-delete $name --disk $diskname")
  # execute rest on remote
  rpyxis('gce._remote_attach_disk[:$diskname:,:$mount:,$clear]',name);
  info("attached disk $diskname as $name:$mount ($mode)")


def detach_disk (mount="data",vmname="$VMNAME",diskname="${vmname}-$mount"):
  name,diskname,mount = interpolate_locals("vmname diskname mount")
  gc("instances detach-disk $name --disk $diskname")
  info("detached disk $diskname from VM $name")


def get_vms ():
  return dict([ x.split(None,1) for x in gcr("instances list").split("\n")[1:] if x])

def list_vms ():
  gc("instances list");
  # vms = get_vms().items();
  # for name,data in sorted(vms):
  #   info("VM $name: $data");

def get_snapshots (pattern="*"):
  a = [ x.split(None,1) for x in gcr1("snapshots list").split("\n")[1:] if x ];
  return dict([ x for x in a if fnmatch.fnmatch(x[0],pattern) ]);

def list_snapshots ():
  gc1("snapshots list");

def get_disks ():
  return dict([ x.split(None,1) for x in gcr("disks list").split("\n")[1:] if x])

def list_disks ():
  gc("disks list");
  # vms = get_disks().items();
  # for name,data in sorted(vms):
  #   info("disk $name: $data");

def list_machine_types ():
  gc("machine-types list");

def delete_disk (*disknames):
  for disk in disknames:
    gc("disks delete $disk --quiet");

def delete_vm (vmname="$VMNAME",disks=True):
  """Deletes a GCE VM instance. If disks=True, deletes associated data disks.""";
  name = interpolate_locals("vmname");
  gco("instances delete $name --quiet");
  info("deleted VM instance $name" + ("; deleting asociated disks" if disks else ""));
  if disks:
    for key,value in get_disks().iteritems():
      if key.startswith(name+"-"):
        gc("disks delete $key --quiet");


def wrapup ():
  files = [ f for f in glob.glob("/var/log/syslog*") + 
            glob.glob(II("$OUTDIR/*txt")) +
            glob.glob(os.path.expanduser("~/screenlog.*")) if exists(f) ];
  if files:
    gcpo("%s $OUTPUT_BUCKET"%" ".join(files));
  x.sh("sudo poweroff")
