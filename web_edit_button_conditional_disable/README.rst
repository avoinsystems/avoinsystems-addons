===================================
Web Edit Button Conditional Disable
===================================

This module introduces a mechanism for disabling editing on a form view based on
a field on the record.


Usage
=====

This module only implements the form view mechanism for disabling editing, but does not introduce
any conditions to any models. Other modules that depend on this one can define a boolean field
`should_disable_form_edit` on any model, which will then used to determine if the form view's edit
should be disabled.
To have an effect, the field must be present on the form view.

When the field's value is `true` on the form view, the edit button will be disabled, as well
as quick editing.


Credits
=======

This module is based on Odoo Community Association's (OCA's)
`web_access_rule_buttons <https://github.com/OCA/web/tree/14.0/web_access_rule_buttons>`_ -module.


Authors
~~~~~~~

* Camptocamp (web_access_rule_buttons)
* Onestein (web_access_rule_buttons)
* Avoin.Systems

Contributors
~~~~~~~~~~~~

* Guewen Baconnier <guewen.baconnier@camptocamp.com>
* Antonio Esposito <a.esposito@onestein.nl>
* Dhara Solanki <dhara.solanki@initos.com>
* Santeri Valjakka <santeri.valjakka@avoin.systems>

