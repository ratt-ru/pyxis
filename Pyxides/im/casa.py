#Pyxis casa wrap
from Pyxis.ModSupport import *
import ms
import im
import subprocess
import tempfile
import  argo
import pyrap.images as Images

# register ourselves with Pyxis and define the superglobals
register_pyxis_module(superglobals="MS LSM OUTDIR DESTDIR")

rm_fr = x.rm.args("-fr")
tigger_restore = x("tigger-restore")

define('CASA_PATH','${im.CASA_PATH}','Casa Path')
define('IMAGER','casa','Imager name')

v.define("LSM","lsm.lsm.html","""current local sky model""")

_casa_known_args = {4.10:set('vis imagename outlierfile field spw selectdata timerange uvrange antenna '
                              'scan observation mode nterms reffreq gridmode wprojplanes cfcache '
                              'painc niter gain threshold psfmode imagermode cyclefactor cyclespeedup '
                              'multiscale negcomponent smallscalebias interactive mask imsize cell '
                              'phasecenter restfreq stokes weighting robust npixels uvtaper outertaper '
                              'innertaper modelimage restoringbeam pbcor minpb usescratch allowchunk '
                              'async nchan start width interpolation chaniter outframe'.split()),
                    4.20:set(),
                    4.22:set('calready fitmachine mosweight noise scaletype veltype'.split()),
}

def STANDARD_IMAGING_OPTS_Template():
    global npix,cellsize,mode,stokes,weight,robust,niter,gain,threshold
    global wprojplanes,cachesize,ifrs,fixed,flux_rescale,velocity,no_weight_fov
    npix = im.npix
    cellsize = im.cellsize
    mode = im.mode
    stokes = im.stokes
    weight = im.weight
    robust = im.robust
    niter = im.niter
    gain = im.gain
    threshold = im.threshold
    wprojplanes = im.wprojplanes
    cachesize = im.cachesize
    ifrs = im.ifrs
    fixed = im.fixed
    # rescale images by factor
    flux_rescale= im.flux_rescale
    # use velocity rather than frequency
    velocity = im.velocity
    no_weight_fov = im.no_weight_fov


# whenever the path changes, find out new version number, and build new set of arguments
_casa_path_version = None,None;
def CASA_VERSION_Template (path='$CASA_PATH'):
    path = interpolate_locals('path')
    path = im.argo.findImager(path)
    if not path:
        return -1
    global _casa_path_version,_casa_args
    if path != _casa_path_version[0]:
        _casa_path_version = path,casa_version(path)
        _casa_args = set()
        for version,args in _casa_known_args.items():
            if version <= _casa_path_version[1][0]:
                _casa_args.update(args)
    return _casa_path_version[1]


def casa_version(path='$CASA_PATH'):
    """ try to find casa version """

    path = interpolate_locals('path')
    std = subprocess.Popen([path,'--help','--log2term','--nologger','--nogui','--help','-c','quit'],
                            stderr=subprocess.PIPE,stdout=subprocess.PIPE)
    if std.stderr.read():
        version = '4.10' # start support from casa 4.10
        tail = ""
    else:
        stdout = std.stdout.read().lower()
        version = stdout.split()
        ind = version.index('version')
        version = version[ind+1].split('-')[0]
        tail = version.split('-')[-1] if '-' in version else ""

    info('$path version is $version${-<tail}')

    if '.' in version:
        try:
            version = list(map(int,version.split('.')))
        except ValueError: 
            version = 4,1,0
        vstr = '%d.' + '%d'*(len(version)-1)
        version = float(vstr%(tuple(version)))
    return version,tail


def _run(path='${im.CASA_PATH}',clean=False,makepsf=False,**kw):
    """ runs casa's clean task """
    
    path = interpolate_locals('path')
    # map some options to casapy equivalents
    global cell,imsize,weighting,_casa_args
    cell,imsize,weighting = cellsize,npix,weight

    # make dict of imager arguments that have been specified globally or locally
    args = dict([ (arg,globals()[arg]) for arg in _casa_args if arg in globals() and globals()[arg] is not None ]);
    args.update([ (arg,kw[arg]) for arg in _casa_args if arg in kw ])
    # add ifrs, spwid and field arguments
    ms.IFRS is not None and args.setdefault('ifrs',ms.IFRS)
    ms.DDID is not None and args.setdefault('spw',ms.DDID)
    ms.FIELD is not None and args.setdefault('field',ms.FIELD)
    
    if args.get("wprojplanes",0):
        args["gridmode"] = "widefield"
    

    # have an IFR subset? Parse that too
    msname,ifrs = args['vis'],args.pop('ifrs',None)
    if ifrs and ifrs.lower() != "all":
        import Meow.IfrSet
        subset = Meow.IfrSet.from_ms(msname).subset(ifrs).taql_string()
        args['selectdata'] = "(%s)&&(%s)"%(args['selectdata'],subset) if 'selectdata' in args else subset
    
    # casapy likes these options as strings 
    for item in 'field spw'.split():
        if not isinstance(args[item],str):
            args[item] = str(args[item])

    im.argo.icasa('clean',**args)
    imagename = kw['imagename']
    # convert casa images to fits files.
    mult = []
    if clean:
        model = kw['model']
        residual = kw['residual']
        restored = kw['restored']
        for img,fitsim in zip('model residual image'.split(),[model,residual,restored]):
            mult.append({'imagename':'%s.%s'%(imagename,img),'fitsimage':fitsim})
    else:
        mult.append({'imagename':'%s.%s'%(imagename,'image'),'fitsimage':kw['dirty']})
    if makepsf: 
        mult.append({'imagename':'%s.%s'%(imagename,'psf'),'fitsimage':kw['psf']})
    if mult:
        velo = kw.get("velocity") or velocity
        fs = kw.get("flux_rescale") or flux_rescale
        for pair in mult:
            casaim, fitsim = pair["imagename"],pair["fitsimage"]
            _im = Images.image(casaim)
            if fs!=1:
                _im.putdata(fs*_im.getdata())
            if os.path.exists(casaim):
                _im.tofits(fitsim, overwrite=True, velocity=velo)
            else:
                abort("Cannot find images. Something went wrong when running CASAPY clean task. Please check logs")
        

#        im.argo.icasa('exportfits',mult=mult,overwrite=True)
    # delete casa images
    for image in ['$imagename.%s'%s for s in 'model residual image flux psf'.split()]:
        if os.path.exists(II(image)):
            rm_fr(image)


def make_image (msname="$MS",column="${im.COLUMN}",imager='$IMAGER',
                dirty=True,restore=False,restore_lsm=True,psf=False,
                dirty_image="${im.DIRTY_IMAGE}",
                model_image="${im.MODEL_IMAGE}",
                restored_image="${im.RESTORED_IMAGE}",
                residual_image="${im.RESIDUAL_IMAGE}",
                psf_image="${im.PSF_IMAGE}",
                algorithm="${im.CLEAN_ALGORITHM}",
                fullrest_image="${im.FULLREST_IMAGE}",
                restoring_options="${im.RESTORING_OPTIONS}",
                channelize=None,lsm="$LSM",**kw0):
    """ run casa imager """

    _imager = im.IMAGER
    im.IMAGER = II(imager)
    #Add algorithm label if required
    if im.DECONV_LABEL and restore: 
        if isinstance(im.DECONV_LABEL,bool):
            if im.DECONV_LABEL:
                im.DECONV_LABEL = algorithm
    elif im.DECONV_LABEL is False:
        im.DECONV_LABEL = None
     
    do_moresane=False
    if algorithm.lower() in ['moresane','pymoresane']: 
        do_moresane = True
        from im import moresane
    imager,msname,column,lsm,dirty_image,psf_image,restored_image,residual_image,\
model_image,algorithm,fullrest_image,restoring_options = \
interpolate_locals("imager msname column lsm dirty_image psf_image restored_image "
                   "residual_image model_image algorithm fullrest_image restoring_options")

    makedir('$DESTDIR')

    if restore and column != "CORRECTED_DATA":
        abort("Due to imager limitations, restored images can only be made from the CORRECTED_DATA column.")

    # setup imager options
    kw0.update(dict(chanstart=ms.CHANSTART,chanstep=ms.CHANSTEP,nchan=ms.NUMCHANS));
    if 'nchan' not in kw0 or 'start' not in kw0:
        if channelize is None:
            channelize = im.IMAGE_CHANNELIZE;
        if channelize == 0:
            kw0.update(nchan=1,width=ms.NUMCHANS);
        elif channelize > 0:
            kw0.update(nchan=ms.NUMCHANS//channelize,start=ms.CHANSTART,width=channelize);

    kw0.update(vis=msname,imagename=im.BASENAME_IMAGE)
    def make_dirty():
        info("im.casa.make_image: making dirty image $dirty_image")
        kw = kw0.copy()
        kw['niter'] = 0
        _run(dirty=dirty_image,makepsf=psf,psf=psf_image,**kw)
    if dirty:
        make_dirty()

    if do_moresane and restore:
        if np.logical_or(not dirty,not psf): 
            psf = True
            make_dirty()

        opts = restore if isinstance(restore,dict) else {}
        info(" making restored image $restored_image\
                    (model is $model_image, residual is $residual_image)")

        moresane.deconv(dirty_image,psf_image,model_image=model_image,
                           residual_image=residual_image,restored_image=restored_image,**opts)
    elif restore:
        info(" making restored image $restored_image\
              (model is $model_image, residual is $residual_image)")
        kw = kw0.copy()
        kw['psfmode'] = algorithm if algorithm in 'clark clarkstokes hogbom' else 'clark'
        if isinstance(restore,dict):
            kw.update(restore)
        _run(model=model_image,residual=residual_image,restored=restored_image,makepsf=psf,psf=psf_image,clean=True,**kw)

    if restore:
        if lsm and restore_lsm:
            info("Restoring LSM into FULLREST_IMAGE=$fullrest_image")
            opts = restore_lsm if isinstance(restore_lsm,dict) else {}
            tigger_restore(restoring_options,"-f",restored_image,lsm,fullrest_image,kwopt_to_command_line(**opts))

    im.IMAGER = _imager

document_globals(make_image,"im.*_IMAGE COLUMN im.IMAGE_CHANNELIZE MS im.RESTORING_OPTIONS im.CLEAN_ALGORITHM ms.IFRS ms.DDID ms.FIELD ms.CHANRANGE")
