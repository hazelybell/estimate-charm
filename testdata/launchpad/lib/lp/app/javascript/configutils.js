/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.configutils', function(Y) {
    /**
     * The configutils module provides objects for managing the config
     * or settings of a web page or widget.
     *
     * Widgets that want to be accessed from a settings/config
     * icon should extend BaseConfigUtil and provide a callback that
     * will run when the icon is clicked.
     *
     * @module lp.configutils
     */

    // Constants
    var CONTENT_BOX = 'contentBox',
        EMPTY_FN = function() {};

    /**
     * BaseConfigUtil is the base object that every FooConfigUtil
     * object should extend.
     *
     * @class BaseConfigUtil
     * @extends Widget
     * @constructor
     */
    function BaseConfigUtil() {
        BaseConfigUtil.superclass.constructor.apply(this, arguments);
    }

    BaseConfigUtil.NAME = 'baseconfigutil';

    BaseConfigUtil.ATTRS = {
        /**
         * A reference to the anchor element created during renderUI.
         *
         * @attribute anchor
         * @type Y.Node
         * @default null
         */
        anchor: {
            value: null
        }
    };

    Y.extend(BaseConfigUtil, Y.Widget, {

        /**
         * Hook for subclasses to do something when the settings
         * icon is clicked.
         */
        _handleClick: EMPTY_FN,

        /**
         * Hook for subclasses to do work after renderUI.
         */
        _extraRenderUI: EMPTY_FN,

        /**
         * Create the anchor element that will display the settings icon.
         *
         * @method renderUI
         */
        renderUI: function() {
            var anchor = Y.Node.create(
                '<a class="sprite config action-icon">Configure</a>');
            anchor.set('title', 'Customise visible bug information');
            this.set('anchor', anchor);
            var content = this.get(CONTENT_BOX);
            content.append(anchor);
            this._extraRenderUI();
        },

        /**
         * Wire up the anchor element to _handleClick.
         *
         * Objects that extend BaseConfigUtil should create their own
         * _handleClick method.
         *
         * @method bindUI
         */
        bindUI: function() {
            // Do some work here to set up click handlers.
            // Add the a element to ATTRS.
            var anchor = this.get('anchor');
            var that = this;
            anchor.on('click', function(e) {
                that._handleClick(e);
            });
        }

    });

    var configutils = Y.namespace('lp.configutils');
    configutils.BaseConfigUtil = BaseConfigUtil;

}, '0.1', {'requires': ['widget']});
