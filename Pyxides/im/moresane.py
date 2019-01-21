"""Pyxis module for MS-related operations""";
from Pyxis.ModSupport import *

import os
import sys
import numpy
import math
import argo
import im
# Standard options
gain = 0.1
sigmalevel = 3.0

define('MORESANE_PATH_Template','${im.MORESANE_PATH}','Path to PyMORESANE')

_moresane_args = {'outputname': None,
                  'modelname': None,
                  'residualname': None,
                  'restoredname':None,
                  'singlerun': False,
                  'subregion': None,
                  'scalecount': None,
                  'startscale': 1,
                  'stopscale': 20,
                  'sigmalevel': 4,
                  'loopgain': 0.2,
                  'tolerance': 0.75,
                  'accuracy': 1e-6,
                  'majorloopmiter': 100,
                  'minorloopmiter': 50,
                  'allongpu': False,
                  'decommode': 'ser',
                  'corecount': 1,
                  'convdevice': 'cpu',
                  'convmode': 'circular',
                  'extractionmode': 'cpu',
                  'enforcepositivity': False,
                  'edgesupression': False,
                  'edgeoffset': 0,
                  'mfs':False,
                  'mfs-chanrange':None,
                  'spi-sigmalevel':10,
                  'spec-curv':False,
                  'fluxthreshold': 0,
                  'mask': None
}

def deconv(dirty_image,psf_image,
                 model_image='${im.MODEL_IMAGE}',
                 residual_image='${im.RESIDUAL_IMAGE}',
                 restored_image='${im.RESTORED_IMAGE}',
                 image_prefix='${im.BASENAME_IMAGE}',
                 path='$MORESANE_PATH',**kw):
    """ Runs PyMORESANE """

    # Check if PyMORESANE is where it is said to be
    model_image,residual_image,restored_image,path = interpolate_locals('model_image residual_image restored_image path')
    found_path = argo.findImager(path,imager_name='PyMORESANE') 
    if not found_path:
        abort('could not find PyMORESANE at $path')
   
    kw['modelname'] = model_image
    kw['residualname'] = residual_image
    kw['restoredname'] = restored_image
    
    # make dict of imager arguments that have been specified globally or locally
    args = dict([ (arg,globals()[arg]) for arg in _moresane_args if arg in globals() and globals()[arg] is not None ]);
    args.update([ (arg,kw[arg]) for arg in _moresane_args if arg in kw ])

    x.sh(argo.gen_run_cmd(path,args,suf='--',assign='=',pos_args=[dirty_image,psf_image,image_prefix]))

document_globals(deconv,'im*_IMAGE MORESANE_PATH im.MORESANE_PATH')
