# A set of useful functions to help navigate the murky waters of radio 
# interferometry packages
import os
import sys
import pyfits
import numpy
import math
import pyrap.tables
import subprocess
import im
import tempfile
import ms
import glob
import time
# Load some Pyxis functionality
from Pyxis.ModSupport import *

# register ourselves with Pyxis and define the superglobals
register_pyxis_module(superglobals="MS LSM")

rm_fr = x.rm.args("-fr")

def fits2casa (input,output):
    """Converts FITS image to CASA image."""
    if exists(output):
        rm_fr(output)
    x.imagecalc("in='$input'","out=$output",split_args=False)

def make_threshold_mask (input="${im.RESTORED_IMAGE}",threshold=0,output="$im.MASK_IMAGE",high=1,low=0):
    """
    Makes a mask image by thresholding the input image at a given value. The output image is a copy of the input image,
    with pixel values of 'high' (1 by default) where input pixels are >= threshold, and 'low' (0 default) where pixels are <threshold.
    """
    input,output = interpolate_locals("input output")
    ff = pyfits.open(input)
    d = ff[0].data
    d[d<threshold] = low
    d[d>threshold] = high
    ff.writeto(output,clobber=True)
    info("made mask image $output by thresholding $input at %g"%threshold)

document_globals(make_threshold_mask,"im.RESTORED_IMAGE im.MASK_IMAGE");

define("COPY_IMAGE_TO_Template", "${MS:BASE}.imagecopy.fits","container for image copy")
def make_empty_image (msname="$MS",image="${COPY_IMAGE_TO}",channelize=None,**kw0):
    msname,image = interpolate_locals("msname image")
    # setup imager options
    kw0.update(dict(ms=msname,channelize=channelize,dirty=True,dirty_image=image,restore=False,
                   select="ANTENNA1==0 && ANTENNA2==1"))
    import im.lwimager
    im.lwimager.make_image(**kw0);
    # sometime this behaves funny, so leave nothing to chance
    hdu = pyfits.open(image)
    hdu[0].data[...] = 0
    hdu.writeto(image,clobber=True)
    info("created empty image $image")


def combine_fits(fitslist,outname='combined.fits',axis=0,ctype=None,keep_old=False):
    """ Combine a list of fits files along a given axiis.
       
       fitslist: list of fits file to combine
       outname: output file name
       axis: axis along which to combine the files (numpy index. not FITS index)
       ctype: Axis label in the fits header (if given, axis will be ignored)
       keep_old: Keep component files after combining?
    """

    hdu = pyfits.open(fitslist[0])[0]
    hdr = hdu.header
    naxis = hdr['NAXIS']

    # find axis via CTYPE key
    if ctype is not None:
        for i in range(1,naxis+1):
            if hdr['CTYPE%d'%i].startswith(ctype):
                axis = naxis - i # fits to numpy convention


    fits_ind = abs(axis-naxis)
    crval = hdr['CRVAL%d'%fits_ind]

    imslice = [slice(None)]*naxis
    _sorted = sorted([pyfits.open(fits) for fits in fitslist],
                    key=lambda a: a[0].header['CRVAL%d'%(naxis-axis)])

    # define structure of new FITS file
    nn = [ hd[0].header['NAXIS%d'%(naxis-axis)] for hd in _sorted] 
    shape = list(hdu.data.shape)
    shape[axis] = sum(nn)
    data = numpy.zeros(shape,dtype=float)

    for i,hdu0 in enumerate(_sorted):
        h = hdu0[0].header
        d = hdu0[0].data
        imslice[axis] = range(sum(nn[:i]),sum(nn[:i+1]) )
        data[imslice] = d
        if crval > h['CRVAL%d'%fits_ind]:
            crval =  h['CRVAL%d'%fits_ind]

    # update header
    hdr['CRVAL%d'%fits_ind] = crval
    hdr['CRPIX%d'%fits_ind] = 1
    
    pyfits.writeto(outname,data,hdr,clobber=True)
    
    # remove old files
    if not keep_old:
        for fits in fitslist:
            os.system('rm -f %s'%fits)


def splitfits(fitsname,chunks,axis=None,ctype=None,prefix=None):
    """ split fits data along a given axis in N chunks """
    
    prefix = prefix or fitsname[:-5] # take everthing but .FITS/.fits
    hdu = pyfits.open(fitsname)
    hdr = hdu[0].header
    data = hdu[0].data.copy()    
    naxis = hdr["NAXIS"]

    if axis is None and ctype is None:
        abort('Please specify either axis or ctype')
    # find axis via CTYPE key
    if ctype :
        for i in range(1,naxis+1):
            if hdr['CTYPE%d'%i].startswith(ctype):
                axis = naxis - i # fits to numpy indexing

    crval = hdr['CRVAL%d'%(naxis-axis)]
    cdelt = hdr['CDELT%d'%(naxis-axis)]
    crpix = hdr['CRPIX%d'%(naxis-axis)]
    # shift crval to crpix=1
    crval = crval - (crpix-1)*cdelt

    nstacks = hdr['NAXIS%d'%(naxis-axis)]
    nchunks = nstacks//chunks
    info("The FITS file $fitsname has $nstacks stacks along this axis. Breaking it up to $nchunks images")

    outfiles = []
    for i in range(0,nchunks):

        _slice = [slice(None)]*naxis
        _slice[axis] = range(i*chunks,(i+1)*chunks if i+1!=nchunks else nstacks)
	warn(data.shape,_slice)
        hdu[0].data = data[_slice]
        hdu[0].header['CRVAL%d'%(naxis-axis)] = crval + i*cdelt*chunks
        hdu[0].header['CRPIX%d'%(naxis-axis)] = 1
        outfile = '%s-%04d.fits'%(prefix,i)
        outfiles.append(outfile)
        info("Making chunk $i : %s. File is $outfile"%repr(_slice[axis]))
        hdu.writeto(outfile,clobber=True)

    hdu.close()
    return outfiles

    
def addcol(msname='$MS',colname=None,shape=None,
           data_desc_type='array',valuetype=None,init_with=0,**kw):
    """ add column to MS 
        msanme : MS to add colmn to
        colname : column name
        shape : shape
        valuetype : data type 
        data_desc_type : 'scalar' for scalar elements and array for 'array' elements
        init_with : value to initialise the column with 
    """
    msname = interpolate_locals('msname')
    tab = pyrap.tables.table(msname,readonly=False)

    try: 
        tab.getcol(colname)
        info('Column already exists')
    except RuntimeError:
        info('Attempting to add %s column to %s'%(colname,msname))
        from pyrap.tables import maketabdesc
        valuetype = valuetype or 'complex'
        if shape is None: 
            dshape = list(tab.getcol('DATA').shape)
            shape = dshape[1:]
        if data_desc_type=='array':
            from pyrap.tables import makearrcoldesc
            coldmi = tab.getdminfo('DATA') # God forbid this (or the TIME) column doesn't exist
            coldmi['NAME'] = colname.lower()
            tab.addcols(maketabdesc(makearrcoldesc(colname,init_with,shape=shape,valuetype=valuetype)),coldmi)
        elif data_desc_type=='scalar':
            from pyrap.tables import makescacoldesc
            coldmi = tab.getdminfo('TIME')
            coldmi['NAME'] = colname.lower()
            tab.addcols(maketabdesc(makescacoldesc(colname,init_with,valuetype=valuetype)),coldmi)
        info('Column added successfuly.')
    tab.close()


def toJy(val):
    _convert = dict(m=1e-3,u=1e-6,n=1e-9)
    unit = val.lower().split('jy')[0][-1]
    if str.isalpha(unit) :
        val= val.lower().split(unit+'jy')[0]
        return float(val)*_convert[unit]
    else:
        return float(val.lower().split('jy')[0])


def toDeg(val):
    """Convert angle to Deg. returns a float. val must be in form: 2arcsec, 2arcmin, or 2rad"""
    import math
    _convert = {'arcsec':3600.,'arcmin':60.,'rad':math.pi/180.,'deg':1.}
    val = val or cellsize
    ind = 1
    if not isinstance(val,str): 
        raise ValueError('Angle must be a string, e.g 10arcmin')
    for i,char in enumerate(val):
            if char is not '.':
                 try: 
                      int(char)
                 except ValueError:
                     ind = i
                     break
    a,b = val[:ind],val[ind:]
    try: 
        return float(a)/_convert[b]
    except KeyError: 
        abort('Could not recognise unit [%s]. Please use either arcsec, arcmin, deg or rad'%b)


def findImager(path,imager_name=None):
    """ Find imager"""
    ispath = len(path.split('/'))>1
    if ispath :
        if os.path.exists(path): 
            return path
        else : 
            return False
    # Look in system path
    check_path = subprocess.Popen(['which',path],stderr=subprocess.PIPE,stdout=subprocess.PIPE)
    stdout = check_path.stdout.read().strip()
    if stdout : 
        return path
#   # Check aliases
#   ##TODO: [@sphe] Potential issues with looking in aliases. Might need to review this
#   stdout = subprocess.Popen(['grep',path,'$HOME/.bash_aliases'],stderr=subprocess.PIPE,stdout=subprocess.PIPE)
#   err,out = stdout.stderr.read(),stdout.stdout.read()
#   if err:
#       return False
#   elif out: 
#       path = out.split('=')[-1].strip("'")
#       path = path.split('#')[0] # Incase there is a comment im the line
#       return path
    else:
        return False # Exhausted all sensible options, give up. 


def swap_stokes_freq(fitsname,freq2stokes=False):
    print 'Checking STOKES and FREQ in FITS file, might need to swap these around.'
    hdu = pyfits.open(fitsname)[0]
    hdr = hdu.header
    data = hdu.data
    if hdr['NAXIS']<4:
        print 'Editing fits file [%s] to make it usable by the pipeline.'%fitsname
        isfreq = hdr['CTYPE3'].startswith('FREQ')
        if not isfreq :
          return False
        hdr.update('CTYPE4','STOKES')
        hdr.update('CDELT4',1)
        hdr.update('CRVAL4',1)
        hdr.update('CUNIT4','Jy/Pixel')
        data.resize(1,*data.shape)
    if freq2stokes:
        if hdr["CTYPE3"].startswith("FREQ") : return 0;
        else:
            hdr0 = hdr.copy()
            hdr.update("CTYPE4",hdr0["CTYPE3"])
            hdr.update("CRVAL4",hdr0["CRVAL3"])
            hdr.update("CDELT4",hdr0["CDELT3"])
            try :
                hdr.update("CUNIT4",hdr0["CUNIT3"])
            except KeyError: 
                hdr.update('CUNIT3','Hz    ')
            #--------------------------
            hdr.update("CTYPE3",hdr0["CTYPE4"])
            hdr.update("CRVAL3",hdr0["CRVAL4"])
            hdr.update("CDELT3",hdr0["CDELT4"])
            try :
                hdr.update("CUNIT3",hdr0["CUNIT4"])
            except KeyError: 
                hdr.update('CUNIT4','Jy/Pixel    ')
                print ('Swapping FREQ and STOKES axes in the fits header [%s]'%fitsname)
            pyfits.writeto(fitsname,np.rollaxis(data,1),hdr,clobber=True)
    elif hdr["CTYPE3"].startswith("FREQ"):
        hdr0 = hdr.copy()
        hdr.update("CTYPE3",hdr0["CTYPE4"])
        hdr.update("CRVAL3",hdr0["CRVAL4"])
        hdr.update("CDELT3",hdr0["CDELT4"])
        try :
            hdr.update("CUNIT3",hdr0["CUNIT4"])
        except KeyError: 
            hdr.update('CUNIT3','Jy/Pixel    ')
        #--------------------------
        hdr.update("CTYPE4",hdr0["CTYPE3"])
        hdr.update("CRVAL4",hdr0["CRVAL3"])
        hdr.update("CDELT4",hdr0["CDELT3"])
        try :
            hdr.update("CUNIT4",hdr0["CUNIT3"])
        except KeyError: 
            hdr.update('CUNIT4','Hz    ')
        print 'Swapping FREQ and STOKES axes in the fits header [%s]. This is a  MeqTrees work arround.'%fitsname
        pyfits.writeto(fitsname,np.rollaxis(data,1),hdr,clobber=True)
    return 0


def gen_run_cmd(path,options,suf='',assign='=',lv_str=False,pos_args=None):
    """ Generate command line run command """

    pos_args = pos_args or []
    run_cmd = '%s '%path

    for key,val in options.iteritems():
        if val is not None:
            if isinstance(val,str) and lv_str:
                val = '"%s"'%val
            if isinstance(val,bool) and suf:
                if val:
                    run_cmd+='%s%s '%(suf,key)
            else:
                run_cmd+='%s%s%s%s '%(suf,key,assign,val)

    for arg in pos_args:
        run_cmd += '%s '%arg
    return run_cmd


def icasa(taskname,mult=None,**kw0):
    """ 
      runs a CASA task given a list of options.
      A given task can be run multiple times with a different options, 
      in this case the options must be parsed as a list/tuple of dictionaries via mult, e.g 
      icasa('exportfits',mult=[{'imagename':'img1.image','fitsimage':'image1.fits},{'imagename':'img2.image','fitsimage':'image2.fits}]). 
      Options you want be common between the multiple commands should be specified as key word args.
    """

    # create temp directory from which to run casapy
    td = tempfile.mkdtemp(dir='.')
    # we want get back to the working directory once casapy is launched
    cdir = os.path.realpath('.')

    if mult:
        if isinstance(mult,(tuple,list)):
            for opts in mult:
                opts.update(kw0)
        else:
            mult.upadte(kw0)
            mult = [mult]
    else:
        mult = [kw0]

    run_cmd = """ """
    for kw in mult:
        task_cmds = ''
        for key,val in kw.iteritems():
            if isinstance(val,str):
                 val = '"%s"'%val
            task_cmds += '\n%s=%s'%(key,val)
        run_cmd += """
import os
os.chdir('%s')
taskname = '%s'
%s
go()

"""%(cdir,taskname,task_cmds)

    tf = tempfile.NamedTemporaryFile(suffix='.py')
    tf.write(run_cmd)
    tf.flush()
    t0 = time.time()
    # all logging information will be in the pyxis log files 
    x.sh('cd $td && casapy --nologger --log2term --nologfile -c %s'%(tf.name))

    # log taskname.last 
    task_last = '%s.last'%taskname
    if exists(task_last):
        with open(task_last,'r') as last:
            info('${taskname}.last is: \n %s'%last.read() )

    # remove temp directory. This also gets rid of the casa log files; so long suckers!
    rm_fr(td,task_last)
    tf.close()
