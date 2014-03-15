# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers for lp.codehosting.codeimport tests."""

__metaclass__ = type

__all__ = [
    'instrument_method', 'InstrumentedMethodObserver']


def instrument_method(observer, obj, name):
    """Wrap the named method of obj in an InstrumentedMethod object.

    The InstrumentedMethod object will send events to the provided observer.
    """
    func = getattr(obj, name)
    instrumented_func = _InstrumentedMethod(observer, name, func)
    setattr(obj, name, instrumented_func)


class _InstrumentedMethod:
    """Wrapper for a callable, that sends event to an observer."""

    def __init__(self, observer, name, func):
        self.observer = observer
        self.name = name
        self.callable = func

    def __call__(self, *args, **kwargs):
        self.observer.called(self.name, args, kwargs)
        try:
            value = self.callable(*args, **kwargs)
        except Exception as exc:
            self.observer.raised(self.name, exc)
            raise
        else:
            self.observer.returned(self.name, value)
            return value


class InstrumentedMethodObserver:
    """Observer for InstrumentedMethod."""

    def __init__(self, called=None, returned=None, raised=None):
        if called is not None:
            self.called = called
        if returned is not None:
            self.returned = returned
        if raised is not None:
            self.raised = raised

    def called(self, name, args, kwargs):
        """Called before an instrumented method."""
        pass

    def returned(self, name, value):
        """Called after an instrumented method returned."""
        pass

    def raised(self, name, exc):
        """Called when an instrumented method raises."""
        pass
