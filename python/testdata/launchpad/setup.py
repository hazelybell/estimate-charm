#!/usr/bin/env python
#
# Copyright 2009, 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import ez_setup


ez_setup.use_setuptools()

from setuptools import setup, find_packages

__version__ = '2.2.3'

setup(
    name='lp',
    version=__version__,
    packages=find_packages('lib'),
    package_dir={'': 'lib'},
    include_package_data=True,
    zip_safe=False,
    maintainer='Launchpad Developers',
    description=('A unique collaboration and Bazaar code hosting platform '
                 'for software projects.'),
    license='Affero GPL v3',
    # this list should only contain direct dependencies--things imported or
    # used in zcml.
    install_requires=[
        'ampoule',
        'auditorclient',
        'auditorfixture',
        'BeautifulSoup',
        'bzr',
        'cssutils',
        # Required for pydkim
        'dnspython',
        'fixtures',
        'FeedParser',
        'feedvalidator',
        'funkload',
        'html5browser',
        'pygpgme',
        'python-debian',
        'python-keystoneclient',
        'python-subunit',
        'python-swiftclient',
        'launchpadlib',
        'lazr.batchnavigator',
        'lazr.config',
        'lazr.delegates',
        'lazr.enum',
        'lazr.lifecycle',
        'lazr.restful',
        'lazr.jobrunner',
        'lazr.smtptest',
        'lazr.testing',
        'lazr.uri',
        'lpjsmin',
        'Markdown',
        'mechanize',
        'meliae',
        'oauth',
        'oops',
        'oops_amqp',
        'oops_datedir_repo',
        'oops_timeline',
        'oops_twisted',
        'oops_wsgi',
        'paramiko',
        'pgbouncer',
        'psycopg2',
        'python-memcached',
        'pyasn1',
        'pydkim',
        'pystache',
        'python-openid',
        'pytz',
        'rabbitfixture',
        's4',
        'setproctitle',
        'setuptools',
        'Sphinx',
        'soupmatchers',
        'sourcecodegen',
        'storm',
        'subvertpy',
        'testtools',
        'timeline',
        'transaction',
        'Twisted',
        'txfixtures',
        'txlongpollfixture',
        'wadllib',
        'z3c.pt',
        'z3c.ptcompat',
        'zc.zservertracelog',
        'zope.app.appsetup',
        'zope.app.http',
        'zope.app.publication',
        'zope.app.publisher',
        'zope.app.server',
        'zope.app.testing',
        'zope.app.wsgi',
        'zope.authentication',
        'zope.contenttype',
        'zope.component[zcml]',
        'zope.datetime',
        'zope.error',
        'zope.event',
        'zope.exceptions',
        'zope.formlib',
        'zope.i18n',
        'zope.interface',
        'zope.lifecycleevent',
        'zope.location',
        'zope.login',
        'zope.pagetemplate',
        'zope.principalregistry',
        'zope.publisher',
        'zope.proxy',
        'zope.schema',
        'zope.security',
        'zope.securitypolicy',
        'zope.sendmail',
        'zope.server',
        'zope.session',
        'zope.tal',
        'zope.tales',
        'zope.testbrowser',
        'zope.testing',
        'zope.traversing',
        'zope.viewlet',  # only fixing a broken dependency
        'zope.vocabularyregistry',
        # Loggerhead dependencies. These should be removed once
        # bug 383360 is fixed and we include it as a source dist.
        'Paste',
        'PasteDeploy',
        'SimpleTAL',
    ],
    url='https://launchpad.net/',
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
    ],
    extras_require=dict(
        docs=[
            'Sphinx',
            'z3c.recipe.sphinxdoc',
        ]
    ),
    entry_points=dict(
        console_scripts=[  # `console_scripts` is a magic name to setuptools
            'apiindex = lp.scripts.utilities.apiindex:main',
            'killservice = lp.scripts.utilities.killservice:main',
            'jsbuild = lp.scripts.utilities.js.jsbuild:main',
            'run = lp.scripts.runlaunchpad:start_launchpad',
            'run-testapp = '
                'lp.scripts.runlaunchpad:start_testapp',
            'harness = lp.scripts.harness:python',
            'twistd = twisted.scripts.twistd:run',
            'start_librarian = '
                'lp.scripts.runlaunchpad:start_librarian',
        ]
    ),
)
