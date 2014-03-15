Inline Help System
==================

The inline help system offers a base implementation for help folder called
HelpFolder. They make it easy for components to register directories
containing inline help documentation.

These are lazr.folder.ExportedFolder that automatically export
their subdirectories.

    >>> from lp.app.browser.folder import ExportedFolder
    >>> from lp.services.inlinehelp.browser import HelpFolder

    >>> issubclass(HelpFolder, ExportedFolder)
    True
    >>> HelpFolder.export_subdirectories
    True

ZCML Registration
-----------------

HelpFolder can be easily registered using a ZCML directive. The directive
takes the directory served by the HelpFolder and the request type for which
it should be registered.

    >>> import tempfile
    >>> help_folder = tempfile.mkdtemp(prefix='help')

    >>> from zope.configuration import xmlconfig
    >>> zcmlcontext = xmlconfig.string("""
    ... <configure xmlns:lp="http://namespaces.canonical.com/lp">
    ...   <include package="lp.services.inlinehelp" file="meta.zcml" />
    ...   <lp:help-folder folder="%s" name="+help"/>
    ... </configure>
    ... """ % help_folder)

The help folder is registered on the ILaunchpadRoot interface.

    >>> from zope.interface import directlyProvides
    >>> from zope.publisher.interfaces.browser import IBrowserRequest
    >>> class FakeRequest:
    ...     pass
    >>> request = FakeRequest()
    >>> directlyProvides(request, IBrowserRequest)

    >>> from zope.component import queryMultiAdapter
    >>> from lp.services.webapp.publisher import rootObject
    >>> help_view = queryMultiAdapter((rootObject, request), name="+help")

    >>> help_view.folder == help_folder
    True

    >>> isinstance(help_view, HelpFolder)
    True

    >>> print help_view.__name__
    +help

    >>> print help_view.__class__.__name__
    +help for /tmp/help...


Cleanup
-------

    >>> from zope.testing.cleanup import cleanUp
    >>> cleanUp()

    >>> import shutil
    >>> shutil.rmtree(help_folder)
