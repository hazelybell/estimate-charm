# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Construct and search simple tree structures.

`LookupTree` encapsulates a simple tree structure that can be used to
do lookups using one or more keys. This was originally created to
support mapping statuses from remote bug trackers into Launchpad
statuses.

Another main criteria was documentation. We want to be able to
automatically generate documentation from the lookup trees that are
specified.

Originally a simple dictionary lookup was attempted, but it proved
difficult to create some of the moderately complex mapping rules we
needed. Supporting defaults and such required additional logic, and
ordering was lost, which may be useful to document.

Secondly, a structure of tuples was attempted, and this proved easier
to construct. However, it proved difficult to see what was going on,
with brackets everywhere!

The final design is a compromise. `LookupTree` and `LookupBranch` both
feel tuple-like when constructing lookup trees in code, especially
because `LookupTree` will promote any regular tuples it's given into
`LookupBranch`es, but they store branches and keys as instance
attributes. They encapsulate the searching algorithm and a few other
conveniences. This makes the generation of lookup trees quite pleasant
on the eye, makes debugging easier, and means they can be customised.
"""

__metaclass__ = type
__all__ = [
    'LookupBranch',
    'LookupTree',
    ]

import copy
import string


class LookupBranch:
    """A branch point during a lookup, containing keys and a result."""

    def __init__(self, *args):
        """Construct a new `LookupBranch` from the given keys and result.

        Split out the keys from the result.  The last argument
        specified is the result of this branch, and all the other
        arguments are keys.

        As an extra step, the branch is verified by calling `_verify`.
        """
        super(LookupBranch, self).__init__()
        self.keys = args[:-1]
        self.result = args[-1]
        self._verify()

    def _verify(self):
        """Check the validity of the branch.

        The default implementation does nothing.

        :raises TypeError: If the branch is invalid.
        """
        pass

    @property
    def is_leaf(self):
        """Whether or not this is a leaf.

        If the result of this branch is not a `LookupTree`, then this
        is a leaf... as well as a branch... the terminology is a
        little confused :)
        """
        return not isinstance(self.result, LookupTree)

    @property
    def is_default(self):
        """Whether or not this is a default branch.

        If there are no keys for this branch, then this is a default
        branch.
        """
        return len(self.keys) == 0

    def describe(self, level=1):
        """A representation of this branch.

        If the result of this branch is a `LookupTree` instance, it's
        asked for a representation at a specific `level`, which
        corresponds to its position in the tree. This allows for
        pretty indentation to aid human comprehension.

        If the result is any other object, `_describe_result` is used.

        Keys are formatted using `_describe_key`.

        This is mainly intended as an aid to development.
        """
        format = 'branch(%s => %%s)'
        if self.is_default:
            format = format % '*'
        else:
            format = format % ', '.join(
                self._describe_key(key) for key in self.keys)
        if self.is_leaf:
            return format % self._describe_result(self.result)
        else:
            return format % self.result.describe(level)

    _describe_key_chars = set(string.letters + string.digits + '-_+=*')

    def _describe_key(self, key):
        """Return a pretty representation of a simple key.

        If the key, as a string, contains only characters from a small
        selected set, it is returned without quotes. Otherwise, the
        result of `repr` is returned.
        """
        as_string = str(key)
        if self._describe_key_chars.issuperset(as_string):
            return as_string
        else:
            return repr(key)

    def _describe_result(self, result):
        """Return a pretty representation of the branch result.

        By default, return the representation as returned by `repr`.
        """
        return repr(result)

    def __repr__(self):
        """A machine-readable representation of this branch."""
        return '%s(%s)' % (
            self.__class__.__name__,
            ', '.join(repr(item) for item in (self.keys + (self.result,))))


class LookupTree:
    """A searchable tree."""

    _branch_factory = LookupBranch

    def __init__(self, *args):
        """Construct a new `LookupTree`.

        Flatten or promote the given arguments into `LookupBranch`s.

        As an extra step, the branch is verified by calling `_verify`.

        :param args: `LookupBranch`s, `LookupTree`s, or iterables to
            be attached to this tree. Iterable arguments will be
            promoted to `LookupBranch` by calling `_branch_factory`
            with all the values from the iterator as positional
            arguments.
        """
        branches = []
        for arg in args:
            if isinstance(arg, LookupTree):
                # Extend this tree with the branches from the given
                # tree.
                branches.extend(arg.branches)
            elif isinstance(arg, LookupBranch):
                # Append this branch.
                branches.append(arg)
            else:
                # Promote a tuple or other iterable into a branch. The
                # last value from the iterable is the result of the
                # branch, and all the preceding values are keys.
                branches.append(self._branch_factory(*arg))

        # Prune the branches to remove duplicate paths.
        seen_keys = set()
        pruned_branches = []
        for branch in branches:
            prune = seen_keys.intersection(branch.keys)
            if len(prune) > 0:
                if len(prune) == len(branch.keys):
                    # This branch has no unseen keys, so skip it.
                    continue
                branch = copy.copy(branch)
                branch.keys = tuple(
                    key for key in branch.keys
                    if key not in prune)
            pruned_branches.append(branch)
            seen_keys.update(branch.keys)

        self.branches = tuple(pruned_branches)
        self._verify()

    def _verify(self):
        """Check the validity of the tree.

        Every branch in the tree must be an instance of
        `LookupBranch`. In addition, only one default branch can
        exist, and it must be the last branch.

        :raises TypeError: If the tree is invalid.
        """
        default = False
        for branch in self.branches:
            if not isinstance(branch, LookupBranch):
                raise TypeError('Not a LookupBranch: %r' % (branch,))
            if default:
                raise TypeError('Default branch must be last.')
            default = branch.is_default

    def find(self, key, *more):
        """Search this tree.

        Searches in the tree for `key`. If the result is another tree,
        it searches down that tree, using the first value of `more` as
        `key`. Once it gets to a leaf, whether or not all the keys
        (i.e. `key` + `more`) have been consumed, the result is
        returned.

        :raises KeyError: If a result is not found.
        """
        for branch in self.branches:
            if key in branch.keys or branch.is_default:
                if branch.is_leaf:
                    return branch.result
                elif len(more) >= 1:
                    try:
                        return branch.result.find(*more)
                    except KeyError as ex:
                        raise KeyError((key,) + ex.args)
                else:
                    raise KeyError(key)
        raise KeyError(key)

    def flatten(self):
        """Generate a flat representation of this tree.

        Generates tuples. The last element in the tuple is the
        result. The previous elements are the branches followed to
        reach the result.

        This can be useful for generating documentation, because it is
        a compact, flat representation of the tree.
        """
        for branch in self.branches:
            if branch.is_leaf:
                yield branch, branch.result
            else:
                for path in branch.result.flatten():
                    yield (branch,) + path

    @property
    def min_depth(self):
        """The minimum distance to a leaf."""
        return min(len(path) for path in self.flatten()) - 1

    @property
    def max_depth(self):
        """The maximum distance to a leaf."""
        return max(len(path) for path in self.flatten()) - 1

    def describe(self, level=1):
        """A representation of this tree, formatted for human consumption.

        The representation of each branch in this tree is indented
        corresponding to `level`, which indicates the position we are
        at within the tree that is being represented.

        When asking each branch for a representation, the next level
        is passed to `describe`, so that sub-trees will be indented
        more.

        This is mainly intended as an aid to development.
        """
        indent = '    ' * level
        format = indent + '%s'
        return 'tree(\n%s\n%s)' % (
            '\n'.join(format % branch.describe(level + 1)
                      for branch in self.branches),
            indent)

    def __repr__(self):
        """A machine-readable representation of this tree."""
        return '%s(%s)' % (
            self.__class__.__name__,
            ', '.join(repr(branch) for branch in self.branches))
