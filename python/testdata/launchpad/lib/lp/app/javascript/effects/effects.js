/* Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.ui.effects', function(Y) {

/**
 * Visual effects built on top of the YUI Animation library.
 *
 * @module lp.ui.effects
 * @namespace lp.ui.effects
 */

var namespace = Y.namespace('lp.ui.effects');

var OPENED = 'lazr-opened';
var CLOSED = 'lazr-closed';

/* Defaults for the slide_in and slide_out effects. */
namespace.slide_effect_defaults = {
    easing: Y.Easing.easeOut,
    duration: 0.4
};


/**
 * Gets the desired total height for a node.
 */
function default_to_height(node) {
    return node.get('scrollHeight');
}

/**
 * Produces a reversible slide-out animation as a Y.Anim object.
 *
 * Simply changing the 'reverse' attribute will pause the animation
 * and prepare it for restarting with run() from the point it was on.
 *
 * The target node obtains the 'lazr-opened' CSS class when open,
 * 'lazr-closed' when closed.
 *
 * @method reversible_slide_out
 * @public
 * @param node {Node|HTMLElement|Selector}  The node to apply the effect to.
 * @param user_cfg {Y.Anim config} Additional Y.Anim config parameters.
 *     These will override the default parameters of the same name.
 * @return {Y.Anim} A new animation instance.
 */
namespace.reversible_slide_out = function(node, user_cfg) {
    var cfg = Y.merge(namespace.slide_effect_defaults, user_cfg);

    if (!Y.Lang.isValue(cfg.node)) {
        cfg.node = node;
    }

    node = Y.one(node);

    // We don't want to stomp on what the user may have given as the
    // from.height and to.height;
    cfg.from        = cfg.from ? cfg.from : {};
    cfg.from.height = cfg.from.height ? cfg.from.height : 0;

    cfg.to          = cfg.to ? cfg.to : {};
    cfg.to.height   = cfg.to.height ? cfg.to.height : default_to_height;

    var anim = new Y.Anim(cfg);
    node.addClass(CLOSED);

    // Set what we need to calculate the new content's scrollHeight.
    // The call-site must ensure we can find the height (iow, display
    // CSS class should be set properly; setting 'display: block' was
    // not necessary for Expander, but may need to be added back).
    node.setStyles({
        height:   cfg.from.height,
        overflow: 'hidden'
    });

    anim.after('reverseChange', function() {
        if (this.get('running')) {
            // Reversing an animation direction always stops it if running.
            this.stop();

            // Store the current height as appropriate for the direction.
            var current_height = node.getStyle('height');
            var full_height = node.get('scrollHeight');

            if (this.get('reverse')) {
                // Animate from current point to closing.
                this.set('from', { height: '0px' });
                this.set('to', { height: current_height });
            } else {
                // Animate from current point to the fully open node.
                this.set('from', { height: current_height });
                this.set('to', { height: full_height });
            }
        } else {
            // Restore the default from/to if we are not in the middle
            // of the animation.
            this.set('from', { height: '0px' });
            this.set('to', { height: default_to_height });
            // Restore the normal node height if we are fully open
            // and need to fold back in.
            if (this.get('reverse')) {
                this.get('node').setStyle('height', 'auto');
            }
        }

    });

    anim.on('end', function() {
        if (this.get('reverse')) {
            node.addClass(CLOSED).removeClass(OPENED);
        } else {
            node.addClass(OPENED).removeClass(CLOSED);
        }
    });
    return anim;

};


/**
 * Produces a reversible slide-in animation as a Y.Anim object.
 *
 * Returned anim object is a reversed slide-out animation.  This means
 * that 'reversed' attribute will likely hold an opposite value from
 * what users might expect because it refers to a slide-out animation.
 *
 * The target node obtains the 'lazr-opened' CSS class when open,
 * 'lazr-closed' when closed.
 *
 * @method reversible_slide_in
 * @public
 * @param node {Node|HTMLElement|Selector}  The node to apply the effect to.
 * @param user_cfg {Y.Anim config} Additional Y.Anim config parameters.
 *     These will override the default parameters of the same name.
 * @return {Y.Anim} A new animation instance.
 */
namespace.reversible_slide_in = function(node, user_cfg) {
    var anim = namespace.reversible_slide_out(node, user_cfg);
    anim.set('reverse', true);
    return anim;
};


/**
 * Produces a simple slide-out drawer effect as a Y.Anim object.
 *
 * Starts by setting the container's overflow to 'hidden', display to 'block',
 * and height to '0'.  After the animation is complete, sets the
 * <code>drawer_closed</code> attribute on the animation object to
 * <code>false</code>, and sets the container overflow to 'visible'.
 *
 * The target node obtains the 'lazr-opened' CSS class when open,
 * 'lazr-closed' when closed.
 *
 * This animation is reversible.
 * XXX 20110704 Danilo:
 * Reversing doesn't actually make the animation restart from
 * where it was stopped, so "jerking" effect can still be seen.
 *
 * @method slide_out
 * @public
 * @param node {Node|HTMLElement|Selector}  The node to apply the effect to.
 * @param user_cfg {Y.Anim config} Additional Y.Anim config parameters.
 *     These will override the default parameters of the same name.
 * @return {Y.Anim} A new animation instance.
 */
namespace.slide_out = function(node, user_cfg) {
    var cfg = Y.merge(namespace.slide_effect_defaults, user_cfg);

    if (typeof cfg.node === 'undefined') {
        cfg.node = node;
    }

    node = Y.one(node);
    if (node === null) {
        Y.fail("A valid node, HTMLElement, or CSS3 selector must be given " +
               "for the slide_out animation.");
        return null;
    }

    // We don't want to stomp on what the user may have given as the
    // from.height and to.height;
    cfg.from        = cfg.from ? cfg.from : {};
    cfg.from.height = cfg.from.height ? cfg.from.height : 0;

    cfg.to          = cfg.to ? cfg.to : {};
    cfg.to.height   = cfg.to.height ? cfg.to.height : default_to_height;

    // Set what we need to calculate the new content's scrollHeight.
    node.setStyles({
        height:   cfg.from.height,
        overflow: 'hidden',
        display:  'block'
    });

    var anim = new Y.Anim(cfg);

    // Set a custom attribute so we can clearly track the slide direction.
    // Used when reversing the slide animation.
    anim.drawer_closed = true;
    add_slide_state_events(anim);
    node.addClass(CLOSED);

    return anim;
};


/**
 * Produces a simple slide-out drawer effect as a Y.Anim object.
 *
 * After the animation is complete, sets the
 * <code>drawer_closed</code> attribute on the animation object to
 * <code>true</code>.
 *
 * The target node obtains the 'lazr-opened' CSS class when open,
 * 'lazr-closed' when closed.
 *
 * This animation is reversible.
 *
 * @method slide_in
 * @public
 * @param node {Node|HTMLElement|Selector}  The node to apply the effect to.
 * @param user_cfg {Y.Anim config} Additional Y.Anim config parameters.
 *     These will override the default parameters of the same name.
 * @return {Y.Anim} A new animation instance.
 */
namespace.slide_in = function(node, user_cfg) {
    var cfg = Y.merge(namespace.slide_effect_defaults, user_cfg);

    if (typeof cfg.node === 'undefined') {
        cfg.node = node;
    }

    node = Y.one(node);
    if (node === null) {
        Y.fail("A valid node, HTMLElement, or CSS3 selector must be given " +
               "for the slide_in animation.");
        return null;
    }

    var default_from_height = node.get('clientHeight');

    // We don't want to stomp on what the user may have given as the
    // from.height and to.height;
    cfg.from        = cfg.from ? cfg.from : {};
    cfg.from.height = cfg.from.height ? cfg.from.height : default_from_height;

    cfg.to          = cfg.to ? cfg.to : {};
    cfg.to.height   = cfg.to.height ? cfg.to.height : 0;

    var anim = new Y.Anim(cfg);

    // Set a custom attribute so we can clearly track the slide direction.
    // Used when reversing the slide animation.
    anim.drawer_closed = false;
    add_slide_state_events(anim);
    node.addClass(OPENED);

    return anim;
};

/*
 * Events designed to handle a sliding animation's opening and closing state.
 */
function add_slide_state_events(anim) {
    var node = anim.get('node');
    anim.on('start', function() {
        if (!this.drawer_closed) {
            // We're closing the draw, so hide the overflow.
            // XXX 20110704 Danilo: this logic seems broken for reversed
            // animations.
            node.setStyle('overflow', 'hidden');
        }
    });

    anim.on('end', function() {
        if (this.drawer_closed) {
            // We've finished opening the drawer, so show the overflow, just
            // to be safe.
            // XXX 20110704 Danilo: this logic seems broken for reversed
            // animations.
            this.drawer_closed = false;
            node.setStyle('overflow', 'visible')
                .addClass(OPENED)
                .removeClass(CLOSED);
        } else {
            this.drawer_closed = true;
            node.addClass(CLOSED).removeClass(OPENED);
        }
    });
}


}, null, {"skinnable": true,
          "requires":["anim", "node"]});
