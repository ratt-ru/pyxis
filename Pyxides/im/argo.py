# A set of useful functions to help navigate the murky waters of radio 
# inteferometry packages
import os
import sys
import pyfits
import numpy
import math
import pyrap.tables
import subprocess

# borrow some Pyxis functionality
from Pyxis.ModSupport import *

def fits2casa (input,output):
    """Converts FITS image to CASA image."""
    if exists(output):
        rm_fr(output)
    x.imagecalc("in='$input'","out=$output",split_args=False)

def combine_fits(fitslist,outname='combined.fits',axis=0,ctype=None,keep_old=False):
    """ Combine a list of fits files along a given axiis"""

    hdu = pyfits.open(fitslist[0])[0]
    hdr = hdu.header
    naxis = hdr['NAXIS']

    # find axis via CTYPE key
    if ctype is not None:
        for i in range(1,naxis+1):
            if hdr['CTYPE%d'%i].startswith(ctype):
                axis = naxis - i # fits to numpy convention

    # define structure of new FITS file
    shape = list(hdu.data.shape)
    shape[axis] = len(fitslist)

    fits_ind = abs(axis-naxis)
    crval = hdr['CRVAL%d'%fits_ind]
    data = numpy.zeros(shape,dtype=float)

    imslice = [slice(None)]*naxis
    for i,fits in enumerate(fitslist):
        hdu = pyfits.open(fits)[0]
        h = hdu.header
        d = hdu.data
        imslice[axis] = i
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

def addcol(msname,colname,shape=None,valuetype=None,init_with=0):
    """ add column to MS """

    tab = pyrap.tables.table(msname,readonly=False)

    try: 
        tab.getcol(colname)
        print 'Coulmn already exists'
    except RuntimeError:
        print 'Attempting to add %s column to %s'%(colname,msname)
        from pyrap.tables import maketabdesc
        from pyrap.tables import makearrcoldesc
        coldmi = tab.getdminfo('DATA')
        dshape = list(tab.getcol('DATA').shape)
        coldmi['NAME'] = colname.lower()
        if shape is None: 
            shape = dshape[1:]
        else:
            valuetype = valuetype or 'complex'
        tab.addcols(maketabdesc(makearrcoldesc(colname,init_with,shape=shape,valuetype=valuetype)),coldmi)
        data = numpy.zeros(dshape,dtype=valuetype)
        if init_with is not 0:
            nrows = dshape[0]
            rowchunk = nrows/10
            for row0 in range(0,nrows,rowchunk):
                nr = min(rowchunk,nrows-row0)
                data[row0:(row0+nr)] = init_with
                tab.putcol(colname,data[row0:(row0+nr)],row0,nr)
        print 'Column added successfuly.'
    tab.close()

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
    # Check aliases
    ##TODO: [@sphe] Potential issues with looking in aliases. Might need to review this
    stdout = os.popen('grep %s $HOME/.bash_aliases'%path).read().strip()
    if stdout: 
        path = stdout.split('=')[-1].strip("'")
        path = path.split('#')[0] # Incase there is a comment im the line
        return path
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

def gen_run_cmd(path,options,suf='',assign='=',pos_args=None):
    """ Generate command line run command """

    pos_args = pos_args or []
    run_cmd = '%s '%path

    for key,val in options.iteritems():
        if val is not None:
            if isinstance(val,bool) and not suf:
                if val:
                    run_cmd+='%s%s '%(suf,key)
            else:
                run_cmd+='%s%s%s%s '%(suf,key,assign,val)

    for arg in pos_args:
        run_cmd += '%s '%arg
    return run_cmd
