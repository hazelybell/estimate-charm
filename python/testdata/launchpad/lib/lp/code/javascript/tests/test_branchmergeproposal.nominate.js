/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Tests for lp.code.branchmergeproposal.nominate.
 *
 */
YUI.add('lp.branchmergeproposal.test', function (Y) {

    var module = Y.lp.code.branchmergeproposal.nominate;

    var tests = Y.namespace('lp.branchmergeproposal.test');
    tests.suite = new Y.Test.Suite('BranchMergeProposal Nominate Tests');


    /*
     * Tests for when a reviewer is nominated for a mp and we check that they
     * can see the source and target branches.
     *
     */
    var TestMixin = {
        setUp: function() {
            this.fixture = Y.one('#fixture');
            var form = Y.Node.create(Y.one('#form-template').getContent());
            this.fixture.appendChild(form);
            this.mockio = new Y.lp.testing.mockio.MockIo();
            window.LP = {
                links: {me : "/~user"},
                cache: {
                    context: {
                        web_link: 'https://code.launchpad.dev/~someone/b2',
                        unique_name: 'b2'
                    }
                }
            };
            module.setup({io_provider: this.mockio});
        },

        tearDown: function() {
            if (this.fixture !== null) {
                this.fixture.empty();
            }
            delete this.fixture;
            delete this.mockio;
            delete window.LP;
        }
    };


    tests.suite.add(new Y.Test.Case(Y.merge(TestMixin, {
        name: 'branchmergeproposal-nominate-reviewer-picker-tests',

        // The module setup function works as expected.
        test_setup: function() {
            var validation_namespace =
                Y.namespace('lp.app.picker.validation');
            var widget_id = 'show-widget-field-reviewer';
            Y.Assert.areEqual(
                module.check_reviewer_can_see_branches,
                validation_namespace[widget_id]);
            var review_type = Y.DOM.byId('field.review_type');
            Y.Assert.isTrue(review_type.disabled);
        },

        // The review type field is correctly disabled if there is no reviewer.
        test_review_type_enable: function() {
            var reviewer = Y.one("[name='field.reviewer']");
            var review_type = Y.one("[name='field.review_type']");
            Y.Assert.isTrue(
                review_type.get('disabled'),
                'review type should be disabled');
            reviewer.set('value', 'someone');
            reviewer.simulate('blur');
            Y.Assert.isFalse(
                review_type.get('disabled'),
                'review type should be enabled');
            reviewer.set('value', '');
            reviewer.simulate('blur');
            Y.Assert.isTrue(
                review_type.get('disabled'),
                'review type should now be disabled');
        },

        // The check_reviewer function works as expected.
        test_check_reviewer_can_see_branches: function() {
            var orig_confirm_reviewer = module.confirm_reviewer;
            var dummy_picker = {};
            var dummy_save_fn = function() {};
            var confirm_reviewer_called = false;
            module.confirm_reviewer = function(
                branches_to_check, branch_info, picker, save_fn, cancel_fn) {
                Y.Assert.areEqual(dummy_picker, picker);
                Y.Assert.areEqual(dummy_save_fn, save_fn);
                Y.Assert.areEqual('Fred', branch_info.person_name);
                Y.Assert.areEqual('b2', branch_info.visible_branches[0]);
                Y.Assert.areEqual('b2', branches_to_check[0]);
                Y.Assert.areEqual('b1', branches_to_check[1]);
                confirm_reviewer_called = true;
            };
            var selected_value = {
                api_uri: '~fred'
            };
            Y.DOM.byId('field.target_branch.target_branch').value = 'b1';
            module.check_reviewer_can_see_branches(
                dummy_picker, selected_value, dummy_save_fn);
            this.mockio.success({
                responseText:
                    '{"person_name": "Fred", "visible_branches": ["b2"]}',
                responseHeaders: {'Content-Type': 'application/json'}});
            module.confirm_reviewer = orig_confirm_reviewer;
            // Check the parameters passed to the io call.
            Y.Assert.areEqual(
                '/api/devel/branches', this.mockio.last_request.url);
            var reviewer_uri = Y.lp.client.normalize_uri(
                selected_value.api_uri);
            reviewer_uri = encodeURIComponent(
                Y.lp.client.get_absolute_uri(reviewer_uri));
            Y.Assert.areEqual(
                'ws.op=getBranchVisibilityInfo&person=' +
                 reviewer_uri + '&branch_names=b2&branch_names=b1',
                this.mockio.last_request.config.data);
            Y.Assert.isTrue(confirm_reviewer_called);
        },

        // Invoke the validation callback with the specified visible branches.
        // The branches to check is always ['b1', 'b2'] and the person name is
        // always 'Fred'. We are checking the correct behaviour depending on what
        // visible branches are passed in.
        _invoke_confirm_reviewer: function(visible_branches) {
            var orig_yesyno = Y.lp.app.picker.yesno_save_confirmation;
            var dummy_picker = {};
            var yesno_called = false;
            Y.lp.app.picker.yesno_save_confirmation = function(
                    picker, content, yes_label, no_label, yes_fn, no_fn) {
                Y.Assert.areEqual('Nominate', yes_label);
                Y.Assert.areEqual('Choose Again', no_label);
                Y.Assert.areEqual(dummy_picker, picker);
                var message = Y.Node.create(content).get('text');
                Y.Assert.isTrue(message.indexOf('Fred') >= 0);
                var invisible_branches = ['b1', 'b2'].filter(function(i) {
                    return visible_branches.indexOf(i) < 0;
                });
                invisible_branches.forEach(function(branch_name) {
                    Y.Assert.isTrue(message.indexOf(branch_name) > 0);
                });
                yesno_called = true;
            };
            var branch_info = {
                person_name: 'Fred',
                visible_branches: visible_branches
            };
            var save_fn_called = false;
            var save_fn = function() {
                save_fn_called = true;
            };
            module.confirm_reviewer(
                ['b1', 'b2'], branch_info, dummy_picker, save_fn);
            Y.lp.app.picker.yesno_save_confirmation = orig_yesyno;
            return {
                save_called: save_fn_called,
                yesno_called: yesno_called
            };
        },

        // Test the validation callback with all branches being visible.
        test_confirm_reviewer_all_branches_visible: function() {
            var result = this._invoke_confirm_reviewer(['b1', 'b2']);
            Y.Assert.isTrue(result.save_called);
            Y.Assert.isFalse(result.yesno_called);
        },

        // Test the validation callback with no branches being visible.
        test_confirm_reviewer_no_branches_visible: function() {
            var result = this._invoke_confirm_reviewer([]);
            Y.Assert.isFalse(result.save_called);
            Y.Assert.isTrue(result.yesno_called);
        },

        // Test the validation callback with some branches being visible.
        test_confirm_reviewer_some_branches_visible: function() {
            var result = this._invoke_confirm_reviewer(['b1']);
            Y.Assert.isFalse(result.save_called);
            Y.Assert.isTrue(result.yesno_called);
        }
    })));


    tests.suite.add(new Y.Test.Case(Y.merge(TestMixin, {
        name: 'branchmergeproposal-nominate-propose-merge-tests',

        // Test that the Propose Merge submit button is re-wired to perform an XHR
        // call and that the correct data is passed and the expected callback is
        // invoked with the returned data.
        test_setup_nominate_submit: function() {
            var orig_confirm_reviewer_nomination
                = module.confirm_reviewer_nomination;
            var confirm_reviewer_nomination_called = false;
            module.confirm_reviewer_nomination = function(branch_info) {
                Y.Assert.areEqual('Fred', branch_info.person_name);
                confirm_reviewer_nomination_called = true;
            };

            module.setup_nominate_submit(this.mockio);
            Y.DOM.byId('field.target_branch.target_branch').value = 'b1';
            Y.DOM.byId('field.reviewer').value = 'mark';
            Y.DOM.byId('field.review_type').value = 'code';

            var submit_button = Y.one("[name='field.actions.register']");
            submit_button.simulate('click');
            Y.Assert.isNotNull(this.fixture.one('.spinner'));
            Y.Assert.areEqual(
                'https://code.launchpad.dev/~someone/b2/+register-merge',
                this.mockio.last_request.url);
            var form = Y.one("[name='launchpadform']");
            var self = this;
            form.all("[name^='field.']").each(function(field) {
                Y.Assert.areEqual(
                    field.get('value'),
                    self.mockio.last_request.config.form[field.get('name')]);
            });
            this.mockio.respond({
                status: 400,
                statusText: 'Branch Visibility',
                responseText: '{"person_name": "Fred"}',
                responseHeaders: {'Content-Type': 'application/json'}});
            Y.Assert.isTrue(confirm_reviewer_nomination_called);
            module.confirm_reviewer_nomination = orig_confirm_reviewer_nomination;
        },

        // Test the confirmation prompt when a mp is submitted and the reviewer
        // needs to be subscribed to the source and/or target branch.
        test_confirm_reviewer_nomination: function() {
            var branch_info = {
                branches_to_check: ['b1', 'b2'],
                visible_branches: ['b1'],
                person_name: 'Fred'
            };
            module.confirm_reviewer_nomination(branch_info);
            var confirmation_overlay_node
                = Y.one('.yui3-lp-app-confirmationoverlay-content');
            var confirmation_content_node
                = confirmation_overlay_node.one('p.large-warning');
            var confirmation_content = confirmation_content_node.get('text');
            Y.Assert.isTrue(
                confirmation_content.indexOf(
                    'Fred does not currently have permission to view branches:')
                    >= 0);
            var form_submitted = false;
            var form = Y.one("[name='launchpadform']");
            var orig_submit = form.submit;
            form.submit = function(e) {
                form_submitted = true;
            };
            var ok_button = Y.one('.yui3-lazr-formoverlay-actions .ok-btn');
            ok_button.simulate('click');
            Y.Assert.isTrue(form_submitted);
            form.submit = orig_submit;
        },

        // Test that when a mp is submitted without any confirmation prompt being
        // required, the response is used to redirect to the new page.
        test_merge_proposal_submission: function() {
            var orig_redirect = module._redirect;
            var redirect_called = false;
            module._redirect = function(url) {
                Y.Assert.areEqual('http://foo', url);
                redirect_called = true;
            };

            module.setup_nominate_submit(this.mockio);
            Y.DOM.byId('field.target_branch.target_branch').value = 'b1';
            Y.DOM.byId('field.reviewer').value = 'mark';
            Y.DOM.byId('field.review_type').value = 'code';

            var submit_button = Y.one("[name='field.actions.register']");
            submit_button.simulate('click');
            this.mockio.success({
                status: 201,
                responseHeaders: {'Location': 'http://foo'}});
            Y.Assert.isTrue(redirect_called);
            module._redirect = orig_redirect;
        }
    })));

}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'dump', 'test-console', 'node',
               'lp.testing.mockio', 'lp.mustache', 'event',
               'node-event-simulate',
               'lp.code.branchmergeproposal.nominate']
});
