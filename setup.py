#!/usr/bin/env python

import os
from distutils.core import setup

setup(name='pyxis',
      version='1.3.0',
      description='Python Extensions for Interferometry Scripting',
      author='Oleg Smirnov',
      author_email='Oleg Smirnov <osmirnov@gmail.com>',
      url='https://github.com/ska-sa/pyxis',
      packages=['Pyxis', 'Pyxides'],
      requires=['pyfits', 'timba', 'matplotlib', 'pyrap', 'numpy'],
      scripts=['Pyxis/bin/' + i for i in os.listdir('Pyxis/bin')],
     )
