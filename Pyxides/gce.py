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

define('VM_SNAPSHOT',"oms-papino-*","snapshot on which VM boot disks are to be based")
define('VM_TYPE',"n1-standard-1","default VM type")

define('VM_USER',E.USER,"default username to be used on remote machine")

define('VM_NUM',1,"VM serial number, included in instance name")
define('VM_NAME_Template',"${VM_USER}-"+socket.gethostname().replace(".","-").lower()+"-$VM_NUM","default VM instance name");
define('VM_OUTPUT_BUCKET_Template',"gs://$VM_USER/outputs/$VM_NAME-$OUTDIR","default cloud storage destination for output products"); 

define('VM_DATADISKSIZE',200,"default data disk size (in Gb) for attach_disk()")

define('VM_PROVISION_SCRIPT','./pyxis-provision.sh','provisioning script to run on remote VM')

def provision_vm (vmname="$VM_NAME"):
  """Waits for specified VM to come up and runs provisioning script""";
  name = interpolate_locals("vmname");
  for attempt in range(1,11):
    if gco("ssh $name --command 'if [ -x $VM_PROVISION_SCRIPT ]; then $VM_PROVISION_SCRIPT; fi'") is 0:
      break;
    if attempt is 1 and name not in get_vms():
      abort("no such VM $name")
    warn("VM $name is not up yet (attempt #$attempt), waiting for 5 seconds to retry");
    time.sleep(5);
  else:
    abort("failed to connect to VM $name after $attempt tries")
  info("VM $name has been provisioned ")
  return True;

document_globals(provision_vm,"VM_NAME VM_PROVISION_SCRIPT PROJECT ZONE");
  
def _version_suffix (x,sep='-'):
  """Helper function: given a string such as "foo-N", returns N as integer, or 0 if string does not match.""";
  try:
    return int(x.rsplit(sep,1)[-1]);
  except:
    return 0;

## create VM
def init_vm (vmname="$VM_NAME",vmtype="$VM_TYPE",
             autodelete=True,reuse_boot=True,autodelete_boot=None,propagate=True,**kw):
  """Creates a GCE VM instance.
  vmname:           instance name
  vmtype:           VM type (use gce.list_machine_types() to get a list)
  autodelete:       if True, deletes any existing instance with same name
  reuse_boot:       if True and a boot disk with same name exists, reuses that
  autodelete_boot:  if True, boot disk will be auto-deleted when VM is shut down
  propagate:        if True, calls propagate_scripts() to copy Pyxis scripts from current
                    directory to VM. Can be set to a directory name to propagate to a 
                    specific directory on the remote machine.
  attach_XXX:       create additional disks. Use attach_XXX=N to create a disk of N Gb and 
                    attach to VM under /XXX (equivalent to calling attach_disk('XXX',size=N)). 
                    attach_XXX=dict(...) will call attach_disk('XXX',...)
""";
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
    snapshot = VM_SNAPSHOT;
    if '*' in snapshot:
      from past.builtins import cmp
      from functools import cmp_to_key
      matching = sorted(list(get_snapshots(snapshot).keys()),
        key=cmp_to_key(lambda a, b:-cmp(_version_suffix(a),_version_suffix(b))));
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
  for key,value in kw.items():
    if key.startswith("attach_"):
      if isinstance(value,dict):
        attach_disk(key[len("attach_"):],vmname=vmname,**value);
      elif isinstance(value,int):
        attach_disk(key[len("attach_"):],size=value,vmname=vmname);
      else:
      	raise TypeError("unknown data type for %s"%key);
  # provision with pyxis scripts in specified directory
  if propagate:
    propagate_scripts(name,dir=propagate if isinstance(propagate,str) else "");

document_globals(init_vm,"VM_NAME VM_TYPE VM_SNAPSHOT VM_DATADISKSIZE PROJECT ZONE");

def rsh (command,vmname='$VM_NAME',bg=False):
  """Executes a command on a VM""";
  command,vmname = interpolate_locals("command vmname");
  if bg:
    gc("ssh $vmname --command 'screen -L -md $command'")
  else:
    gc("ssh $vmname --command '$command'")

document_globals(rsh,"VM_NAME PROJECT ZONE");

def rpyxis (command,vmname='$VM_NAME',dir=None,bg=False,wrapup=False):
  """Executes a pyxis command on a VM
  command:    command(s) to execute
  vmname:     instance name
  dir:        change into directory before running command. Default will 
              run on home directory on VM.
  bg:         if False, waits until command has finished. If True, launches
              command remotely (under screen) and returns
  wrapup:     if True, remote will call gce.wrapup() after command has finished.
              This is generally used to copy output to GCE storage and kill the VM.
  """;
  command,vmname = interpolate_locals("command vmname");
  cd = II("cd $dir;") if dir else "";
  wrap = II("--wrapup gce.wrapup") if wrapup else "";
  if bg:
    gc("ssh $vmname --command 'screen -L -md bash -i -c \"$cd pyxis gce.VM_NAME=$vmname $command $wrap\"'")
  else:
    gc("ssh $vmname --command 'bash -i -c \"$cd pyxis gce.VM_NAME=$vmname $command $wrap\"'")

document_globals(rpyxis,"VM_NAME PROJECT ZONE");

def propagate_scripts (vmname="$VM_NAME",dir=""):
  """Copies pyxis-*.{py,conf} from current directory to VM.
  If 'dir' is specified, copies to specific directory, else copies to home directory.
  """
  name,dir = interpolate_locals("vmname dir");
  # make sure the machine is ready -- retry the file copy until we succeed
  files = " ".join(list(glob.glob("pyxis-*py")) + list(glob.glob("pyxis-*.conf")));
  if files:
    gc("copy-files $files $name:$dir");
    info("propagated $files to VM");
  else:
    info("no pyxis-*{py,conf} files in current directory, nothing to propagate")

document_globals(propagate_scripts,"VM_NAME PROJECT ZONE");

def _remote_attach_disk (diskname,mount,clear):
  """Internal helper function run by remote VM to attach a disk""";
  if not os.path.exists(mount):
    x.sh("sudo mkdir $mount");
  x.sh("sudo /usr/share/google/safe_format_and_mount -m 'mkfs.ext4 -F' /dev/disk/by-id/google-$diskname $mount");
  x.sh("sudo chown $VM_USER.$VM_USER $mount");
  if clear:
    x.sh("sudo rm -fr $mount/*");
  # make symlink, if mounting at root level 
  mm = os.path.realpath(mount).split("/");
  if len(mm) < 3 and not os.path.exists(mm[-1]):
    gc("ln -s $mount");

def attach_disk (mount="data",diskname="${vmname}-$mount",vmname="$VM_NAME",
                 size=None,snapshot=None,ssd=False,
                 init=False,clear=False,mode="rw",autodelete=False):
  """Attached an extra disk to a VM (creating the disk as needed).
  mount:        where to mount the disk, e.g. mount='data' mounts under /data
  diskname:     provide explicit name for the disk (otherwise auto-named as "vmname-mount"). 
                Can be used to attach previously created disks.
  vmname:       name of VM instance
  size:         disk size for new disks, VM_DATADISKSIZE by default
  snapshot:     init disk from a named snapshot (else create empty disk)
  ssd:          if True, creates (faster but more expensive) SSD disk
  init:         if True and disk already exists, deletes and re-creates it. If False, reuses.
  clear:        if True and disk already exists, wipes its data.
  mode:         default "rw". Use "ro" to attach as read-only.
  autodelete:   if True, disk will be deleted when the VM is shut down
  """
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
      size = VM_DATADISKSIZE;
    gc("disks create $diskname ${--size <disksize} --type $disktype ${--source-snapshot <snapshot}");
    clear = False;
  # attach disk to VM
  gc("instances attach-disk $name --disk $diskname --mode $mode --device-name $diskname")
  if autodelete:
    gc("instances set-disk-auto-delete --auto-delete $name --disk $diskname")
  # execute rest on remote
  rpyxis('gce._remote_attach_disk[:$diskname:,:$mount:,$clear]',name);
  info("attached disk $diskname as $name:$mount ($mode)")

document_globals(attach_disk,"VM_NAME VM_DATADISKSIZE PROJECT ZONE")

def detach_disk (mount="data",vmname="$VM_NAME",diskname="${vmname}-$mount"):
  """Detaches disk from VM instance
  mount:      mountpoint of disk.
  vmname:     name of VM instance.
  diskname:   explicit disk name, formed as vmname-mount by default.
  """;
  name,diskname,mount = interpolate_locals("vmname diskname mount")
  gc("instances detach-disk $name --disk $diskname")
  info("detached disk $diskname from VM $name")

document_globals(detach_disk,"VM_NAME PROJECT ZONE")

def get_vms ():
  """returns list of all VMs in zone""";
  return dict([ x.split(None,1) for x in gcr("instances list").split("\n")[1:] if x])
document_globals(get_vms,"PROJECT ZONE");

def list_vms ():
  """prints list of all VMs in zone""";
  gc("instances list");
document_globals(list_vms,"PROJECT ZONE");

def get_snapshots (pattern="*"):
  """returns list of all snapshots in zone""";
  a = [ x.split(None,1) for x in gcr1("snapshots list").split("\n")[1:] if x ];
  return dict([ x for x in a if fnmatch.fnmatch(x[0],pattern) ]);
document_globals(get_snapshots,"PROJECT ZONE");

def list_snapshots ():
  """prints list of all snapshots in zone""";
  gc1("snapshots list");
document_globals(list_snapshots,"PROJECT ZONE");

def get_disks ():
  """returns list of all disks in zone""";
  return dict([ x.split(None,1) for x in gcr("disks list").split("\n")[1:] if x])
document_globals(get_disks,"PROJECT ZONE");

def list_disks ():
  """prints list of all disks in zone""";
  gc("disks list");
  # vms = get_disks().items();
  # for name,data in sorted(vms):
  #   info("disk $name: $data");
document_globals(list_disks,"PROJECT ZONE");

def list_machine_types ():
  """prints list of all VM types available in zone (i.e. possible VM_TYPE settings)""";
  gc("machine-types list");
document_globals(list_machine_types,"PROJECT ZONE");

def delete_disk (*disknames):
  """deletes the specified disk(s)"""
  for disk in disknames:
    gc("disks delete $disk --quiet");
document_globals(delete_disk,"PROJECT ZONE");

def delete_vm (vmname="$VM_NAME",disks=True):
  """Deletes a GCE VM instance. If disks=True, deletes associated data disks.""";
  name = interpolate_locals("vmname");
  gco("instances delete $name --quiet");
  info("deleted VM instance $name" + ("; deleting asociated disks" if disks else ""));
  if disks:
    for key,value in get_disks().items():
      if key.startswith(name+"-"):
        gc("disks delete $key --quiet");
document_globals(delete_vm,"VM_NAME PROJECT ZONE");


def wrapup ():
  """Helper function run on remote VMs to wrap up (i.e. if wrapup=True is given to gce.rpyxis()). Copies
  outputs to cloud storage and shuts down the VM.
  """
  files = [ f for f in glob.glob("/var/log/syslog*") + 
            glob.glob(II("$OUTDIR/*txt")) +
            glob.glob(os.path.expanduser("~/screenlog.*")) if exists(f) ];
  if files:
    gcpo("%s $VM_OUTPUT_BUCKET"%" ".join(files));
  x.sh("sudo poweroff")
document_globals(wrapup,"VM_NAME VM_OUTPUT_BUCKET OUTDIR");
