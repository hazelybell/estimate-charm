# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
This code is from:
    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/286222
    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/65333
This is under the Python Licence.

It also contains spiv's code from:
    http://twistedmatrix.com/users/spiv/countrefs.py
This is under 'MIT Licence if I'm pressed'

None of this should be in day-to-day use. Feel free to document usage
and improve APIs as needed.

"""

__metatype__ = type
__all__ = [
    'classesWithMostRefs',
    'countsByType',
    'deltaCounts',
    'logInThread',
    'memory',
    'mostRefs',
    'printCounts',
    'readCounts',
    'resident',
    'stacksize',
    ]


import gc
import os
import sys
import threading
import time
import types


_proc_status = '/proc/%d/status' % os.getpid()

_scale = {'kB': 1024.0, 'mB': 1024.0*1024.0,
          'KB': 1024.0, 'MB': 1024.0*1024.0}

def _VmB(VmKey):
    '''Private.
    '''
    global _proc_status, _scale
     # get pseudo file  /proc/<pid>/status
    try:
        t = open(_proc_status)
        v = t.read()
        t.close()
    except OSError:
        return 0.0  # non-Linux?
     # get VmKey line e.g. 'VmRSS:  9999  kB\n ...'
    i = v.index(VmKey)
    v = v[i:].split(None, 3)  # whitespace
    if len(v) < 3:
        return 0.0  # invalid format?
     # convert Vm value to bytes
    return float(v[1]) * _scale[v[2]]


def memory(since=0.0):
    '''Return memory usage in bytes.
    '''
    return _VmB('VmSize:') - since


def resident(since=0.0):
    '''Return resident memory usage in bytes.
    '''
    return _VmB('VmRSS:') - since


def stacksize(since=0.0):
    '''Return stack size in bytes.
    '''
    return _VmB('VmStk:') - since


def dump_garbage():
    """
    show us what's the garbage about

    import gc
    gc.enable()
    gc.set_debug(gc.DEBUG_LEAK)

    """

    # force collection
    print "\nGARBAGE:"
    gc.collect()

    print "\nGARBAGE OBJECTS:"
    for x in gc.garbage:
        s = str(x)
        if len(s) > 80:
            s = s[:80]
        print type(x), "\n  ", s

# This is spiv's reference count code, under 'MIT Licence if I'm pressed'.
#

def classesWithMostRefs(n=30):
    """Return the n ClassType objects with the highest reference count.

    This gives an idea of the number of objects in the system by type,
    since each instance will have at lest one reference to the class.

    :return: A list of tuple (count, type).
    """
    d = {}
    for obj in gc.get_objects():
        if type(obj) in (types.ClassType, types.TypeType):
            d[obj] = sys.getrefcount(obj)
    counts = [(x[1], x[0]) for x in d.items()]
    counts.sort()
    return reversed(counts[-n:])


def mostRefs(n=30):
    """Return the n types with the highest reference count.

    This one uses a different algorithm than classesWithMostRefs. Instead of
    retrieving the number of references to each ClassType, it counts the
    number of objects returned by gc.get_objects() and aggregates the results
    by type.

    :return: A list of tuple (count, type).
    """
    return countsByType(gc.get_objects(), n=n)


def countsByType(objects, n=30):
    """Return the n types with the highest instance count in a list.

    This takes a list of objects and count the number of objects by type.
    """
    d = {}
    for obj in objects:
        if type(obj) is types.InstanceType:
            cls = obj.__class__
        else:
            cls = type(obj)
        d[cls] = d.get(cls, 0) + 1
    counts = [(x[1], x[0]) for x in d.items()]
    counts.sort()
    return reversed(counts[-n:])


def deltaCounts(counts1, counts2, n=30):
    """Compare two references counts lists and return the increase."""
    counts1_map = dict((ref_type, count) for count, ref_type in counts1)
    counts2_map = dict((ref_type, count) for count, ref_type in counts2)
    types1 = set(counts1_map.keys())
    types2 = set(counts2_map.keys())
    delta = []
    # Types that disappeared.
    for ref_type in types1.difference(types2):
        delta.append((-counts1_map[ref_type], ref_type))

    # Types that changed.
    for ref_type in types1.intersection(types2):
        diff = counts2_map[ref_type] - counts1_map[ref_type]
        if diff != 0:
            delta.append((diff, ref_type))

    # New types.
    for ref_type in types2.difference(types1):
        delta.append((counts2_map[ref_type], ref_type))

    delta.sort()
    return reversed(delta[-n:])


def printCounts(counts, file=None):
    for c, obj in counts:
        if file is None:
            print c, obj
        else:
            file.write("%s %s\n" % (c, obj))

def readCounts(file, marker=None):
    """Reverse of printCounts().

    If marker is not None, this will return the counts as soon as a line
    containging is encountered. Otherwise, it reads until the end of file.
    """
    counts = []
    # We read one line at a time because we want the file pointer to
    # be after the marker line if we encounters it.
    while True:
        line = file.readline()
        if not line or (marker is not None and line == marker):
            break
        count, ref_type = line.strip().split(' ', 1)
        counts.append((int(count), ref_type))
    return counts


def logInThread(n=30):
    reflog = file('/tmp/refs.log','w')
    t = threading.Thread(target=_logRefsEverySecond, args=(reflog, n))
    # Allow process to exit without explicitly stopping thread.
    t.setDaemon(True)
    t.start()


def _logRefsEverySecond(log, n):
    while True:
        printCounts(mostRefs(n=n), file=log)
        log.write('\n')
        log.flush()
        time.sleep(1)


if __name__ == "__main__":
    counts = mostRefs()
    printCounts(counts)

    gc.enable()
    gc.set_debug(gc.DEBUG_LEAK)

    # make a leak
    l = []
    l.append(l)
    del l

    # show the dirt ;-)
    dump_garbage()

