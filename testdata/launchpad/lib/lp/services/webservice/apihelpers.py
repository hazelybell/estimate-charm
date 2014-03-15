# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers to patch circular import shortcuts for the webservice.

Many of the exports for the webservice entries deliberately set various
types to `Interface` because using the real types cause circular import
problems.

The only current option is to later patch the types to the correct value.
The helper functions in this file make that easy.
"""

__metaclass__ = type

__all__ = [
    'patch_choice_parameter_type',
    'patch_choice_vocabulary',
    'patch_collection_property',
    'patch_collection_return_type',
    'patch_entry_explicit_version',
    'patch_entry_return_type',
    'patch_list_parameter_type',
    'patch_operation_explicit_version',
    'patch_operations_explicit_version',
    'patch_plain_parameter_type',
    'patch_reference_property',
    ]


from lazr.restful.declarations import LAZR_WEBSERVICE_EXPORTED
from zope.schema import getFields


def patch_entry_return_type(exported_class, method_name, return_type):
    """Update return type for a webservice method that returns entries.

    :param exported_class: The class containing the method.
    :param method_name: The method name that you need to patch.
    :param return_type: The new return type for the method.
    """
    exported_class[method_name].queryTaggedValue(
        LAZR_WEBSERVICE_EXPORTED)['return_type'].schema = return_type


def patch_collection_return_type(exported_class, method_name, return_type):
    """Update return type for a webservice method that returns a collection.

    :param exported_class: The class containing the method.
    :param method_name: The method name that you need to patch.
    :param return_type: The new return type for the method.
    """
    collection = exported_class[method_name].queryTaggedValue(
        LAZR_WEBSERVICE_EXPORTED)
    collection['return_type'].value_type.schema = return_type


def patch_list_parameter_type(exported_class, method_name, param_name,
        param_type):
    """Update a list parameter type for a webservice method.

    :param exported_class: The class containing the method.
    :param method_name: The method name that you need to patch.
    :param param_name: The name of the parameter that you need to patch.
    :param param_type: The new type for the parameter.
    """
    method = exported_class[method_name]
    params = method.queryTaggedValue(LAZR_WEBSERVICE_EXPORTED)['params']
    params[param_name].value_type = param_type


def patch_plain_parameter_type(exported_class, method_name, param_name,
                               param_type):
    """Update a plain parameter type for a webservice method.

    :param exported_class: The class containing the method.
    :param method_name: The method name that you need to patch.
    :param param_name: The name of the parameter that you need to patch.
    :param param_type: The new type for the parameter.
    """
    exported_class[method_name].queryTaggedValue(
        LAZR_WEBSERVICE_EXPORTED)['params'][param_name].schema = param_type


def patch_choice_parameter_type(exported_class, method_name, param_name,
                                choice_type):
    """Update a `Choice` parameter type for a webservice method.

    :param exported_class: The class containing the method.
    :param method_name: The method name that you need to patch.
    :param param_name: The name of the parameter that you need to patch.
    :param choice_type: The new choice type for the parameter.
    """
    param = exported_class[method_name].queryTaggedValue(
        LAZR_WEBSERVICE_EXPORTED)['params'][param_name]
    param.vocabulary = choice_type


def patch_reference_property(exported_class, property_name, property_type):
    """Set the type of the given property on the given class.

    :param exported_class: The class containing the property.
    :param property_name: The name of the property whose type you need
        to patch.
    :param property_type: The new type for the property.
    """
    exported_class[property_name].schema = property_type


def patch_collection_property(exported_class, property_name,
                              collection_type):
    """Set the collection type of the given property on the given class.

    :param exported_class: The class containing the property.
    :param property_name: The name of the property whose type you need
        to patch.
    :param collection_type: The `Collection` type.
    """
    exported_class[property_name].value_type.schema = collection_type


def patch_choice_vocabulary(exported_class, method_name, param_name,
                            vocabulary):
    """Set the `Vocabulary` for a `Choice` parameter for a given method.

    :param exported_class: The class containing the property.
    :param property_name: The name of the property whose type you need
        to patch.
    :param vocabulary: The `Vocabulary` type.
    """
    exported_class[method_name].queryTaggedValue(
        LAZR_WEBSERVICE_EXPORTED)[
            'params'][param_name].vocabulary = vocabulary


def patch_entry_explicit_version(interface, version):
    """Make it look as though an entry definition used as_of.

    This function should be phased out in favor of actually using
    as_of. This function patches the entry's fields as well as the
    entry itself. Fields that are explicitly published as of a given
    version (even though the entry is not) are ignored.
    """
    tagged = interface.getTaggedValue(LAZR_WEBSERVICE_EXPORTED)
    versioned = tagged.dict_for_name(version) or tagged.dict_for_name(None)
    versioned['_as_of_was_used'] = True

    # Now tag the fields.
    for name, field in getFields(interface).items():
        tagged = field.queryTaggedValue(LAZR_WEBSERVICE_EXPORTED)
        if tagged is None:
            continue
        versioned = (
            tagged.dict_for_name(version) or
            tagged.dict_for_name(None))
        if versioned is None:
            # This field is explicitly published in some other version.
            # Just ignore it.
            continue
        else:
            versioned['_as_of_was_used'] = True


def patch_operations_explicit_version(interface, version, *method_names):
    """Make it look like operations' first tags were @operation_for_version.

    This function should be phased out in favor of actually using
    @operation_for_version, everywhere.
    """
    for method in method_names:
        patch_operation_explicit_version(interface, version, method)


def patch_operation_explicit_version(interface, version, method_name):
    """Make it look like an operation's first tag was @operation_for_version.

    This function should be phased out in favor of actually using
    @operation_for_version, everywhere.
    """
    tagged = interface[method_name].getTaggedValue(LAZR_WEBSERVICE_EXPORTED)
    error_prefix = "%s.%s: Attempted to patch to version %s, but " % (
        interface.__name__, method_name, version)
    if (len(tagged.stack) > 1
        and tagged.stack[0].version == None
        and tagged.stack[1].version == version):
        raise ValueError(
            error_prefix + (
                'it is already published in %s. Did you just change '
                'it to be explicitly published?' % version))
    if tagged.stack[0].version == version:
        raise ValueError(
            error_prefix + (
                'it seems to have already been patched. Does this '
                'method come from a mixin used in multiple interfaces?'))
    tagged.rename_version(None, version)
