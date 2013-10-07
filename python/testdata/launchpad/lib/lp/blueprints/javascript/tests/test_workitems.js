YUI.add('lp.workitems.expanders.test', function (Y) {

var tests = Y.namespace('lp.workitems.expanders.test');
tests.suite = new Y.Test.Suite("lp.workitems.expanders Tests");
var module = Y.lp.workitems.expanders;

tests.suite.add(new Y.Test.Case({
    name: 'setUpWorkItemExpanders test',

    setUp: function() {
        this.fixture = Y.one("#fixture");
        module.test__ping_called = false;
    },

    tearDown: function () {
        if (this.fixture !== null) {
          this.fixture.empty();
        }
        delete this.fixture;
        delete module.test__ping_called;
    },

    _setup_fixture: function(template_selector) {
        var template = Y.one(template_selector).getContent();
        var test_node = Y.Node.create(template);
        this.fixture.append(test_node);
    },

    _all_expanders_are_closed: function(){
        var found_open = false;
        Y.all('.collapsible-body').each(function(e) {
            found_collapsible_body = true;
            if (!e.hasClass('hidden'))
            {
                found_open = true;
                return;
            }
        });
        return found_open === false;
    },

    _all_expanders_are_open: function(){
        var found_closed = false;
        Y.all('.collapsible-body').each(function(e) {
            found_collapsible_body = true;
            if (e.hasClass('hidden'))
            {
                found_closed = true;
                return;
            }
        });
        return found_closed === false;
    },

    test_setUpWorkItemExpanders: function() {
        this._setup_fixture('#work-items-test-0');

        Y.all('.collapsible-body').each(function(e) {
            Y.Assert.isFalse(e.hasClass('lazr-closed'));
        });

        Y.all('[class=expandable]').each(function(e) {
            module._add_expanders(e);
        });

        Y.all('.collapsible-body').each(function(e) {
            // For some reason lazr-closed is attached when expander bodies are
            // in their default state. Once clicked open they get lazr-open
            // and clicked closed they get the classes lazr-closed and hidden.
            // This assert is more encapsulating in case this changes.
            Y.Assert.isTrue(e.hasClass('lazr-closed') ||
                            e.hasClass('lazr-open'));
        });
    },

    attach_ping_catcher: function(event){
        module._attach_handler(event, function(){
            module.test__ping_called = true;
        });
    },

    test_attach_handler: function() {
        // Test that _attach_handler attaches a function as expected. This
        // covers expand, collapse and default functions.
        this._setup_fixture('#work-items-test-0');

        // Call the expander attach handler function
        Y.all('.expandall_link').on("click", this.attach_ping_catcher);

        // Check that it attached correctly
        Y.one('.expandall_link').simulate('click');
        Y.Assert.isTrue(module.test__ping_called);
    },

    test_default_closed: function() {
        // Test that clicking the default link restores expanders to their
        // initial state.

        this._setup_fixture('#work-items-test-default-collapsed');
        module.setUpWorkItemExpanders({ no_animation: true });

        // The test document should have all expanders collapsed. Check this.
        Y.Assert.isTrue(this._all_expanders_are_closed());

        // Expand everything
        Y.one('.expandall_link').simulate('click');
        Y.Assert.isTrue(this._all_expanders_are_open());

        // Return to default (collapsed)
        Y.one('.defaultall_link').simulate('click');
        Y.Assert.isTrue(this._all_expanders_are_closed());

        // Collapse everything (should be no change)
        Y.one('.collapseall_link').simulate('click');
        Y.Assert.isTrue(this._all_expanders_are_closed());

        // Check default link leaves everything closed
        Y.one('.defaultall_link').simulate('click');
        Y.Assert.isTrue(this._all_expanders_are_closed());
    },

    test_default_open: function() {
        // Test that clicking the default link restores expanders to their
        // initial state.

        this._setup_fixture('#work-items-test-default-expanded');
        module.setUpWorkItemExpanders({ no_animation: true });

        // The test document should have all expanders collapsed. Check this.
        Y.Assert.isTrue(this._all_expanders_are_closed());

        // Expand everything
        Y.one('.expandall_link').simulate('click');
        Y.Assert.isTrue(this._all_expanders_are_open());

        // Set to default (should be no change)
        Y.one('.defaultall_link').simulate('click');
        Y.Assert.isTrue(this._all_expanders_are_open());

        // Collapse everything
        Y.one('.collapseall_link').simulate('click');
        Y.Assert.isTrue(this._all_expanders_are_closed());

        // Check default link opens everything back up
        Y.one('.defaultall_link').simulate('click');
        Y.Assert.isTrue(this._all_expanders_are_open());
    }
}));

}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'test-console', 'node', 'lp.ui.picker-base',
               'lp.workitems.expanders',
               'event', 'node-event-simulate', 'dump']
});
