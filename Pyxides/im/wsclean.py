"""Pyxis module for MS-related operations""";
from Pyxis.ModSupport import *

import argo
import ms
import im
import subprocess

rm_fr = x.rm.args("-fr")
tigger_restore = x("tigger-restore")

# register ourselves with Pyxis and define the superglobals
register_pyxis_module(superglobals="MS LSM DESTDIR");

def STANDARD_IMAGER_OPTS_Template():
    """ Initialise standard imager options """
    global npix,cellsize,mode,stokes,weight,robust,niter,gain,threshold
    npix = im.npix
    cellsize = im.cellsize
    mode = im.mode
    stokes = im.stokes
    weight = im.weight
    robust = im.robust
    niter = im.niter
    gain = im.gain
    threshold = im.threshold

define('WSCLEAN_PATH','${im.WSCLEAN_PATH}','Path to WSCLEAN')

# dict of known lwimager arguments, by version number
# this is to accommodate newer versions
_wsclean_known_args = {1.4:set('name predict size scale nwlayers minuvw maxuvw maxw pol '
                       'joinpolarizations multiscale multiscale-threshold-bias multiscale-scale-bias '
                       'cleanborder niter threshold gain mgain smallinversion '
                       'nosmallinversion smallpsf gridmode nonegative negative '
                       'stopnegative interval channelrange channelsout join-channels '
                       'field weight natural mfsweighting superweight beamsize makepsf '
                       'imaginarypart datacolumn gkernelsize oversampling reorder no-reorder '
                       'addmodel addmodelapp savemodel wlimit mem absmem j'.split()),
                       0:set('addmodel addmodelapp savemodel'.split())
}

# whenever the path changes, find out new version number, and build new set of arguments
_wsclean_path_version = None,None;
def WSCLEAN_VERSION_Template (path='$WSCLEAN_PATH'):
    """ initilise imager arguments """
    # first check if wsclean is installed
    path = interpolate_locals('path')
    path = im.argo.findImager(path)
    if path is False:
        return -1
    global _wsclean_path_version,_wsclean_args
    if path != _wsclean_path_version[0]:
        _wsclean_path_version = path,wsclean_version()
        _wsclean_args = set()
        for version,args in _wsclean_known_args.iteritems():
            if version <= _wsclean_path_version[1][0]:
                _wsclean_args.update(args)
    return _wsclean_path_version[1]

def wsclean_version(path='${WSCLEAN_PATH}'):
    """ try to find wsclean version """
    path = interpolate_locals('path')
    std = subprocess.Popen([path,'--version'],stderr=subprocess.PIPE,stdout=subprocess.PIPE)
    if std.stderr.read():
        # if return error assume its version 0
        version = 0
    else:
        stdout = std.stdout.read().lower()
        version = stdout.split()
        ind = version.index('version')
        version = version[ind+1]
    info('$path version is $version')
    return version,""
    


def _run(msname='$MS',clean=False,path='${im.WSCLEAN_PATH}',**kw):
    """ Run WSCLEAN """

    msname,path = interpolate_locals('msname path')
    path = argo.findImager(path,imager_name='WSCLEAN')
    if path is False:
        abort('Could not find WSCLEAN in system path, alises or at $path')

    # map stokes and npix and cellsize to wsclean equivalents
    global scale,pol,size,weight
    scale = cellsize if isinstance(cellsize,(int,float)) else argo.toDeg(cellsize)
    pol = repr(list(stokes)).strip('[]').replace('\'','').replace(' ','')

    size = '%d %d'%(npix,npix)
    if weight is 'briggs':
        weight = '%s %.2f'%(weight,robust)
    
    # make dict of imager arguments that have been specified globally or locally
    args = dict([ (arg,globals()[arg]) for arg in _wsclean_args if arg in globals() and globals()[arg] is not None ]);
    args.update([ (arg,kw[arg]) for arg in _wsclean_args if arg in kw ])
    
    if not clean:
        args['niter'] = 0

    ms.FIELD is not None and args.setdefault('field',ms.FIELD)
    x.sh(argo.gen_run_cmd(path,args,suf='-',assign=' ',pos_args=[msname]))
   
def make_image(msname='$MS',image_prefix='${im.BASENAME_IMAGE}',column='${im.COLUMN}',
                path='${im.WSCLEAN_PATH}',
                restore=False,
                dirty=True,
                psf=False,
                restore_lsm=False,
                lsm='$LSM',
                algorithm='${im.CLEAN_ALGORITHM}',
                channelize='${im.IMAGE_CHANNELIZE}',
                psf_image='${im.PSF_IMAGE}',
                dirty_image='${im.DIRTY_IMAGE}',
                model_image='${im.MODEL_IMAGE}',
                residual_image='${im.RESIDUAL_IMAGE}',
                restored_image='${im.RESTORED_IMAGE}',
                fullrest_image='${im.FULLREST_IMAGE}',
                restoring_options='${im.RESTORING_OPTIONS}',**kw):
    """ run WSCLEAN """

    makedir('$DESTDIR')

    im.IMAGER = 'wsclean'
    path,msname,image_prefix,column,dirty_image,model_image,residual_image,restored_image,psf_image,channelize,\
      fullrest_image,restoring_optins = \
      interpolate_locals('path msname image_prefix column dirty_image model_image residual_image '
                         'restored_image psf_image channelize fullrest_image restoring_options')

    # Check if WSCLEAN is where it is said to be
    path = argo.findImager(path,imager_name='WSCLEAN')
    
    # wsclean requires a WEIGHT_SPECTRUM column in the MS
    argo.addcol(msname,colname='WEIGHT_SPECTRUM',valuetype='float',init_with=1) 
    
    # Cater for moresane
    moresane = False
    if restore and algorithm.lower() in ['moresane','pymoresane']:
        kw['niter'] = 0
        kw['makepsf'] = True
        psf = True
        if isinstance(restore,dict):
            kw0 = restore.copy()
        else: 
            kw0 = {}
        restore = False
        moresane = True
    else:
        if isinstance(restore,dict):
            kw.update(restore)
            restore = True
        elif not isinstance(restore,bool):
            restore = False

    kw['name'] = image_prefix    

    # Check channel selection options in kw
    if 'interval' in kw.keys():
        start,end = map(int,kw['interval'].split())
        ms.CHANSTART = start
        ms.NUMCHANS = end-start

    channelize = int(channelize)
    nr = 0
    if channelize and ms.NUMCHANS==1:
        ms.set_default_spectral_info()
        nr = ms.NUMCHANS//channelize
        if 'channelsout' in kw.keys():
            nr = kw['channelsout']

    nr = nr or ms.NUMCHANS//channelize
    if nr: kw['channelsout'] = nr

    if dirty: info("im.wsclean.make_image: making dirty image $dirty_image")
    if restore: info("                   (restored image is $restored_image \
model is $model_image, residual is $residual_image)")
    
    if psf and not restore:
        kw['makepsf'] = True

    if 'pol' not in kw.keys():
        pol = repr(list(stokes)).strip('[]').replace('\'','').replace(' ','')
    else:
        pol = kw['pol']
    _run(msname,clean=restore,**kw)

    # Combine images if needed
    if not channelize:
        if dirty:
            x.mv('${image_prefix}-dirty.fits $dirty_image')
        else: rm_fr('${image_prefix}-dirty.fits')

        if restore:
             x.mv('${image_prefix}-model.fits $model_image')
             x.mv('${image_prefix}-residual.fits $residual_image')
             x.mv('${image_prefix}-image.fits $restored_image')
             x.mv('${image_prefix}-psf.fits $psf_image')
        else:
            rm_fr('${image_prefix}-image.fits')
    else:
        def eval_list(vals):
            l = []
            for val in vals:
                l.append(II(val))
            return l

        # Combine component images from wsclean
        labels = ['%04d'%d for d in range(nr)]
        if psf or restore: 
            psfs = eval_list(['$image_prefix-%s-psf.fits'%d for d in labels])
            argo.combine_fits(psfs,outname=II('$image_prefix.psf.fits'),ctype='FREQ',keep_old=False)
        
        if len(pol.split(','))==1 :
            pol = ''

        for i in pol.split(','):

            if i : 
                i = '-%s'%i
         
            dirtys = eval_list(['$image_prefix-%s$i-dirty.fits'%d for d in labels])
            if dirty:
                argo.combine_fits(dirtys,outname=II('$image_prefix$i-dirty.fits') if pol else dirty_image,ctype='FREQ',keep_old=False)
                if not restore:
                    xo.sh('rm -fr ${image_prefix}*image*.fits')
            else: 
                for fits in dirtys:
                    rm_fr(fits)
            if restore:
                model = eval_list(['$image_prefix-%s$i-model.fits'%d for d in labels])
                argo.combine_fits(model,outname=II('$image_prefix$i-model.fits') if pol else model_image,ctype='FREQ',keep_old=False)

                residual = eval_list(['$image_prefix-%s$i-residual.fits'%d for d in labels])
                argo.combine_fits(residual,outname=II('$image_prefix$i-residual.fits') if pol else residual_image,ctype='FREQ',keep_old=False)

                restored = eval_list(['$image_prefix-%s$i-image.fits'%d for d in labels])
                argo.combine_fits(restored,outname=II('$image_prefix$i-image.fits') if pol else restored_image ,ctype='FREQ',keep_old=False)
                if not pol:
                    x.mv('${image_prefix}-MFS-image.fits %s'%(restored_image.replace('.restored.fits','-MFS.restored.fits')))

        if pol:
            if dirty: 
                dirtys = eval_list(['$image_prefix-%s-dirty.fits'%d for d in pol.split(',')])
                argo.combine_fits(dirtys,outname=dirty_image,ctype='STOKES',keep_old=False)

            if restore:
                model = eval_list(['$image_prefix-%s-model.fits'%d for d in pol.split(',')])
                argo.combine_fits(model,outname=model_image,ctype='STOKES',keep_old=False)
                model_mfs = eval_list(['$image_prefix-MFS-%s-model.fits'%d for d in pol.split(',')])
                argo.combine_fits(model_mfs,outname=model_image.replace('.model.fits','-MFS.model.fits'),ctype='STOKES',keep_old=False)

                residual = eval_list(['$image_prefix-%s-residual.fits'%d for d in pol.split(',')])
                argo.combine_fits(residual,outname=residual_image,ctype='STOKES',keep_old=False)
                residual_mfs = eval_list(['$image_prefix-MFS-%s-residual.fits'%d for d in pol.split(',')])
                argo.combine_fits(residual_mfs,outname=restored_image.replace('.residual.fits','-MFS.residual.fits'),ctype='STOKES',keep_old=False)

                restored = eval_list(['$image_prefix-%s-image.fits'%d for d in pol.split(',')])
                argo.combine_fits(restored,outname=restored_image,ctype='STOKES',keep_old=False)
                restored_mfs = eval_list(['$image_prefix-MFS-%s-image.fits'%d for d in pol.split(',')])
                argo.combine_fits(restored_mfs,outname=restored_image.replace('.restored.fits','-MFS.restored.fits'),ctype='STOKES',keep_old=False)

    if moresane:
        restored_image = restored_image.replace('wsclean','moresane')
        residual_image = residual_image.replace('wsclean','moresane')
        model_image = model_image.replace('wsclean','moresane')

        info(" im.moresane.deconv: making estored image $restored_image \
model is $model_image, residual is $residual_image)")

        im.moresane.deconv(dirty_image,psf_image,model_image=model_image,
                           residual_image=residual_image,
                           restored_image=restored_image,**kw0)
    if restore:
        if lsm and restore_lsm:
            info("Restoring LSM into FULLREST_IMAGE=${im.FULLREST_IMAGE}");
            opts = restore_lsm if isinstance(restore_lsm,dict) else {};
            tigger_restore(restoring_options,"-f",restored_image,lsm,fullrest_image,kwopt_to_command_line(**opts));

document_globals(make_image,"im.*_IMAGE COLUMN im.IMAGE_CHANNELIZE MS im.RESTORING_OPTIONS im.CLEAN_ALGORITHM ms.IFRS ms.DDID ms.FIELD ms.CHANRANGE")
