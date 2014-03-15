# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# This file is imported by parts/scripts/sitecustomize.py, as set up in our
# buildout.cfg (see the "initialization" key in the "[scripts]" section).

from collections import defaultdict
import itertools
import logging
import os
import warnings

from twisted.internet.defer import (
    Deferred,
    DeferredList,
    )
from zope.interface import alsoProvides
import zope.publisher.browser
from zope.security import checker

from lp.services.log import loglevels
from lp.services.log.logger import LaunchpadLogger
from lp.services.log.mappingfilter import MappingFilter
from lp.services.log.nullhandler import NullHandler
from lp.services.mime import customizeMimetypes
from lp.services.webapp.interfaces import IUnloggedException


def add_custom_loglevels():
    """Add out custom log levels to the Python logging package."""

    # This import installs custom ZODB loglevels, which we can then
    # override. BLATHER is between INFO and DEBUG, so we can leave it.
    # TRACE conflicts with DEBUG6, and since we are not using ZEO, we
    # just overwrite the level string by calling addLevelName.
    from ZODB.loglevels import BLATHER, TRACE

    # Confirm our above assumptions, and silence lint at the same time.
    assert BLATHER == 15
    assert TRACE == loglevels.DEBUG6

    logging.addLevelName(loglevels.DEBUG2, 'DEBUG2')
    logging.addLevelName(loglevels.DEBUG3, 'DEBUG3')
    logging.addLevelName(loglevels.DEBUG4, 'DEBUG4')
    logging.addLevelName(loglevels.DEBUG5, 'DEBUG5')
    logging.addLevelName(loglevels.DEBUG6, 'DEBUG6')
    logging.addLevelName(loglevels.DEBUG7, 'DEBUG7')
    logging.addLevelName(loglevels.DEBUG8, 'DEBUG8')
    logging.addLevelName(loglevels.DEBUG9, 'DEBUG9')

    # Install our customized Logger that provides easy access to our
    # custom loglevels.
    logging.setLoggerClass(LaunchpadLogger)

    # Fix the root logger, replacing it with an instance of our
    # customized Logger. The original one is instantiated on import of
    # the logging module, so our override does not take effect without
    # this manual effort.
    old_root = logging.root
    new_root = LaunchpadLogger('root', loglevels.WARNING)

    # Fix globals.
    logging.root = new_root
    logging.Logger.root = new_root

    # Fix manager.
    manager = logging.Logger.manager
    manager.root = new_root

    # Fix existing Logger instances.
    for logger in manager.loggerDict.values():
        if getattr(logger, 'parent', None) is old_root:
            logger.parent = new_root


def silence_amqplib_logger():
    """Install the NullHandler on the amqplib logger to silence logs."""
    amqplib_logger = logging.getLogger('amqplib')
    amqplib_logger.addHandler(NullHandler())
    amqplib_logger.propagate = False


def silence_bzr_logger():
    """Install the NullHandler on the bzr logger to silence logs."""
    bzr_logger = logging.getLogger('bzr')
    bzr_logger.addHandler(NullHandler())
    bzr_logger.propagate = False


def silence_zcml_logger():
    """Lower level of ZCML parsing DEBUG messages."""
    config_filter = MappingFilter(
        {logging.DEBUG: (7, 'DEBUG4')}, 'config')
    logging.getLogger('config').addFilter(config_filter)


def silence_transaction_logger():
    """Lower level of DEBUG messages from the transaction module."""
    # Transaction logging is too noisy. Lower its DEBUG messages
    # to DEBUG3. Transactions log to loggers named txn.<thread_id>,
    # so we need to register a null handler with a filter to ensure
    # the logging records get mutated before being propagated up
    # to higher level loggers.
    txn_handler = NullHandler()
    txn_filter = MappingFilter(
        {logging.DEBUG: (8, 'DEBUG3')}, 'txn')
    txn_handler.addFilter(txn_filter)
    logging.getLogger('txn').addHandler(txn_handler)


def dont_wrap_class_and_subclasses(cls):
    checker.BasicTypes.update({cls: checker.NoProxy})
    for subcls in cls.__subclasses__():
        dont_wrap_class_and_subclasses(subcls)


def dont_wrap_bzr_branch_classes():
    from bzrlib.branch import Branch
    # Load bzr plugins
    import lp.codehosting
    lp.codehosting
    # Force LoomBranch classes to be listed as subclasses of Branch
    import bzrlib.plugins.loom.branch
    bzrlib.plugins.loom.branch
    dont_wrap_class_and_subclasses(Branch)


def silence_warnings():
    """Silence warnings across the entire Launchpad project."""
    # pycrypto-2.0.1 on Python2.6:
    #   DeprecationWarning: the sha module is deprecated; use the hashlib
    #   module instead
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        module="Crypto")
    # Filter all deprecation warnings for Zope 3.6, which emanate from
    # the zope package.
    filter_pattern = '.*(Zope 3.6|provide.*global site manager).*'
    warnings.filterwarnings(
        'ignore', filter_pattern, category=DeprecationWarning)


def customize_logger():
    """Customize the logging system.

    This function is also invoked by the test infrastructure to reset
    logging between tests.
    """
    silence_amqplib_logger()
    silence_bzr_logger()
    silence_zcml_logger()
    silence_transaction_logger()


def customize_get_converter(zope_publisher_browser=zope.publisher.browser):
    """URL parameter conversion errors shouldn't generate an OOPS report.

    This injects (monkey patches) our wrapper around get_converter so improper
    use of parameter type converters (like http://...?foo=bar:int) won't
    generate OOPS reports.
    """
    original_get_converter = zope_publisher_browser.get_converter

    def get_converter(*args, **kws):
        """Get a type converter but turn off OOPS reporting if it fails."""
        converter = original_get_converter(*args, **kws)

        def wrapped_converter(v):
            try:
                return converter(v)
            except ValueError as e:
                # Mark the exception as not being OOPS-worthy.
                alsoProvides(e, IUnloggedException)
                raise

        # The converter can be None, in which case wrapping it makes no sense,
        # otherwise it is a function which we wrap.
        if converter is None:
            return None
        else:
            return wrapped_converter

    zope_publisher_browser.get_converter = get_converter


def main(instance_name):
    # This is called by our custom buildout-generated sitecustomize.py
    # in parts/scripts/sitecustomize.py. The instance name is sent to
    # buildout from the Makefile, and then inserted into
    # sitecustomize.py.  See buildout.cfg in the "initialization" value
    # of the [scripts] section for the code that goes into this custom
    # sitecustomize.py.  We do all actual initialization here, in a more
    # visible place.
    if instance_name and instance_name != 'development':
        # See bug 656213 for why we do this carefully.
        os.environ.setdefault('LPCONFIG', instance_name)
    os.environ['STORM_CEXTENSIONS'] = '1'
    add_custom_loglevels()
    customizeMimetypes()
    silence_warnings()
    customize_logger()
    dont_wrap_bzr_branch_classes()
    checker.BasicTypes.update({defaultdict: checker.NoProxy})
    checker.BasicTypes.update({Deferred: checker.NoProxy})
    checker.BasicTypes.update({DeferredList: checker.NoProxy})
    checker.BasicTypes[itertools.groupby] = checker._iteratorChecker
    # The itertools._grouper type is not exposed by name, so we must get it
    # through actually using itertools.groupby.
    grouper = type(list(itertools.groupby([0]))[0][1])
    checker.BasicTypes[grouper] = checker._iteratorChecker
    customize_get_converter()
