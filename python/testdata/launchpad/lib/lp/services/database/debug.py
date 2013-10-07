# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

'''
Replace the psycopg connect method with one that returns a wrapped connection.
'''

import logging
import textwrap
import traceback

import psycopg

# From http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/279155
def LN(*args, **kwargs):
    """Prints a line number and some text.

    A variable number of positional arguments are allowed. If
        LN(obj0, obj1, obj2)
    is called, the text part of the output looks like the output from
        print obj0, obj1, obj2
    The optional keyword "wrap" causes the message to be line-wrapped. The
    argument to "wrap" should be "1" or "True". "name" is another optional
    keyword parameter. This is best explained by an example:
        from linenum import LN
        def fun1():
            print LN('error', 'is', 'here')
        def fun2():
            print LN('error',  'is', 'here', name='mess')
        fun1()
        fun2()
    The output is:
        L3 fun1: error is here
        L5 mess: error is here
    """
    stack = traceback.extract_stack()
    a, b, c, d = stack[-3]
    out = []
    for obj in args:
        out.append(str(obj))
    text = ' '.join(out)
    if 'name' in kwargs:
        text = 'L%s %s: %s' % (b, kwargs['name'], text)
    else:
        text = 'L%s %s: %s' % (b, c, text)
    if 'wrap' in kwargs and kwargs['wrap']:
        text = textwrap.fill(text)
    return text


class ConnectionWrapper(object):
    _log = None
    _real_con = None
    def __init__(self, real_con):
        self.__dict__['_log'] = \
                logging.getLogger('lp.services.database.debug').debug
        self.__dict__['_real_con'] = real_con

    def __getattr__(self, key):
        if key in ('rollback','close','commit'):
            print '%s %r.__getattr__(%r)' % (LN(), self, key)
            self.__dict__['_log']('__getattr__(%r)', key)
        return getattr(self._real_con, key)

    def __setattr__(self, key, val):
        print '%s %r.__setattr__(%r, %r)' % (LN(), self, key, val)
        self.__dict__['_log']('__setattr__(%r, %r)', key, val)
        return setattr(self._real_con, key, val)

_org_connect = None

def debug_connect(*args, **kw):
    global _org_connect
    con = ConnectionWrapper(_org_connect(*args, **kw))
    logging.getLogger('lp.services.database.debug').debug(
            'connect(*%r, **%r) == %r', args, kw, con
            )
    print '%s connect(*%r, **%r) == %r' % (LN(), args, kw, con)
    return con

def install():
    global _org_connect
    assert _org_connect is None, 'Already installed'
    _org_connect = psycopg.connect
    psycopg.connect = debug_connect

def uninstall():
    global _org_connect
    assert _org_connect is not None, 'Not installed'
    psycopg.connect = _org_connect
    _org_connect = None

