"""Pyxis module for MS-related operations""";
from __future__ import absolute_import, print_function, division

from Pyxis.ModSupport import *

from . import argo
from Pyxides import ms
from Pyxides import im
import subprocess,glob

rm_fr = x.rm.args("-fr")
tigger_restore = x("tigger-restore")

# Keep wsclean gridding image? 
KEEP_GRIDDING_IMAGE = False        
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
define('IMAGER','wsclean','Imager name')

# dict of known lwimager arguments, by version number
# this is to accommodate newer versions
_wsclean_known_args = {0:set('name predict size scale nwlayers minuvw maxuvw maxw pol '
                       'joinpolarizations multiscale multiscale-threshold-bias multiscale-scale-bias '
                       'cleanborder niter threshold gain mgain smallinversion '
                       'nosmallinversion smallpsf gridmode nonegative negative '
                       'stopnegative interval channelrange joinchannels '
                       'field weight natural mfsweighting superweight beamsize makepsf '
                       'imaginarypart datacolumn gkernelsize oversampling reorder no-reorder '
                       'addmodel addmodelapp savemodel wlimit'.split()),
                       1.4:set('channelsout mem absmem j'.split()),
                       1.5:set('fitbeam nofitbeam circularbeam ellipticalbeam beamshape tempdir '                                
                               'savegridding minuvw-m maxuvw-m'.split()),
                       1.6:set('dft-predict'),
                       1.7:set('moresane-ext casamask fitsmask mgain intervalsout ' 
                               'no-update-model-required saveweights'.split()),
                       1.8:set('moresane-arg moresane-sl'.split()),
                       1.9:set('fit-spectral-pol fit-spectral-log-pol deconvolution-channels'.split())
}

# whenever the path changes, find out new version number, and build new set of arguments
_wsclean_path_version = None,None;

def WSCLEAN_VERSION_Template (path='$WSCLEAN_PATH'):
    """ initilise imager arguments """

    # first check if wsclean is installed
    path = interpolate_locals('path')
    path = argo.findImager(path)
    if path is False:
        return -1

    global _wsclean_path_version,_wsclean_args
    if path != _wsclean_path_version[0]:
        _wsclean_path_version = path,wsclean_version()
        _wsclean_args = set()
        for version,args in _wsclean_known_args.items():
            if version <= _wsclean_path_version[1][0]:
                _wsclean_args.update(args)

    # the following options are not versions > 1.4 
    if _wsclean_path_version[1][0]>=1.4:
        for item in 'addmodel addmodelapp savemodel'.split():
            _wsclean_args.discard(item)
    return _wsclean_path_version[1][0]

def wsclean_version(path='${WSCLEAN_PATH}'):
    """ try to find wsclean version """

    path = interpolate_locals('path')
    std = subprocess.Popen([path,'-version'],stderr=subprocess.PIPE,stdout=subprocess.PIPE)
    stderr = str(std.stderr.read())
    if not stderr:
        # if return error assume its version 0
        version = '0.0'
        tail = ""
    else:
        stdout = str(std.stdout.read()).lower()
        version = stdout.split()
        try:
            ind = version.index('version')
            version = version[ind+1].split('-')[0]
            tail = version.split('-')[-1] if '-' in version else ""
        except ValueError:        
            version = '0.0'
            tail = ""
    info('$path version is $version${-<tail}')

    if '.' in version:
        if version.startswith('1.9') or version.startswith('1.10') or \
            version.startswith('1.11') or version.startswith('1.12') or \
            version.startswith('2.'):
            info("using wsclean 1.9 interface for $version")
            version = '1.9'
        try:
            version = list(map(int,version.split('.')))
        except ValueError: 
            version = 0,0
        vstr = '%d.' + '%d'*(len(version)-1)
        version = float(vstr%(tuple(version)))
    return version,tail

def _run(msname='$MS',clean=False,path='${im.WSCLEAN_PATH}',**kw):
    """ Run WSCLEAN """
    msname,path = interpolate_locals('msname path')
    path = argo.findImager(path,imager_name='WSCLEAN')
    if path is False:
        abort('Could not find WSCLEAN in system path, alises or at $path')

    # make dict of imager arguments that have been specified globally or locally
    args = dict([ (arg,globals()[arg.replace("-","_")]) for arg in _wsclean_args 
                    if arg.replace("-","_") in globals() and globals()[arg.replace("-","_")] is not None ]);
    args.update([ (arg,kw[arg]) for arg in _wsclean_args if arg in kw ])

    # map image size/resolution parameters
    csz = kw.get('cellsize',cellsize)
    np = kw.get('npix',npix)
    args['scale'] = csz if isinstance(csz,(int,float)) else argo.toDeg(csz)
    args['size']= '%d %d'%(np,np)

    # map weight parameters
    wgt = args['weight'];
    if wgt == "robust" or wgt == "briggs":
        args['weight'] = 'briggs %.2f'%(kw.get('robust',robust))

    # map threshold
    if isinstance(args['threshold'],str):
        args['threshold'] = im.argo.toJy(args['threshold'])
    
    # map clean parameter
    if not clean:
        args['niter'] = 0

    ms.FIELD is not None and args.setdefault('field',ms.FIELD)
    x.sh(argo.gen_run_cmd(path,args,suf='-',assign=' ',pos_args=[msname] if not isinstance(msname,(list,tuple)) else msname))
   
def make_image(msname='$MS',image_prefix='${im.BASENAME_IMAGE}',column='${im.COLUMN}',
               mslist=None,         # if given, overrieds msname
                path='${WSCLEAN_PATH}',
                imager='$IMAGER',
                restore=False,
                dirty=True,
                psf=False,
                restore_lsm=False,
                lsm='$LSM',
                algorithm='${im.CLEAN_ALGORITHM}',
                channelize=None,
                psf_image='${im.PSF_IMAGE}',
                dirty_image='${im.DIRTY_IMAGE}',
                model_image='${im.MODEL_IMAGE}',
                residual_image='${im.RESIDUAL_IMAGE}',
                restored_image='${im.RESTORED_IMAGE}',
                fullrest_image='${im.FULLREST_IMAGE}',
                restoring_options='${im.RESTORING_OPTIONS}',
                keep_component_images=False,
                **kw):
    """ run WSCLEAN """

    makedir('$DESTDIR')
    _imager = im.IMAGER
    im.IMAGER = II(imager)
    #Add algorithm label if required
    if im.DECONV_LABEL and restore:
        if isinstance(im.DECONV_LABEL,bool):
            if im.DECONV_LABEL:
                im.DECONV_LABEL = algorithm
    elif im.DECONV_LABEL is False:
        im.DECONV_LABEL = None

    path,msname,image_prefix,column,dirty_image,model_image,residual_image,restored_image,psf_image,channelize,\
      fullrest_image,restoring_options = \
      interpolate_locals('path msname image_prefix column dirty_image model_image residual_image '
                         'restored_image psf_image channelize fullrest_image restoring_options')

    # Check if WSCLEAN is where it is said to be
    path = argo.findImager(path,imager_name='WSCLEAN')
    
    # wsclean requires a WEIGHT_SPECTRUM column in the MS
    if wsclean_version()[0]<1.6:
        argo.addcol(msname,colname='WEIGHT_SPECTRUM',valuetype='float',init_with=1) 
    
    if 'datacolumn' not in list(kw.keys()):
        kw['datacolumn'] = column
     
    # Cater for moresane
    do_moresane = False
    if restore and algorithm.lower() in ['moresane','pymoresane']:
        kw['niter'] = 0
        kw['makepsf'] = True
        psf = True
        dirty = True
        if isinstance(restore,dict):
            kw0 = restore.copy()
        else: 
            kw0 = {}
        restore = False
        do_moresane = True
        from im import moresane
    else:
        if isinstance(restore,dict):
            kw.update(restore)
            restore = True
        elif not isinstance(restore,bool):
            restore = False

    kw['name'] = image_prefix    

    # Check channel selection options in kw
    if 'channelrange' in list(kw.keys()):
        if isinstance(kw['channelrange'],str):
            start,end = list(map(int,kw['channelrange'].split()))
        else:
            start,end = kw['channelrange']
    else:
        start,end = ms.CHANSTART,ms.CHANSTART+ms.NUMCHANS;
        # if multiple MSs are specified, adjust channel range
        if mslist:
            end = ms.TOTAL_CHANNELS*(len(mslist)-1) + end

    kw['channelrange'] = "%d %d"%(start,end);

    nr = 1 
    if not channelize:
        channelize = im.IMAGE_CHANNELIZE
    if channelize:
        nr = (end-start)//channelize
        kw['channelsout'] = nr
    if nr ==1:
        channelize=False
   
    if dirty: info("im.wsclean.make_image: making dirty image $dirty_image")
    if restore: info(" making restored image $restored_image\
                    (model is $model_image, residual is $residual_image)")
    
    if psf and not restore:
        kw['makepsf'] = True

    if 'pol' in list(kw.keys()):
        pol = kw['pol']
    elif 'stokes' in list(kw.keys()):
        pol = kw['pol'] = kw.pop('stokes')
    else:
        pol = stokes
        kw['pol'] = pol

    if ',' in pol:
        pol = pol.split(',')
    kw['clean'] = restore

    # also accepts list of MSs
    _run(mslist or msname,**kw)

    # delete gridding image unless user wants it
    if not KEEP_GRIDDING_IMAGE:
        rm_fr('$image_prefix-gridding.fits')

    # delete first-residual images
    first_residual_images = glob.glob(II("$image_prefix-*-first-residual.fits"))
    if first_residual_images:
        rm_fr(" ".join(first_residual_images))

    #TODO(sphe): always keep wsclean MFS images?
    # Combine images if needed
#    mfs = mode if 'mode' not in kw.keys() else kw['mode']
#    mfs = mode=='mfs'
#    abort(mfs,mode)

    def eval_list(vals):
        l = []
        for val in vals:
            l.append(II(val))
        return l

    def combine_pol(pol,image_prefix=None,mfs=False):
        dirtys = eval_list(['$image_prefix-%s-dirty.fits'%d for d in pol])
        if dirty:
            argo.combine_fits(dirtys,outname=dirty_image,ctype='STOKES',keep_old=keep_component_images)
        else:
            for item in dirtys:
                rm_fr(item)

        if restore:
            model = eval_list(['$image_prefix-%s-model.fits'%d for d in pol])
            argo.combine_fits(model,outname=model_image,ctype='STOKES',keep_old=keep_component_images)

            residual = eval_list(['$image_prefix-%s-residual.fits'%d for d in pol])
            argo.combine_fits(residual,outname=residual_image,ctype='STOKES',keep_old=keep_component_images)

            restored = eval_list(['$image_prefix-%s-image.fits'%d for d in pol])
            argo.combine_fits(restored,outname=restored_image,ctype='STOKES',keep_old=keep_component_images)

            if mfs:
                model_mfs = eval_list(['$image_prefix-MFS-%s-model.fits'%d for d in pol])
                argo.combine_fits(model_mfs,
                       outname=model_image.replace('.model.fits','-MFS.model.fits'),
                       ctype='STOKES',keep_old=keep_component_images)

                residual_mfs = eval_list(['$image_prefix-MFS-%s-residual.fits'%d for d in pol])
                argo.combine_fits(residual_mfs,
                       outname=residual_image.replace('.residual.fits','-MFS.residual.fits'),
                       ctype='STOKES',keep_old=keep_component_images)

                restored_mfs = eval_list(['$image_prefix-MFS-%s-image.fits'%d for d in pol])
                argo.combine_fits(restored_mfs,
                       outname=restored_image.replace('.restored.fits','-MFS.restored.fits'),
                       ctype='STOKES',keep_old=False)
        else:
            for fits in ['$image_prefix-%s-image.fits'%d for d in pol]:
                rm_fr(fits)

    if not channelize:
        if psf:
            x.mv('${image_prefix}-psf.fits $psf_image')
        elif restore:
            rm_fr('${image_prefix}-psf.fits')
        if len(pol)>1:
            combine_pol(pol,image_prefix)
        else:
            if dirty:
                x.mv('${image_prefix}-dirty.fits $dirty_image')
            else: 
                rm_fr('${image_prefix}-dirty.fits')

            if restore:
                 x.mv('${image_prefix}-model.fits $model_image')
                 x.mv('${image_prefix}-residual.fits $residual_image')
                 x.mv('${image_prefix}-image.fits $restored_image')
                # x.mv('${image_prefix}-psf.fits $psf_image')
            else:
                rm_fr('${image_prefix}-image.fits')
    else:
        # Combine component images from wsclean
        labels = ['%04d'%d for d in range(nr)]
        psfs = eval_list(['$image_prefix-%s-psf.fits'%d for d in labels])
        if psf: 
            argo.combine_fits(psfs,outname=II('$image_prefix.psf.fits'),ctype='FREQ',keep_old=keep_component_images)
        elif restore:
            for fits in psfs:
                rm_fr(fits)

        for i in pol:
            if len(pol) == 1:
               i = ''

            if i : 
                i = '-%s'%i
         
            dirtys = eval_list(['$image_prefix-%s$i-dirty.fits'%d for d in labels])
            if dirty:
                argo.combine_fits(dirtys,
                       outname=II('$image_prefix$i-dirty.fits') if i else dirty_image,
                       ctype='FREQ',keep_old=keep_component_images)
                if not restore:
                    xo.sh('rm -fr ${image_prefix}*image*.fits')
            else: 
                for fits in dirtys:
                    rm_fr(fits)

            if restore:
                model = eval_list(['$image_prefix-%s$i-model.fits'%d for d in labels])
                argo.combine_fits(model,outname=II('$image_prefix$i-model.fits') if i else model_image,
                       ctype='FREQ',keep_old=keep_component_images)

                residual = eval_list(['$image_prefix-%s$i-residual.fits'%d for d in labels])
                argo.combine_fits(residual,outname=II('$image_prefix$i-residual.fits') if i else residual_image,
                       ctype='FREQ',keep_old=keep_component_images)

                restored = eval_list(['$image_prefix-%s$i-image.fits'%d for d in labels])
                argo.combine_fits(restored,outname=II('$image_prefix$i-image.fits') if i else restored_image ,
                       ctype='FREQ',keep_old=keep_component_images)
                if len(pol)==1:
                    for old,new in zip([image_prefix+'-MFS-%s.fits'%img for img in 'model residual image'.split()],
                                       [model_image.replace('.model.fits','-MFS.model.fits'),
                                        residual_image.replace('.residual.fits','-MFS.residual.fits'),
                                        restored_image.replace('.restored.fits','-MFS.restored.fits')]):
                        #TODO(sphe) Should we always keep wsclean MFS images?
                        #if mfs:
                        x.mv('$old $new')
                        #else: 
                        #    rm_fr(old)

        if len(pol)>1:
            combine_pol(pol,image_prefix,mfs=True)

    if do_moresane:
        info(" im.moresane.deconv: making estored image $restored_image \
              model is $model_image, residual is $residual_image)")
        moresane.deconv(dirty_image,psf_image,model_image=model_image,
                           residual_image=residual_image,
                           restored_image=restored_image,**kw0)

    if restore or do_moresane:
        if lsm and restore_lsm:
            info("Restoring LSM into FULLREST_IMAGE=$fullrest_image");
            opts = restore_lsm if isinstance(restore_lsm,dict) else {};
            tigger_restore(restoring_options,"-f",
                           restored_image,lsm,
                           fullrest_image,
                           kwopt_to_command_line(**opts));
    
    im.IMAGER = _imager

document_globals(make_image,"im.*_IMAGE COLUMN im.IMAGE_CHANNELIZE MS im.RESTORING_OPTIONS im.CLEAN_ALGORITHM ms.IFRS ms.DDID ms.FIELD ms.CHANRANGE")
