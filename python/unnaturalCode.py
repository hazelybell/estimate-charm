#    Copyright 2013 Joshua Charles Campbell
#
#    This file is part of UnnaturalCode.
#    
#    UnnaturalCode is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    UnnaturalCode is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with UnnaturalCode.  If not, see <http://www.gnu.org/licenses/>.
from ucUtil import *
import os, zmq
import logging
from logging import debug, info, warning, error

zctx = None

@singleton
class unnaturalCode(object):
    """Singleton class for UC."""
    
    def __init__(self, logFilePath=None, logLevel=None):
        """Initialize global context."""
        self.logFilePath = (logFilePath or os.getenv("ucLogFile", "/tmp/ucLog-%i" % os.getpid()))
        self.logLevel = (logLevel or os.getenv("ucLogLevel", "DEBUG").upper())
        # from http://docs.python.org/2/howto/logging.html#logging-basic-tutorial 2013-10-04
        # LICENSE: PSF
        numeric_level = getattr(logging, self.logLevel.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: %s' % loglevel)
        # end from
        if not logging.getLogger():
            logging.basicConfig(filename=self.logFilePath, level=numeric_level)
        debug("UC Init")
        global zctx
        if not zctx:
            self.zctx = zmq.Context()
            zctx = self.zctx
        self.forceTrain = toBool(os.getenv("ucForceTrain", "false"))
        self.forceValidate = toBool(os.getenv("ucValidate", "false"))

# rwfubmqqoiigevcdefhmidzavjwg
