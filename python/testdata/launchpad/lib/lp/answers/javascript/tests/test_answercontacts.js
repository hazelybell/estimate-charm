YUI.add('lp.answercontacts.test', function (Y) {

var module = Y.lp.answers.answercontacts;

var tests = Y.namespace('lp.answercontacts.test');
tests.suite = new Y.Test.Suite('Answer Contacts Tests');


tests.suite.add(new Y.Test.Case({
    name: 'QuestionAnswerContactsList constructor test',

    setUp: function() {
        this.root = Y.Node.create('<div />');
        Y.one('body').appendChild(this.root);
        window.LP = {
            links: {},
            cache: {
                context: { web_link: "/~web_link", self_link: "/~link" },
                another_context_answer_portlet_url_data:
                    { web_link: "/~another_web_link",
                        self_link: "/~another_link" }}
        };
    },

    tearDown: function() {
        this.root.remove();
        delete window.LP;
    },

    setUpLoader: function() {
        this.root.appendChild(
            Y.Node.create('<div />').addClass('container'));
        return new module.createQuestionAnswerContactsLoader({
            container_box: '.container'});
    },

    test_contacts_list_instantiation: function() {
        var loader = this.setUpLoader();
        Y.Assert.areEqual('/~web_link/+portlet-answercontacts-details',
            loader.subscribers_portlet_uri);
    },

    test_url_data_override: function() {
        // Check that we can override the default context used to provide the
        // web_link and self_link urls.
        this.root.appendChild(
            Y.Node.create('<div />').addClass('container'));
        var loader = new module.createQuestionAnswerContactsLoader({
            container_box: '.container',
            context_name: 'another_context'});
        Y.Assert.areEqual(
            '/~another_web_link/+portlet-answercontacts-details',
            loader.subscribers_portlet_uri);
    },

    test_addContact: function() {
        // Check that the contact list has been created and can accept
        // new contacts. Answer contacts do not use subscription levels so
        // pass in '' and check this works as expected.
        var loader = this.setUpLoader(this.root);
        var node = loader.subscribers_list.addSubscriber(
            { name: 'user' }, '');

        // Node is constructed using _createSubscriberNode.
        Y.Assert.isTrue(node.hasClass('subscriber'));
        // And the ID is set inside addSubscriber() method.
        Y.Assert.areEqual('subscriber-user', node.get('id'));

        // And it nested in the subscribers-list of a 'Direct' section.
        var list_node = node.ancestor('.subscribers-list');
        Y.Assert.isNotNull(list_node);
        var section_node = list_node.ancestor(
            '.subscribers-section-default');
        Y.Assert.isNotNull(section_node);
    }
}));

}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'test-console', 'node',
               'lp.ui.picker-base', 'lp.answers.answercontacts',
               'event', 'node-event-simulate', 'dump']
});
