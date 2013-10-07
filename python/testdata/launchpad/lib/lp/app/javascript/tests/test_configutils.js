/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.baseconfigutils.test', function(Y) {

var baseconfigutils_test = Y.namespace('lp.baseconfigutils.test');

var suite = new Y.Test.Suite('BaseConfigUtil Tests');

var Assert = Y.Assert;

suite.add(new Y.Test.Case({

    name: 'baseconfigutils_widget_tests',

    tearDown: function() {
        if (Y.Lang.isValue(this.baseconfig)) {
            this.baseconfig.destroy();
        }
    },

    _makeSrcNode: function(id) {
        var src_node = Y.Node.create('<div></div>').set('id', id);
        Y.one('body').appendChild(src_node);
    },

    test_base_config_render: function() {
        // The div rendered should have sprite and config
        // class names added to it.
        this._makeSrcNode();
        this.baseconfig = new Y.lp.configutils.BaseConfigUtil({
            srcNode: Y.one('#test-div')
        });
        this.baseconfig.render();
        var config_a = Y.one('.yui3-baseconfigutil a');
        Assert.isTrue(config_a.hasClass('sprite'));
        Assert.isTrue(config_a.hasClass('config'));
    },

    test_base_config_anchor_attribute: function() {
        // BaseConfigUtil keeps a reference to the DOM node it created.
        this._makeSrcNode();
        this.baseconfig = new Y.lp.configutils.BaseConfigUtil({
            srcNode: Y.one('#test-div')
        });
        // anchor should be null before render.
        Assert.isNull(this.baseconfig.get('anchor'));
        // After render, "anchor" attribute should match the node via DOM.
        this.baseconfig.render();
        var config_via_dom = Y.one('.yui3-baseconfigutil a');
        Assert.areEqual(config_via_dom, this.baseconfig.get('anchor'));
    },

    test_base_config_click_callback: function() {
        // _handleClick should be called when the settings
        // icon is clicked.
        this._makeSrcNode();
        this.baseconfig = new Y.lp.configutils.BaseConfigUtil({
            srcNode: Y.one('#test-div')
        });
        // _handleClick already exists but does nothing.
        Assert.areSame(this.baseconfig._handleClick(), undefined);
        var click_handled = false;
        this.baseconfig._handleClick = function(e) {
            click_handled = true;
        };
        this.baseconfig.render();
        Y.one('.config').simulate('click');
        Assert.isTrue(click_handled);
    },

    test_base_config_extra_render_ui: function() {
        // BaseConfigUtil provides a hook for subclasses to do
        // additional renderUI work.
        this._makeSrcNode();
        this.baseconfig = new Y.lp.configutils.BaseConfigUtil({
            srcNode: Y.one('#test-div')
        });
        // _extraRenderUI already exists but does nothing.
        Assert.areSame(this.baseconfig._extraRenderUI(), undefined);
        var href = 'http://example.com/';
        var html = 'This is some sample text to add.';
        var that = this;
        this.baseconfig._extraRenderUI = function() {
            var anchor = that.baseconfig.get('anchor');
            anchor.set('href', href);
            anchor.set('innerHTML', html);
        };
        this.baseconfig.render();
        var anchor = this.baseconfig.get('anchor');
        Assert.areEqual(href, anchor.get('href'));
        Assert.areEqual(html, anchor.get('innerHTML'));
    }

}));

baseconfigutils_test.suite = suite;

}, '0.1', {'requires': ['test', 'node-event-simulate', 'lp.configutils']});
