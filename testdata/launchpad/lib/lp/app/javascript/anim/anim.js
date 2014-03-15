/* Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.anim', function(Y) {

var namespace = Y.namespace('lp.anim'),
    testspace = Y.namespace('lp.anim.test'),
    attrcaller = Y.lp.extras.attrcaller;


/**
 * @function flash_in
 * @description Create a flash-in animation object.  Dynamically checks
 * the 'to' property to see that the node's color isn't "transparent".
 * @param cfg Additional Y.Anim configuration.
 * @return Y.Anim instance
 */
var flash_in;

flash_in = function(cfg) {
    var acfg = Y.merge(flash_in.defaults, cfg);
    var anim = new Anim(acfg);
    return anim;
};

flash_in.defaults = {
    duration: 1,
    easing: Y.Easing.easeIn,
    from: { backgroundColor: '#FFFF00' },
    to: { backgroundColor: '#FFFFFF' }
};


/**
 * @function green_flash
 * @description A green flash and fade, used to indicate new page data.
 * @param cfg Additional Y.Anim configuration.
 * @return Y.Anim instance
 */
var green_flash;

green_flash = function(cfg) {
    return flash_in(
        Y.merge(green_flash.defaults, cfg));
};

green_flash.defaults = {
    from: { backgroundColor: '#90EE90' }
};


/**
 * @function red_flash
 * @description A red flash and fade, used to indicate errors.
 * @param cfg Additional Y.Anim configuration.
 * @return Y.Anim instance
 */
var red_flash;

red_flash = function(cfg) {
    return flash_in(
        Y.merge(red_flash.defaults, cfg));
};

red_flash.defaults = {
    from: { backgroundColor: '#FF6666' }
};


/**
 * Resolve a selector, Node or NodeList into a NodeList.
 *
 * @return {Y.NodeList}
 */
var resolveNodeListFrom = function(protonode) {
    if (Y.Lang.isString(protonode)) {
        return Y.all(protonode);
    } else if (protonode instanceof Y.Node) {
        return new Y.NodeList([protonode]);
    } else if (protonode instanceof Y.NodeList) {
        return protonode;
    }
    throw('Not a selector, Node, or NodeList');
};


/**
 * The Anim widget similar to Y.anim.Anim, but supports operating on a
 * NodeList.
 *
 * @class Anim
 */
var Anim = function(config) {
    var nodelist = resolveNodeListFrom(config.node);
    this._anims = nodelist.map(function(node) {
        var ncfg = Y.merge(config, {node: node});
        var anim = new Y.Anim(ncfg);
        // We need to validate the config
        // afterwards because some of the
        // properties may be dynamic.
        var to = ncfg.to;
        // Check the background color to make sure
        // it isn't 'transparent'.
        if (Y.Lang.isObject(to) && Y.Lang.isFunction(to.backgroundColor)) {
            var bg = to.backgroundColor.call(anim, anim.get('node'));
            if (bg === 'transparent') {
                Y.error("Can not animate to a 'transparent' background " +
                        "in '" + anim + "'");
            }
        }
        // Reset the background color. This is
        // normally only necessary when the
        // original background color of the node
        // or its parent are not white, since we
        // normally fade to white.
        var original_bg = null;
        anim.on('start', function () {
            original_bg = anim.get('node').getStyle('backgroundColor');
        });
        anim.on('end', function () {
            anim.get('node').setStyle('backgroundColor', original_bg);
        });
        return anim;
    });
};

Anim.prototype = {

    /**
     * Run all animations.
     */
    run: function() {
        Y.each(this._anims, attrcaller("run"));
    },

    /**
     * Delegate all behavior back to the collection of animations.
     */
    on: function() {
        var args = arguments;
        Y.each(this._anims, function(anim) {
            anim.on.apply(anim, args);
        });
    }

};


// Exports.
namespace.Anim = Anim;
namespace.flash_in = flash_in;
namespace.green_flash = green_flash;
namespace.red_flash = red_flash;

// Exports for testing.
testspace.resolveNodeListFrom = resolveNodeListFrom;


}, "0.1", {"requires": ["base", "node", "anim", "lp.extras"]});
