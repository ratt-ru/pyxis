#!/usr/bin/env python

import os
from distutils.core import setup
import six

install_requires = [
      'astropy<=2.0.11',
      # 'timba', not available on pypi
      'matplotlib',
      'python_casacore',
      'numpy<=1.16',
      'scipy',
      'future'
] if six.PY2 else [
      'astropy>=3.0',
      # 'timba', not available on pypi
      'matplotlib',
      'python_casacore',
      'numpy>=1.16',
      'scipy',
      'future'
]

def readme():
    """ Return README.rst contents """
    with open('README.md') as f:
      return f.read()

setup(name='astro-pyxis',
      version='1.7.4.1',
      python_requires='>=3.0.0',
      description='Python Extensions for astronomical Interferometry Scripting',
      author='Oleg Smirnov',
      author_email='Oleg Smirnov <osmirnov@gmail.com>',
      url='https://github.com/ska-sa/pyxis',
      packages=['Pyxis', 'Pyxides', 'Pyxides.im', 'Pyxides.utils'],
      install_requires=install_requires,
      zip_safe=True,
      include_package_data=True,
      scripts=['Pyxis/bin/' + i for i in os.listdir('Pyxis/bin')],
     )
