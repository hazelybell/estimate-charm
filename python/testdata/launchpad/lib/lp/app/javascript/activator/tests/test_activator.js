/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.activator.test', function (Y) {

var tests = Y.namespace('lp.activator.test');
tests.suite = new Y.Test.Suite('Activator Tests');

var Assert = Y.Assert;  // For easy access to isTrue(), etc.

/*
 * A wrapper for the Y.Event.simulate() function.  The wrapper accepts
 * CSS selectors and Node instances instead of raw nodes.
 */
function simulate(selector, evtype) {
    var rawnode = Y.Node.getDOMNode(Y.one(selector));
    Y.Event.simulate(rawnode, evtype);
}

/* Helper function to clean up a dynamically added widget instance. */
function cleanup_widget(widget) {
    // Nuke the boundingBox, but only if we've touched the DOM.
    if (widget.get('rendered')) {
        var bb = widget.get('boundingBox');
        bb.get('parentNode').removeChild(bb);
    }
    // Kill the widget itself.
    widget.destroy();
}

tests.suite.add(new Y.Test.Case({
    name: 'activator_tests',


    setUp: function() {
        this.workspace = Y.one('#workspace');
        if (!this.workspace){
            Y.one(document.body).appendChild(Y.Node.create(
                '<div id="workspace" ' +
                'style="border: 1px solid blue; ' +
                'width: 20em; ' +
                'margin: 1em; ' +
                'padding: 1em">'+
                '</div>'));
            this.workspace = Y.one('#workspace');
        }
        this.workspace.appendChild(Y.Node.create(
            '<div id="example-1">' +
            '<div id="custom-animation-node"/>' +
            '<span class="yui3-activator-data-box">' +
            '    Original Value' +
            '</span>' +
            '<button ' +
            ' class="lazr-btn yui3-activator-act yui3-activator-hidden">' +
            '    Go' +
            '</button>' +
            '<div class="yui3-activator-message-box yui3-activator-hidden">' +
            '</div>' +
            '</div>'));
        this.activator = new Y.lp.ui.activator.Activator(
            {contentBox: Y.one('#example-1')});
        this.action_button = this.activator.get('contentBox').one(
            '.yui3-activator-act');
    },

    tearDown: function() {
        cleanup_widget(this.activator);
        this.workspace.set('innerHTML', '');
    },

    test_library_exists: function () {
        Y.Assert.isObject(Y.lp.ui.activator,
            "Could not locate the lp.ui.activator module");
    },

    test_correct_animation_node: function() {
        // Check that the correct animation node is used.
        // First check the default.
        Assert.areEqual(this.activator.get('contentBox'),
                    this.activator.animation_node);
        // Now check a custom one.
        var custom_node = Y.one('#custom-animation-node');
        this.activator = new Y.lp.ui.activator.Activator(
            {contentBox: Y.one('#example-1'), animationNode: custom_node});
        Assert.areEqual(custom_node, this.activator.animation_node);
    },

    test_unhiding_action_button: function() {
        this.action_button.addClass('yui3-activator-hidden');
        Assert.isTrue(this.action_button.hasClass('yui3-activator-hidden'));
        this.activator.render();
        Assert.isFalse(
            this.action_button.hasClass('yui3-activator-hidden'),
            "yui3-activator-hidden class wasn't removed from the " +
            "action button");
    },

    test_simulate_click_on_action_button: function() {
        var fired = false;
        this.activator.render();
        this.activator.subscribe('act', function(e) {
            fired = true;
        }, this);
        simulate(this.action_button, 'click');
        Assert.isTrue(fired, "'act' event wasn't fired.");
    },

    test_renderSuccess: function() {
        this.activator.render();
        var data = Y.Node.create('new value');
        var message = Y.Node.create('success message');
        Assert.isFalse(
            this.activator.get('contentBox').hasClass(
                'yui3-activator-success'),
            'The widget is not setup propertly.');

        this.activator.renderSuccess(data, message);

        Assert.isTrue(
            this.activator.get('contentBox').hasClass(
                'yui3-activator-success'),
            'renderSuccess did not add the success css class');

        var data_box = this.activator.get('contentBox').one(
            '.yui3-activator-data-box');
        Assert.areEqual(
            'new value',
            data_box.get('innerHTML'),
            'renderSuccess did not set the contents of the data-box');

        var message_body = this.activator.get('contentBox').one(
            '.yui3-activator-message-body');

        Assert.areEqual(
            'success message',
            message_body.get('innerHTML'),
            'renderSuccess did not set the contents of the message-body');
    },

    test_renderProcessing: function() {
        this.activator.render();
        var message_text = 'processing message';
        var message = Y.Node.create('<b>' + message_text + '</b>');
        Assert.isFalse(
            this.activator.get('contentBox').hasClass(
                'yui3-activator-processing'),
            'The widget is not setup propertly.');

        this.activator.renderProcessing(message);

        Assert.isTrue(
            this.activator.get('contentBox').hasClass(
                'yui3-activator-processing'),
            'renderProcessing did not add the processing css class');

        var message_body = this.activator.get('contentBox').one(
            '.yui3-activator-message-body');

        // Opera uppercases all tags, Safari lowercases all tags,
        // and IE gets an extra _yuid attribute in the <b>.
        var added_node = message_body.one('b');
        Assert.areEqual(
            message_text,
            added_node.get('innerHTML'),
            'renderProcessing did not set the contents of the message-body');
    },

    test_renderCancellation: function() {
        this.activator.render();
        var message_text = 'cancel message';
        var message = Y.Node.create('<b>' + message_text + '</b>');
        Assert.isFalse(
            this.activator.get('contentBox').hasClass(
                'yui3-activator-cancellation'),
            'The widget is not setup propertly.');

        this.activator.renderCancellation(message);

        Assert.isTrue(
            this.activator.get('contentBox').hasClass(
                'yui3-activator-cancellation'),
            'renderCancellation did not add the cancel css class');

        var message_body = this.activator.get('contentBox').one(
            '.yui3-activator-message-body');
        // Opera uppercases all tags, Safari lowercases all tags,
        // and IE gets an extra _yuid attribute in the <b>.
        var added_node = message_body.one('b');
        Assert.areEqual(
            message_text,
            added_node.get('innerHTML'),
            "renderCancellation didn't set the contents of the message-body");
    },

    test_renderFailure: function() {
        this.activator.render();
        var message = Y.Node.create('failure message');
        Assert.isFalse(
            this.activator.get('contentBox').hasClass(
                'yui3-activator-failure'),
            'The widget is not setup propertly.');

        this.activator.renderFailure(message);

        Assert.isTrue(
            this.activator.get('contentBox').hasClass(
                'yui3-activator-failure'),
            'renderFailure did not add the failure css class');

        var message_body = this.activator.get('contentBox').one(
            '.yui3-activator-message-body');

        Assert.areEqual(
            'failure message',
            message_body.get('innerHTML'),
            'renderFailure did not set the contents of the message-body');
    },

    test_empty_message_box: function() {
        // If no message_node is passed to renderFailure(),
        // the message box is hidden.
        this.activator.render();
        this.activator.renderFailure();

        var message_box = this.activator.get('contentBox').one(
            '.yui3-activator-message-box');

        Assert.isTrue(
            message_box.hasClass('yui3-activator-hidden'),
            "Message box should be hidden.");
        Assert.areEqual(
            '',
            message_box.get('innerHTML'),
            'Message box contents should be empty.');
    },

    test_closing_message_box: function() {
        this.activator.render();
        this.activator.renderFailure(Y.Node.create('short message'));

        var message_box = this.activator.get('contentBox').one(
            '.yui3-activator-message-box');
        var message_body = this.activator.get('contentBox').one(
            '.yui3-activator-message-body');
        var message_close_button = this.activator.get('contentBox').one(
            '.yui3-activator-message-close');
        simulate(message_close_button, 'click');
        Assert.isTrue(
            message_box.hasClass('yui3-activator-hidden'),
            "Message box should be hidden.");
        Assert.areEqual(
            'short message',
            message_body.get('innerHTML'),
            'Message body contents should still be there.');
    },

    test_widget_has_a_disabled_tabindex_when_focused: function() {
        // The tabindex attribute appears when the widget is focused.
        this.activator.render();
        this.activator.focus();

        // Be aware that in IE when the tabIndex is set to -1,
        // get('tabIndex') returns -1 as expected but getAttribute('tabIndex')
        // returns 65535. This is due to YUI's getAttribute() calling
        // dom_node.getAttribute('tabIndex', 2), which is an IE extension
        // that happens to treat this attribute as an unsigned integer instead
        // of as a signed integer.
        // http://msdn.microsoft.com/en-us/library/ms536429%28VS.85%29.aspx
        Assert.areEqual(
            -1,
            this.activator.get('boundingBox').get('tabIndex'),
            "The widget should have a tabindex of -1 (disabled).");
    }
}));


}, '0.1', {
    'requires': ['test', 'test-console', 'node', 'lp.ui.activator', 'event',
        'event-simulate']
});
