# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Cached properties for situations where a property is computed once and then
returned each time it is asked for.

See `doc/propertycache.txt` for documentation.
"""

__metaclass__ = type
__all__ = [
    'cachedproperty',
    'clear_property_cache',
    'get_property_cache',
    ]

from functools import partial

from zope.interface import (
    implements,
    Interface,
    )
from zope.security.proxy import removeSecurityProxy


class IPropertyCache(Interface):

    def __getattr__(name):
        """Return the cached value corresponding to `name`.

        Raise `AttributeError` if no value is cached.
        """

    def __setattr__(name, value):
        """Cache `value` for `name`."""

    def __delattr__(name):
        """Delete value for `name`.

        If no value is cached for `name` this is a no-op.
        """

    def __contains__(name):
        """Whether or not `name` is cached."""

    def __iter__():
        """Iterate over the cached names."""


class DefaultPropertyCache:
    """A simple cache."""

    implements(IPropertyCache)

    # __getattr__ -- well, __getattribute__ -- and __setattr__ are inherited
    # from object.

    def __delattr__(self, name):
        """See `IPropertyCache`."""
        self.__dict__.pop(name, None)

    def __contains__(self, name):
        """See `IPropertyCache`."""
        return name in self.__dict__

    def __iter__(self):
        """See `IPropertyCache`."""
        return iter(self.__dict__)


def get_property_cache(target):
    """Obtain a `DefaultPropertyCache` for any object."""
    if IPropertyCache.providedBy(target):
        return target
    else:
        naked_target = removeSecurityProxy(target)
        try:
            return naked_target._property_cache
        except AttributeError:
            naked_target._property_cache = DefaultPropertyCache()
            return naked_target._property_cache


def clear_property_cache(target):
    """Clear the property cache."""
    get_property_cache(target).__dict__.clear()


class CachedProperty:
    """Cached property descriptor.

    Provides only the `__get__` part of the descriptor protocol. Setting and
    clearing cached values should be done explicitly via `IPropertyCache`
    instances.
    """

    def __init__(self, populate, name):
        """Initialize this instance.

        `populate` is a callable responsible for providing the value when this
        property has not yet been cached.

        `name` is the name under which this property will cache itself.
        """
        self.populate = populate
        self.name = name

    def __get__(self, instance, cls):
        if instance is None:
            return self
        cache = get_property_cache(instance)
        try:
            return getattr(cache, self.name)
        except AttributeError:
            value = self.populate(instance)
            setattr(cache, self.name, value)
            return value

    def __set__(self, instance, value):
        raise AttributeError(
            "%s cannot be set here; instead set explicitly with "
            "get_property_cache(object).%s = %r" % (
                self.name, self.name, value))

    def __delete__(self, instance):
        raise AttributeError(
            "%s cannot be deleted here; instead delete explicitly "
            "with del get_property_cache(object).%s" % (
                self.name, self.name))


def cachedproperty(name_or_function):
    """Decorator to create a cached property.

    See `doc/propertycache.txt` for usage.
    """
    if isinstance(name_or_function, basestring):
        name = name_or_function
        return partial(CachedProperty, name=name)
    else:
        name = name_or_function.__name__
        populate = name_or_function
        return CachedProperty(name=name, populate=populate)
