/**
 * Copyright 2011 Canonical Ltd. This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Things that YUI3 really needs.
 *
 * @module lp
 * @submodule extras
 */

YUI.add('lp.extras', function(Y) {

var namespace = Y.namespace("lp.extras"),
    NodeList = Y.NodeList;

/**
 * NodeList is crying out for map.
 * @static
 *
 * @param {Y.NodeList|Array} instance The node list or array of nodes
 *     (Node or DOM nodes) to map over.
 * @param {Function} fn The function to apply. It receives 1 argument:
 *     the current Node instance.
 * @param {Object} context optional An optional context to apply the
 *     function with. The default context is the current Node
 *     instance.
 */
NodeList.map = function(instance, fn, context) {
    return Y.Array.map(
        Y.Array.map(Y.Array(NodeList.getDOMNodes(instance)), Y.one),
        function(node) {
            return fn.call(context || node, node);
        }
    );
};

/**
 * NodeList is crying out for map.
 *
 * @param {Function} fn The function to apply. It receives 1 argument:
 *     the current Node instance.
 * @param {Object} context optional An optional context to apply the
 *     function with. The default context is the current Node
 *     instance.
 */
NodeList.prototype.map = function(fn, context) {
    return NodeList.map(this, fn, context);
};

/**
 * Returns a function that gets the named attribute from an object.
 *
 * @param {String} name The attribute to get.
 */
var attrgetter = function(name) {
    return function(thing) {
        return thing[name];
    };
};

/**
 * Returns a function that gets the named attribute from an array of
 * objects (returning those attributes as an array).
 *
 * @param {String} name The attribute to select.
 */
var attrselect = function(name) {
    return function(things) {
        return Y.Array.map(Y.Array(things), attrgetter(name));
    };
};

/**
 * Returns a function that calls a named function on an object.
 *
 * @param {String} name The name of the function to look for.
 *
 * Remaining arguments are passed to the discovered function.
 */
var attrcaller = function(name) {
    var args = Y.Array(arguments).splice(1);
    return function(thing) {
        return thing[name].apply(thing, args);
    };
};

// Exports.
namespace.attrgetter = attrgetter;
namespace.attrselect = attrselect;
namespace.attrcaller = attrcaller;

}, "0.1", {requires: ["array-extras", "node"]});
