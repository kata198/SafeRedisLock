#!/usr/bin/env python
#
# Copyright (c) 2016 Timothy Savannah under terms of LGPLv3. You should have received a copy of this with this distribution as "LICENSE"


#vim: set ts=4 sw=4 expandtab

import os
import sys
from setuptools import setup


if __name__ == '__main__':
 

    dirName = os.path.dirname(__file__)
    if dirName and os.getcwd() != dirName:
        os.chdir(dirName)

    summary = 'A safe and fast queue-based lock implementation for Redis, with support for global timeouts'

    try:
        with open('README.rst', 'rt') as f:
            long_description = f.read()
    except Exception as e:
        sys.stderr.write('Exception when reading long description: %s\n' %(str(e),))
        long_description = summary

    setup(name='SafeRedisLock',
            version='1.0.0',
            packages=['SafeRedisLock'],
            author='Tim Savannah',
            author_email='kata198@gmail.com',
            maintainer='Tim Savannah',
            url='https://github.com/kata198/SafeRedisLock',
            maintainer_email='kata198@gmail.com',
            description=summary,
            long_description=long_description,
            license='LGPLv3',
            requires=['redis'],
            install_requires=['redis'],
            keywords=['lock', 'redis', 'safe', 'timeout', 'acquire', 'release', 'hasLock', 'SafeRedisLock', 'semaphore', 'exclusive', 'shared', 'server', 'network'],
            classifiers=['Development Status :: 4 - Beta',
                         'Programming Language :: Python',
                         'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',
                         'Programming Language :: Python :: 2',
                          'Programming Language :: Python :: 2',
                          'Programming Language :: Python :: 2.6',
                          'Programming Language :: Python :: 2.7',
                          'Programming Language :: Python :: 3',
                          'Programming Language :: Python :: 3.3',
                          'Programming Language :: Python :: 3.4',
                          'Programming Language :: Python :: 3.5',
                          'Topic :: System :: Networking',
                          'Topic :: Software Development :: Libraries',
                          'Topic :: Software Development :: Libraries :: Python Modules',
            ]
    )


