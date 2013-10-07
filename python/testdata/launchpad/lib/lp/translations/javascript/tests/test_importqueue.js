/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 */
YUI.add('lp.translations.importqueue.test', function (Y) {

var tests = Y.namespace('lp.translations.importqueue.test');
tests.suite = new Y.Test.Suite("importqueue Tests");
var namespace = Y.lp.translations.importqueue;


var make_choice_confs = function() {
    // Make generic confs fot testing. The test can change these as needed.
    var confs = [];
    var values = ['Imported', 'Imported'];
    var statuses = ['Approved', 'Imported'];
    Y.Array.forEach(values, function(value) {
        var conf = {
            'value': value,
            'items': []
            };
        Y.Array.forEach(statuses, function(status) {
            conf.items.push({
                'style': '',
                'help': '',
                'css_class': 'translationimportstatus' + status,
                'description': '',
                'value': status,
                'disabled': false,
                'description_css_class': 'choice-description',
                'name': status
                });
            });
        confs.push(conf);
        });
    return confs;
};


tests.suite.add(new Y.Test.Case({
    name: 'importqueue macros',

    setUp: function() {
        fixture = Y.one("#fixture");
        var template = Y.one('#import-queue-listing').getContent();
        var test_node = Y.Node.create(template);
        fixture.append(test_node);
    },

    tearDown: function() {
        Y.one("#fixture").empty();
    },

    test_initialize_import_queue_page: function() {
        choice_confs = make_choice_confs();  // setup global choice_confs.
        namespace.initialize_import_queue_page(Y);
        Y.Assert.isTrue(
            Y.one('#import-queue-submit').hasClass('hidden'));
        Y.Assert.isTrue(
            Y.one('.status-select').hasClass('hidden'));
        status_choice = Y.one('.status-choice');
        Y.Assert.isFalse(status_choice.hasClass('hidden'));
    }
}));

tests.suite.add(new Y.Test.Case({
    name: 'helpers',

    test_output_loader_failure: function() {
        var output_node = Y.Node.create("<div></div>");
        var handlers = namespace._output_loader(output_node);
        handlers.on.failure('ignored');
        var output = output_node.get('children');
        Y.Assert.areEqual(1, output._nodes.length);
        Y.Assert.areEqual('STRONG', output.item(0).get('tagName'));
    },

    test_output_loader_success: function() {
        var output_node = Y.Node.create("<div>temporary</div>");
        var handlers = namespace._output_loader(output_node);
        var entry = new Y.lp.client.Entry();
        entry.set('error_output', 'testing<escaped>');
        handlers.on.success(entry);
        var output = output_node.get('children');
        Y.Assert.areEqual(1, output._nodes.length);
        var pre_node = output.item(0);
        Y.Assert.areEqual('PRE', pre_node.get('tagName'));
        Y.Assert.isTrue(pre_node.hasClass('wrap'));
        Y.Assert.areEqual('testing<escaped>', pre_node.get('text'));
    }
}));

}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'test-console', 'lp.client',
               'lp.translations.importqueue']
});
