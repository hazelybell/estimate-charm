YUI.add('lp.lp_links.test', function (Y) {
    var tests = Y.namespace('lp.lp_links.test');

    var links = Y.lp.app.links;
    tests.suite = new Y.Test.Suite("lp.app.links Tests");
    var mock_io = new Y.lp.testing.mockio.MockIo();

    tests.suite.add(new Y.Test.Case({
        name: 'test_bugs_branches',

        setUp: function() {
            links.check_valid_lp_links(mock_io);
            var response = {
                "bug_links": {
                    "valid": {
                        "/bugs/14": [
                            "jokosher exposes personal details ",
                            "in its actions portlet"].join('')},
                    "invalid": {
                        "/bugs/200": "Bug 200 cannot be found"}},
                "branch_links": {
                    "invalid": {
                        "/+branch/invalid":
                            "No such product: 'invalid'."}}};
            mock_io.success({
                responseText: Y.JSON.stringify(response),
                responseHeaders: {'Content-type': 'application/json'}
            });
        },

        test_bugs_branches: function () {
            var validbug = Y.one('#valid-bug');
            var invalidbug = Y.one('#invalid-bug');
            var validbranch = Y.one('#valid-branch');
            var invalidbranch = Y.one('#invalid-branch');
            Y.Assert.isTrue(validbug.hasClass('bug-link'));
            Y.Assert.isTrue(invalidbug.hasClass('invalid-link'));
            Y.Assert.areSame(
                'jokosher exposes personal details in its actions portlet',
                validbug.get('title')
            );
            Y.Assert.isTrue(validbranch.hasClass('branch-short-link'));
            Y.Assert.isTrue(invalidbranch.hasClass('invalid-link'));
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'test_bugs',

        setUp: function() {
            links.check_valid_lp_links(mock_io);
            var response = {
                "bug_links": {
                    "valid": {
                        "/bugs/14": [
                            "jokosher exposes personal details ",
                            "in its actions portlet"].join('')},
                    "invalid": {
                        "/bugs/200": "Bug 200 cannot be found"}}};
            mock_io.success({
                responseText: Y.JSON.stringify(response),
                responseHeaders: {'Content-type': 'application/json'}
            });
        },

        test_bugs: function () {
            var validbug = Y.one('#valid-bug');
            var invalidbug = Y.one('#invalid-bug');
            Y.Assert.isTrue(validbug.hasClass('bug-link'));
            Y.Assert.isTrue(invalidbug.hasClass('invalid-link'));
            Y.Assert.areSame(
                'jokosher exposes personal details in its actions portlet',
                validbug.get('title')
            );
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'test_bugs',

        setUp: function() {
            links.check_valid_lp_links(mock_io);
            var response = {
                "branch_links": {
                    "invalid": {
                        "/+branch/invalid":
                            "No such product: 'invalid'."}}};
            mock_io.success({
                responseText: Y.JSON.stringify(response),
                responseHeaders: {'Content-type': 'application/json'}
            });
        },

        test_branch: function () {
            var validbranch = Y.one('#valid-branch');
            var invalidbranch = Y.one('#invalid-branch');
            Y.Assert.isTrue(validbranch.hasClass('branch-short-link'));
            Y.Assert.isTrue(invalidbranch.hasClass('invalid-link'));
        }
    }));

}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'test-console',
               'lp.app.links', 'lp.testing.mockio', 'lp.client',
               'node']
});
