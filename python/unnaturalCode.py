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
from copy import copy

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
        
class ucPos(tuple):
    def __new__(cls, *args):
        if len(args) == 2:
            l = args[0]
            c = args[1]
        elif isinstance(args[0], ucPos):
            return args[0]
        elif isinstance(args[0], tuple):
            (l, c) = args[0]
        else:
          raise TypeError("Bad constructor arguments.")
        assert isinstance(l, int)
        assert isinstance(c, int)
        assert l >= 1
        assert c >= 0
        return tuple.__new__(cls, (l, c))
    
    def __getattr__(self, name):
        if name[0] == 'l':
          return self[0]
        elif name[0] == 'c':
          return self[1]
        raise AttributeError
    
    def __str__(self):
        return str(self[0]) + ":" + str(self[1])
    
    def __eq__(self, other):
        return (self[0] == other[0]) and (self[1] == other[1])
    
    def __ne__(self, other):
      return not self.__eq__(other)
    
    def __gt__(self, other):
        return (self[0] > other[0]) or ((self[0] == other[0]) and (self[1] > other[1]))
      
    def __lt__(self, other):
        return not self.__gt__(other)
    
    def __ge__(self, other):
        return self.__gt__(other) or self.__eq__(other)
      
    def __le__(self, other):
        return self.__lt__(other) or self.__eq__(other)
      
class ucLexeme(tuple):
    def __new__(cls, *args):
        """Initialize a lexeme object."""
        if isinstance(args[0], cls):
            return args[0]
        elif isinstance(args[0], tuple):
            t = (args[0][0], args[0][1], ucPos(args[0][2]), ucPos(args[0][3]))
        elif isinstance(args[0], dict):
            t = (args[0]['type'], args[0]['value'],  ucPos(args[0]['start']),  ucPos(args[0]['end']))
        elif len(args) == 4:
            t = (args[0], args[1], ucPos(args[2]), ucPos(args[3]))
        else:
            raise TypeError("Constructor arguments")
        assert t[0]
        assert isinstance(t[0], str)
        assert isinstance(t[1], str)
        assert isinstance(t[2], ucPos)
        assert isinstance(t[3], ucPos)
        assert t[2] <= t[3], "%s > %s" % (start, end)
        return tuple.__new__(cls, t)
    
    def __getitem__(self, name):
        if isinstance(name, int):
            return tuple.__getitem__(self, name)
        else:
            return self.__getattr__(name)
            
        
    def __getattr__(self, name):
        if name == 'ltype' or name == 'type':
            return self[0]
        elif name == 'val' or name == 'value':
            return self[1]
        elif name == 'start':
            return self[2]
        elif name == 'end':
            return self[3]
        elif name == 'comment':
            return False
        raise AttributeError

    def __str__(self):
        if self.val:
            return self.val
        else:
            return '<'+self.ltype+'>'
    
class ucSource(list):
    
    def __new__(cls, *args):
        return list.__new__(cls, *args)
    
    def __init__(self, *args):
        return self.extend(*args)

    def extend(self, arg):
        a = map(ucLexeme, arg)
        for i in range(0, len(a)-1):
            assert a[i].end <= a[i+1].start
        return super(ucSource, self).extend(a)
    
    def append(self, *args):
        return self.extend(args)
      
    def insert(self, i, arg):
        return self.insert(i, ucLexeme(arg))
    
    def scrubbed(self):
        return copy(self)
    
    def __getslice__(self, *args):
        return ucSource(super(ucSource, self).__getslice__(*args))
      
# rwfubmqqoiigevcdefhmidzavjwg
