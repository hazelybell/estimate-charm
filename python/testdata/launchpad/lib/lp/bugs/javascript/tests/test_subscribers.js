YUI.add('lp.bugs.subscribers.test', function (Y) {

    var tests = Y.namespace('lp.bugs.subscribers.test');
    var module = Y.lp.bugs.subscribers;

    tests.suite = new Y.Test.Suite('bug subscribers Tests');
    tests.suite.add(new Y.Test.Case({
        name: 'BugSubscribersList constructor test',

        setUp: function() {
            this.root = Y.Node.create('<div />');
            Y.one('body').appendChild(this.root);
            window.LP = {
                cache: {
                    context:  {
                        bug_link: '/bug/1',
                        web_link: '/base'
                    }
                }
            };
        },

        tearDown: function() {
            this.root.remove();
            delete window.LP;
        },

        setUpLoader: function() {
            this.root.appendChild(
                Y.Node.create('<div />').addClass('container'));
            return new module.createBugSubscribersLoader({
                container_box: '.container',
                subscribers_details_view: '/+bug-portlet-subscribers-details'});
        },

        test_subscribers_list_instantiation: function() {
            this.setUpLoader();
        },

        test_addSubscriber: function() {
            // Check that the subscription list has been created with the expected
            // subscription levels for bugs. This can be done by adding a
            // subscriber to one of the expected levels and checking the results.
            var loader = this.setUpLoader(this.root);
            var node = loader.subscribers_list.addSubscriber(
                { name: 'user' }, 'Lifecycle');

            // Node is constructed using _createSubscriberNode.
            Y.Assert.isTrue(node.hasClass('subscriber'));
            // And the ID is set inside addSubscriber() method.
            Y.Assert.areEqual('subscriber-user', node.get('id'));

            // And it nested in the subscribers-list of a 'Level3' section.
            var list_node = node.ancestor('.subscribers-list');
            Y.Assert.isNotNull(list_node);
            var section_node = list_node.ancestor(
                '.subscribers-section-lifecycle');
            Y.Assert.isNotNull(section_node);
        }
    }));

}, '0.1', {
    requires: [ 'lp.testing.runner', 'test', 'test-console', 'node',
                'lp.ui.picker-base', 'lp.bugs.subscribers', 'event',
                'node-event-simulate', 'dump' ]
});
