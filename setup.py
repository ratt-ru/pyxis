#!/usr/bin/env python

import os
from distutils.core import setup

install_requires = [
      'astropy',
      # 'timba', not available on pypi
      'matplotlib',
      'python_casacore',
      'numpy',
      'future',
      'six',
]

setup(name='astro-pyxis',
      version='1.6.1',
      description='Python Extensions for astronomical Interferometry Scripting',
      author='Oleg Smirnov',
      author_email='Oleg Smirnov <osmirnov@gmail.com>',
      url='https://github.com/ska-sa/pyxis',
      packages=['Pyxis', 'Pyxides', 'Pyxides._utils', 'Pyxides.im'],
      install_requires=install_requires,
      scripts=['Pyxis/bin/' + i for i in os.listdir('Pyxis/bin')],
     )
