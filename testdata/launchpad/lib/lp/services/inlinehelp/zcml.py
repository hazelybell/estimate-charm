# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ZCML directive for help folder registrations."""

__metaclass__ = type
__all__ = []

from zope.component.zcml import handler
from zope.configuration.fields import Path
from zope.interface import Interface
from zope.publisher.interfaces.browser import (
    IBrowserPublisher,
    IBrowserRequest,
    )
from zope.schema import TextLine
from zope.security.checker import (
    defineChecker,
    NamesChecker,
    )

from lp.services.inlinehelp.browser import HelpFolder
from lp.services.webapp.interfaces import ILaunchpadApplication


class IHelpFolderDirective(Interface):
    """Directive to register an help folder."""
    folder = Path(
        title=u'The path to the help folder.',
        required=True)
    name = TextLine(
        title=u'The name to register the help folder under.',
        required=True)


def register_help_folder(context, folder, name):
    """Create a help folder subclass and register it with the ZCA."""

    help_folder = type(
        str('%s for %s' % (name, folder)), (HelpFolder, ),
        {'folder': folder, '__name__': name})

    defineChecker(
        help_folder,
        NamesChecker(list(IBrowserPublisher.names(True)) + ['__call__']))

    context.action(
        discriminator=(
            'view', (ILaunchpadApplication, IBrowserRequest), name),
        callable=handler,
        args=('registerAdapter',
              help_folder, (ILaunchpadApplication, IBrowserRequest),
              Interface, name, context.info),
        )
