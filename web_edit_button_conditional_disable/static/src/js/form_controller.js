/* Copyright 2016 Camptocamp SA
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

odoo.define("web_access_rule_buttons.main", function (require) {
    "use strict";
    var FormController = require("web.FormController");
    FormController.include({
        async _update(state, params) {
            await this._super(state, params);
            if ('should_disable_form_edit' in state.data) {
                this.show_hide_edit_button(state.data.should_disable_form_edit);
            }
        },
        show_hide_edit_button: function (edit_disabled) {
            if (this.$buttons) {
                var button = this.$buttons.find(".o_form_button_edit");
                this.activeActions.edit = !edit_disabled
                if (button) {
                    button.prop("disabled", edit_disabled);
                }
            }
        },
        _onQuickEdit: function (ev) {
            // Disable quick edit from doing anything if editing is disabled
            if (this.activeActions.edit) {
                this._super.apply(this, arguments)
            } else {
                ev.stopPropagation();
            }
        },
        _enableButtons: function () {
            // Deactivate the edit button when _enableButtons is called.
            // When a dialog is opened and then closed,
            // for example when a button has a confirmation prompt on it,
            // the buttons get disabled and then re-enabled, which enables the
            // edit button without triggering `_update`. Without this,
            // triggering a dialog and then closing it would enable the use
            // of the Edit-button when it shouldn't.
            this._super.apply(this, arguments);
            this.show_hide_edit_button(!this.activeActions.edit);
        },

    });
});
