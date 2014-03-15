/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Expander widget.  Can be used to let the user toggle the visibility of
 * existing elements on the page, or to make the page load elements on demand
 * as the user expands them.
 *
 * Synonyms: collapsible, foldable.
 *
 * Each expander needs two tags as "connection points":
 *  * Icon tag, to be marked up with the expander icon.
 *  * Content tag, to be exposed by the expander.
 *
 * Either may have initial contents.  The initial contents of the icon tag
 * stays in place, so it could say something like "Details..." that explains
 * what the icon means.  You'll want to hide it using the "hidden" class if
 * these contents should only be shown once the expander has been set up.
 *
 * Any initial contents of the content tag will be revealed when the expander
 * is opened; hide them using the "hidden" class if they should not be shown
 * when the expander has not been enabled.  An optional loader function may
 * produce new contents for this tag when the user first opens the expander.
 *
 * If you provide a loader function, the expander runs it when the user first
 * opens it.  The loader should produce a DOM node or node list(it may do this
 * asynchronously) and feed that back to the expander by passing it to the
 * expander's "receive" method.  The loader gets a reference to the expander
 * as its first argument.
 *
 * The expander is set up in its collapsed state by default.  If you want it
 * created in its expanded state instead, mark your content tag with the
 * "expanded" class.
 *
 * An expander may be created with a group_id. Expanders which belong to the
 * same group can only have one instance in the expanded state at any time. If
 * a collapsed expander is opened, any other open expander within the same
 * group will be closed.
 *
 * @module lp.app.widgets.expander
 * @requires node, event
 */

YUI.add('lp.app.widgets.expander', function(Y) {

var namespace = Y.namespace('lp.app.widgets.expander');

// Define some constants.
var EXPANDER_CREATED = 'expander:created',
    EXPANDER_DESTROYED = 'expander:destroyed',
    EXPANDER_STATE_CHANGED = 'expander:state_changed',
    EXPANDED = 'expander:expanded',
    COLLAPSED = 'expander:collapsed';

namespace.EXPANDER_CREATED = EXPANDER_CREATED;
namespace.EXPANDER_DESTORYED = EXPANDER_DESTROYED;
namespace.EXPANDER_STATE_CHANGED = EXPANDER_STATE_CHANGED;
namespace.EXPANDED = EXPANDED;
namespace.COLLAPSED = COLLAPSED;

/**
 * A single ExpanderRadioController instance is created for this namespace.
 * Each expander instance which is created with a group id is registered with
 * this controller. The controller ensures that only one expander from each
 * group is open at any time.
 */
function ExpanderRadioController() {
    ExpanderRadioController.superclass.constructor.apply(this, arguments);
}

ExpanderRadioController.NAME = "ExpanderRadioController";

Y.extend(ExpanderRadioController, Y.Base, {

    initializer: function() {
        this.expanders = {};
        var controller = this;
        Y.on(EXPANDER_CREATED, function(group_id, expander) {
            controller._registerExpander(group_id, expander);
        });
        Y.on(EXPANDER_DESTROYED, function(group_id, expander) {
            controller._deregisterExpander(group_id, expander);
        });
        Y.on(EXPANDER_STATE_CHANGED,
            function(group_id, new_state, active_expander) {
                controller._stateChangeProcessor(
                    group_id, new_state, active_expander);
            });
    },

    _stateChangeProcessor: function(group_id, new_state, active_expander) {
        Y.Array.forEach(this.expanders[group_id], function(expander) {
            if (new_state === EXPANDED && expander !== active_expander) {
                if (expander.isExpanded()) {
                    expander.render(false);
                }
            }
        }, this);
    },

    _registerExpander: function(group_id, expander) {
        if (!this.expanders.hasOwnProperty(group_id)) {
            this.expanders[group_id] = [];
        }
        this.expanders[group_id].push(expander);
    },

    _deregisterExpander: function(group_id, expander) {
        if (this.expanders.hasOwnProperty(group_id)) {
            var idx = Y.Array.indexOf(this.expanders[group_id], expander);
            if (idx !== -1) {
                this.expanders[group_id].splice(idx, 1);
            }
        }
    }
});

// Create the controller instance
if (namespace.expanderRadioController === undefined) {
    namespace.expanderRadioController = new ExpanderRadioController();
}

/*
 * Create an expander.
 *
 * @param icon_node Node to serve as connection point for the expander icon.
 * @param content_node Node to serve as connection point for expander content.
 * @param config Object with additional parameters.
 *     loader: A function that will produce a Node or NodeList to replace the
 *         contents of the content tag.  Receives the Expander object
 *         "expander" as its argument.  Once the loader has constructed the
 *         output Node or NodeList it wants to display ("output"), it calls
 *         expander.receive(output) to update the content node.
 *     animate_node: A node to perform an animation on.  Mostly useful for
 *         animating table rows/cells when you want to animate the inner
 *         content (eg. a <div>).
 *     no_animation: Set to true if no animation should be used.  Useful for
 *         when you can't rearrange the nodes so animations apply to them
 *         (eg. we want to show a bunch of rows in the same table).
 */
function Expander(icon_node, content_node, config) {
    Expander.superclass.constructor.apply(this);

    if (!Y.Lang.isObject(icon_node)) {
        throw new Error("No icon node given.");
    }
    if (!Y.Lang.isObject(content_node)) {
        throw new Error("No content node given.");
    }
    if (content_node.hasClass('hide-on-load')) {
        content_node.removeClass('hide-on-load');
        content_node.addClass(this.css_classes.hidden);
    }
    this.icon_node = icon_node;
    this.content_node = content_node;
    if (Y.Lang.isValue(config)) {
        this.config = config;
    } else {
        this.config = {};
    }
    this.loaded = !Y.Lang.isValue(this.config.loader);

    if (Y.Lang.isValue(this.config.animate_node)) {
        this._animate_node = Y.one(this.config.animate_node);
    } else {
        this._animate_node = this.content_node;
    }

    if (this.config.no_animation !== true) {
        this._animation = Y.lp.ui.effects.reversible_slide_out(
            this._animate_node);
    } else {
        this._animation = undefined;
    }

    if (Y.Lang.isValue(this.config.group_id)) {
        Y.fire(EXPANDER_CREATED, this.config.group_id, this);
    }

    // Is setup complete?  Skip any animations until it is.
    this.fully_set_up = false;
}
Expander.NAME = "Expander";
namespace.Expander = Expander;

Y.extend(Expander, Y.Base, {
    /*
     * CSS classes.
     */
    css_classes: {
        expanded: 'expanded',
        hidden: 'hidden'
    },

    destructor: function() {
        if (Y.Lang.isValue(this.config.group_id)) {
            Y.fire(EXPANDER_DESTROYED, this.config.group_id, this);
        }
    },

    /*
     * Return sprite name for given expander state.
     */
    nameSprite: function(expanded) {
        if (expanded) {
            return 'treeExpanded';
        } else {
            return 'treeCollapsed';
        }
    },

    /*
     * Is the content node currently expanded?
     */
    isExpanded: function() {
        return this.content_node.hasClass(this.css_classes.expanded);
    },

    /*
     * Either add or remove given CSS class from the content tag.
     *
     * @param want_class Whether this class is desired for the content tag.
     *     If it is, then the function may need to add it; if it isn't, then
     *     the function may need to remove it.
     * @param class_name CSS class name.
     */
    setContentClassIf: function(want_class, class_name) {
        if (want_class) {
            this.content_node.addClass(class_name);
        } else {
            this.content_node.removeClass(class_name);
        }
    },

    /*
     * Record the expanded/collapsed state of the content tag and fire the
     * state_changed event.
     */
    setExpanded: function(is_expanded) {
        var state_changed = this.isExpanded() !== is_expanded;
        this.setContentClassIf(is_expanded, this.css_classes.expanded);
        if (state_changed && Y.Lang.isValue(this.config.group_id)) {
            Y.fire(
                EXPANDER_STATE_CHANGED,
                this.config.group_id,
                is_expanded?EXPANDED:COLLAPSED, this);
        }
    },

    /*
     * Hide or reveal the content node (by adding the "hidden" class to it).
     *
     * @param expand Are we expanding?  If not, we must be collapsing.
     * @param no_animation {Boolean} Whether to short-circuit the animation?
     */
    foldContentNode: function(expand, no_animation) {
        var expander = this;
        var has_paused = false;
        if (no_animation === true || Y.Lang.isUndefined(this._animation)) {
            // Make the animation have the proper direction set from
            // the start.
            if (!Y.Lang.isUndefined(this._animation)) {
                this._animation.set('reverse', expand);
            }
            expander.setContentClassIf(
                !expand, expander.css_classes.hidden);
        } else {
            this._animation.set('reverse', !expand);

            if (expand) {
                // Show when expanding.
                expander.setContentClassIf(
                    false, expander.css_classes.hidden);
            } else {
                // Hide when collapsing but only after
                // animation is complete.
                this._animation.once('end', function() {
                    // Only hide if the direction has not been
                    // changed in the meantime.
                    if (this.get('reverse')) {
                        expander.setContentClassIf(
                            true, expander.css_classes.hidden);
                    }
                });
            }

            expander._animation.run();
        }
    },

    revealIcon: function() {
        this.icon_node
            .addClass('sprite')
            .removeClass('hidden');
    },

    /*
     * Set icon to either the "expanded" or the "collapsed" state.
     *
     * @param expand Are we expanding?  If not, we must be collapsing.
     */
    setIcon: function(expand) {
        this.icon_node
            .removeClass(this.nameSprite(!expand))
            .addClass(this.nameSprite(expand))
            .setStyle('cursor', 'pointer');
    },

    /*
     * Process the output node being produced by the loader.  To be invoked
     * by a custom loader when it's done.
     *
     * @param output A Node or NodeList to replace the contents of the content
     *     tag with.
     * @param failed Whether loading has failed and should be retried.
     */
    receive: function(output, failed) {
        if (failed === true) {
            this.loaded = false;
        }
        var from_height = this._animate_node.getStyle('height');
        this._animate_node.setContent(output);
        if (Y.Lang.isUndefined(this._animation)) {
            return;
        }
        var to_height = this._animate_node.get('scrollHeight');
        if (this._animation.get('running')) {
            this._animation.stop();
        }
        this._animation.set('to', { height: to_height });
        this._animation.set('from', { height: from_height });
        this._animation.run();
    },

    /*
     * Invoke the loader, and record the fact that the loader has been
     * started.
     */
    load: function() {
        this.loaded = true;
        this.config.loader(this);
    },

    /*
     * Set the expander's DOM elements to a consistent, operational state.
     *
     * @param expanded Whether the expander is to be rendered in its expanded
     *     state.  If not, it must be in the collapsed state.
     */
    render: function(expanded, no_animation) {
        this.foldContentNode(expanded, no_animation);
        this.setIcon(expanded);
        if (expanded && !this.loaded) {
            this.load();
        }
        this.setExpanded(expanded);
    },

    /**
     * Wrap node content in an <a> tag and mark it as js-action.
     *
     * @param node Y.Node object to modify: its content is modified
     *     in-place so node events won't be lost, but anything set on
     *     the inner content nodes might be.
     */
    wrapNodeWithLink: function(node) {
        var link_node = Y.Node.create('<a></a>')
            .addClass('js-action')
            .set('href', '#')
            .setContent(node.getContent());
        node.setContent(link_node);
    },

    /*
     * Set up an expander's DOM and event handler.
     *
     * @param linkify {Boolean} Wrap the icon node into an <A> tag with
     *     proper CSS classes and content from the icon node.
     */
    setUp: function(linkify) {
        var expander = this;
        function click_handler(e) {
            e.halt();
            expander.render(!expander.isExpanded());
        }

        this.render(this.isExpanded(), true);
        if (linkify === true) {
            this.wrapNodeWithLink(this.icon_node);
        }
        this.icon_node.on('click', click_handler);
        this.revealIcon();
        this.fully_set_up = true;
        return this;
    }
});

/*
 * Initialize expanders based on CSS selectors.
 *
 * @param widget_select CSS selector to specify each tag that will have an
 *     expander created inside it.
 * @param icon_select CSS selector for the icon tag inside each tag matched
 *     by widget_select.
 * @param content_select CSS selector for the content tag inside each tag
 *     matched by widget_select.
 * @param linkify Whether to linkify the content in the icon_select node.
 * @param loader Optional loader function for each expander that is set up.
 *     Must take an Expander as its argument, create a Node or NodeList with
 *     the output to be displayed, and feed the output to the expander's
 *     "receive" method.
 */
function createByCSS(widget_select, icon_select, content_select, linkify,
                     loader) {
    var config = {
        loader: loader
    };
    var expander_factory = function(widget) {
        var expander = new Expander(
            widget.one(icon_select), widget.one(content_select), config);
        expander.setUp(linkify);
    };
    Y.all(widget_select).each(expander_factory);
}
namespace.createByCSS = createByCSS;

}, "0.1", {
    "requires": ["array-extras", "base", "event", "node", "lp.ui.effects"]
});
