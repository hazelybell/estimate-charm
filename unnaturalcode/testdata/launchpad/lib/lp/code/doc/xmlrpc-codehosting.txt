The BranchPuller application
============================

The codehosting application is an XMLRPC service that allows the
codehosting service and puller to find and update the status of
branches.  It is available as the codehosting attribute of our private
XMLRPC instance.

    >>> from lp.xmlrpc.interfaces import IPrivateApplication
    >>> from lp.code.interfaces.codehosting import (
    ...     ICodehostingApplication)
    >>> from lp.testing import verifyObject

    >>> private_root = getUtility(IPrivateApplication)
    >>> verifyObject(
    ...     ICodehostingApplication,
    ...     private_root.codehosting)
    True

The CodehostingAPI view provides the ICodehostingAPI XML-RPC API:

    >>> from lp.services.webapp.servers import LaunchpadTestRequest
    >>> from lp.code.interfaces.codehosting import ICodehostingAPI
    >>> from lp.code.xmlrpc.codehosting import CodehostingAPI

    >>> codehosting_api = CodehostingAPI(
    ...     private_root.codehosting, LaunchpadTestRequest())
    >>> verifyObject(ICodehostingAPI, codehosting_api)
    True

The ICodehostingAPI interface defines some methods, for which see the
unit tests.
