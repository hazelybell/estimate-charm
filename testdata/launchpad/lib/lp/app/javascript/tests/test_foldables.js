/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.app.foldables.test', function (Y) {

    var test_foldables = Y.namespace('lp.app.foldables.test');
    var suite = new Y.Test.Suite('Foldable Tests');

    var quote_comment = ['<p>Mister X wrote:<br />',
        '<span class="foldable-quoted">',
        '&gt; This is a quoted line<br />',
        '&gt; This is a quoted line<br />',
        '&gt; This is a quoted line<br />',
        '&gt; This is a quoted line<br />',
        '&gt; This is a quoted line<br />',
        '&gt; This is a quoted line<br />',
        '&gt; This is a quoted line<br />',
        '&gt; This is a quoted line<br />',
        '&gt; This is a quoted line<br />',
        '&gt; This is a quoted line<br />',
        '&gt; This is a quoted line<br />',
        '</span>',
        'This is a reply to the line above.<br />',
        'This is a continuation line.</p>'].join('');

    var longer_comment = [
        '<p>Attribution line<br />',
        '<span class="foldable-quoted">',
        '&gt; First line in the first paragraph.<br />',
        '&gt; Second line in the first paragraph.<br />',
        '&gt; First line in the second paragraph.<br />',
        '&gt; Second line in the second paragraph.<br />',
        '&gt; First line in the third paragraph.<br />',
        '&gt; First line in the third paragraph.<br />',
        '&gt; First line in the third paragraph.<br />',
        '&gt; First line in the third paragraph.<br />',
        '&gt; First line in the third paragraph.<br />',
        '&gt; First line in the third paragraph.<br />',
        '&gt; First line in the third paragraph.<br />',
        '&gt; First line in the third paragraph.<br />',
        '&gt; First line in the third paragraph.<br />',
        '</span></p>'
    ];

    var foldable_comment = [
        '<p><span class="foldable" style="display: none; "><br>',
        '-----BEGIN PGP SIGNED MESSAGE-----<br>',
        'Hash: SHA1',
        '</span></p>'
    ].join('');

    suite.add(new Y.Test.Case({

        name: 'foldable_tests',

        _add_comment: function (comment) {
            var cnode = Y.Node.create('<div/>');
            cnode.set('innerHTML', comment);
            Y.one('#target').appendChild(cnode);
        },

        tearDown: function () {
            Y.one('#target').setContent('');
        },

        test_namespace_exists: function () {
            Y.Assert.isObject(Y.lp.app.foldables,
                'Foldable should be found');
        },

        test_inserts_ellipsis: function () {
            this._add_comment(longer_comment);
            Y.lp.app.foldables.activate();
            Y.Assert.isObject(Y.one('a'));
            Y.Assert.areSame('[...]', Y.one('a').getContent());
        },

        test_hides_quote: function () {
            this._add_comment(longer_comment);
            Y.lp.app.foldables.activate();
            var quote = Y.one('.foldable-quoted');
            Y.Assert.areSame(quote.getStyle('display'), 'none');
        },

        test_doesnt_hide_short: function () {
            this._add_comment(quote_comment);
            Y.lp.app.foldables.activate();
            Y.Assert.isNull(Y.one('a'));
            var quote = Y.one('.foldable-quoted');
            // this one should be visible since it's only 12 lines
            Y.Assert.areSame(quote.getStyle('display'), 'inline');
        },

        test_clicking_link_shows: function () {
            this._add_comment(longer_comment);
            Y.lp.app.foldables.activate();

            var quote = Y.one('.foldable-quoted');
            // it should be hidden to start since it's 13 lines long
            Y.Assert.areSame(quote.getStyle('display'), 'none');

            var link = Y.one('a');
            link.simulate('click');
            var quote = Y.one('.foldable-quoted');
            Y.Assert.areSame(quote.getStyle('display'), 'inline');

            // Make sure that if clicked again it hides.
            link.simulate('click');
            Y.Assert.areSame(quote.getStyle('display'), 'none');
        },

        test_foldable: function () {
            this._add_comment(foldable_comment);
            Y.lp.app.foldables.activate();
            var link = Y.one('a');
            link.simulate('click');

            var quote = Y.one('.foldable');
            Y.Assert.areSame(quote.getStyle('display'), 'inline');

            // Make sure that if clicked again it hides.
            link.simulate('click');
            Y.Assert.areSame(quote.getStyle('display'), 'none');
        }
    }));

    test_foldables.suite = suite;

}, '0.1', {
    requires: ['test', 'node-event-simulate', 'node', 'lp.app.foldables']
});
