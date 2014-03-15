/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Utility functions for converting valid Launchpad names for use in
 * CSS classes and back.
 *
 * Launchpad account names match the pattern [a-z0-9][a-z0-9+.-]*.
 * CSS class names roughly match the pattern -?[_a-z][_a-z0-9-]*.
 *
 * These method uses the fact that CSS allows '_' anywhere whereas LP
 * does not use it to escape starting digits and '+' or '.'.
 *
 * When no exceptions are thrown,
 *   css_to_launchpad(launchpad_to_css(string))
 * is idempotent.
 *
 * See `lp.app.validators.name.valid_name_pattern` and
 * http://www.w3.org/TR/CSS21/grammar.html#scanner
 *
 * @module lp
 * @submodule names
 */

YUI.add('lp.names', function(Y) {

var namespace = Y.namespace('lp.names');

/**
 * Gets a name suitable to be used as a CSS class for the "valid"
 * Launchpad name.
 *
 * Throws an exception if the `name` is not a valid Launchpad name.
 *
 * This is a bijective function with the inverse provided by
 *   css_to_launchpad().
 *
 * @method launchpad_to_css
 * @param name {String} A valid Launchpad name (eg. a person or project name).
 * @return {String} A converted `name` usable in a CSS class directly.
 */
function launchpad_to_css(name) {

    // Ensure we're being asked to convert the valid LP name.
    if (!name.match(/^[a-z0-9][a-z0-9\+\.\-]*$/)) {
        Y.error(
            'Passed value "' + name + '" is not a valid Launchpad name.');
        return;
    }

    if (name.match(/^[a-z][a-z0-9\-]*$/)) {
        // This is an intersection between valid LP and CSS names.
        return name;
    } else {
        // Do the conversion.
        var first_char = name.charAt(0);
        if (first_char >= '0' && first_char <= '9') {
            name = '_' + name;
        }

        // In the rest of the string, we convert all "+"s with "_y" and all
        // "."s with "_z".
        name = name.replace(/\+/g, '_y');
        name = name.replace(/\./g, '_z');
    }
    return name;
}
namespace.launchpad_to_css = launchpad_to_css;

/**
 * Convert the CSS name as gotten by launchpad_to_css to
 * it's originating Launchpad name.
 *
 * Throws an exception if the `name` is not a valid CSS class name
 * and in the format as produced by launchpad_to_css.
 * WARNING: this won't produce a valid Launchpad name for arbitrary
 * CSS class names.
 *
 * This is an inverse function of the function
 *   launchpad_to_css().
 *
 * @method css_to_launchpad
 * @param name {String} A valid CSS class name, but usually the result of
 *   launchpad_to_css() call.
 * @return {String} A converted `name` that is identical to the originating
 *   Launchpad name passed into launchpad_to_css().
 *   In practice, starting '_a', '_b', ..., '_j' are replaced with
 *   '0', '1', ..., '9' and '_y' and '_z' are replaced with '+' and '.'
 *   throughout the string.
 */
function css_to_launchpad(name) {
    if (!name.match(/^-?[_a-z][_a-z0-9\-]*$/)) {
        Y.error(
            'Passed value "' + name + '" is not a valid CSS class name.');
    }
    if (!name.match(/^((_[0-9yz])|[a-z])([a-z0-9\-]|(_[yz]))*$/)) {
        Y.error(
            'Passed value "' + name +
                '" is not produced by launchpad_to_css.');
    }

    if (name.match(/^[a-z][a-z0-9\-]*$/)) {
        // This is an intersection between valid LP and CSS names.
        return name;
    }

    if (name.charAt(0) === '_') {
        // It may start with a digit (iow, '_0' to '_9' for digits,
        // or '_y', '_z' for '+', '.' but we don't care about these [yet]).
        var second_char = name.charAt(1);
        if (second_char >= '0' && second_char <= '9') {
            name = name.substr(1);
        }
    }
    // Replace escaped variants of '+' and '.' back.
    name = name.replace(/_y/g, '+');
    name = name.replace(/_z/g, '.');

    return name;
}
namespace.css_to_launchpad = css_to_launchpad;

}, "0.1", {"requires": []});
