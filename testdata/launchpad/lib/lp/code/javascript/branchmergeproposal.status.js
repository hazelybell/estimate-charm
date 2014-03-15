/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Code for handling the update of the branch merge proposals.
 *
 * @module lp.code.branchmergeproposal
 * @requires node, lp.ui.choiceedit, lp.client.plugins
 */

YUI.add('lp.code.branchmergeproposal.status', function(Y) {

var namespace = Y.namespace('lp.code.branchmergeproposal.status');

/*
 * Connect the branch status to the javascript events.
 */
namespace.connect_status = function(conf) {

    var status_content = Y.one('#branchmergeproposal-status-value');

    if (conf.user_can_edit_status) {
        var status_choice_edit = new Y.ChoiceSource({
            contentBox: status_content,
            value: conf.status_value,
            title: 'Change status to',
            items: conf.status_widget_items});
        status_choice_edit.showError = function(err) {
            Y.lp.app.errors.display_error(null, err);
        };
        status_choice_edit.on('save', function(e) {
            config = {
                on: {
                    success: function(entry) {
                        var cb = status_choice_edit.get('contentBox');
                        Y.Array.each(conf.status_widget_items, function(item) {
                                if (item.value == status_choice_edit.get('value')) {
                                    cb.one('a').addClass(item.css_class);
                                } else {
                                    cb.one('a').removeClass(item.css_class);
                                }
                            });
                        update_summary();
                    },
                    end: function() {
                        status_content.one('img').set('src', '/@@/edit');
                    }
                },
                parameters: {
                    status: status_choice_edit.get('value'),
                    revid: conf.source_revid
                }
            };
            status_content.one('img').set('src', '/@@/spinner');
            lp_client = new Y.lp.client.Launchpad();
            lp_client.named_post(
                LP.cache.context.self_link, 'setStatus', config);

        });
        status_choice_edit.render();
    }
};

/*
 * Update the summary table for the merge proposal.
 *
 * An async request is made for the summary table, and the content is
 * inspected. We don't modify the status row as it is in the process of having
 * animations run on it.  Each of the table rows has an id that is strictly
 * alphabetical.  This ordering is used to determine if a row needs to be
 * added or removed to the table shown on the current page.  If the row
 * appears in both, the content is checked (except for diffs as that'll never
 * be the same due to the javascript added classes) and if it differs the
 * shown rows are updated.
 */
function update_summary() {
    var existing_summary = Y.one('#proposal-summary tbody');
    SUMMARY_SNIPPET = '+pagelet-summary';
    Y.io(SUMMARY_SNIPPET, {
            on: {
                success: function(id, response) {
                    var new_summary = Y.Node.create(response.responseText);
                    var new_rows = new_summary.all('tr');
                    var old_rows = existing_summary.all('tr');
                    // Skip over the status row (row 0).
                    var new_pos = 1;
                    var old_pos = 1;
                    var new_size = new_rows.size();
                    var old_size = old_rows.size();

                    while (new_pos < new_size && old_pos < old_size) {
                        var new_row = new_rows.item(new_pos);
                        var old_row = old_rows.item(old_pos);
                        var new_id = new_row.get('id');
                        var old_id = old_row.get('id');
                        if (new_id == old_id) {
                            if (new_id != 'summary-row-b-diff') {
                                // Don't mess with the diff.
                                if (new_row.get('innerHTML') !=
                                    old_row.get('innerHTML')) {
                                    existing_summary.insertBefore(new_row, old_row);
                                    old_row.remove();
                                }
                            }
                            ++new_pos;
                            ++old_pos;
                        } else if (new_id < old_id) {
                            ++new_pos;
                            existing_summary.insertBefore(new_row, old_row);
                        } else {
                            ++old_pos;
                            old_row.remove();
                        }
                    }
                    // Remove all left over old rows, and add all left over new rows.
                    while (old_pos < old_size) {
                        var old_row = old_rows.item(old_pos);
                        ++old_pos;
                        old_row.remove();
                    }
                    while (new_pos < new_size) {
                        var new_row = new_rows.item(new_pos);
                        ++new_pos;
                        if (new_row.get('id') != 'summary-row-b-diff') {
                            existing_summary.append(new_row);
                        }
                    }
                }
            }});
}

  }, "0.1", {"requires": ["io", "node", "lp.ui.choiceedit", "lp.client",
                          "lp.client.plugins"]});
