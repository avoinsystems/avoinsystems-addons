# -*- coding: utf-8 -*-
##############################################################################
#
#    Author: Avoin.Systems
#    Copyright 2015 Avoin.Systems
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models


# NOTE: This class _should be_ in a more general l10n_fi module. Since there is
# no such module yet, I'll just leave this here.
class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Change default address format if country isn't specified.
    # Note, this method doesn't have to be overridden after this PR has
    # been accepted: https://github.com/odoo/odoo/pull/8577
    def _display_address(self, cr, uid, address, without_company=False, context=None):

        """
        The purpose of this function is to build and return an address
        formatted accordingly to the standards of the country where it belongs.

        :param address: browse record of the res.partner to format
        :returns: the address formatted in a display that fit its country
                  habits (or the default ones if not country is specified)
        :rtype: string
        """

        # get the information that will be injected into the display format
        # get the address format
        address_format = address.country_id.address_format \
            or self._get_default_address_format()
        args = {
            'state_code': address.state_id.code or '',
            'state_name': address.state_id.name or '',
            'country_code': address.country_id.code or '',
            'country_name': address.country_id.name or '',
            'company_name': address.parent_name or '',
        }
        for field in self._address_fields(cr, uid, context=context):
            args[field] = getattr(address, field) or ''
        if without_company:
            args['company_name'] = ''
        elif address.parent_id:
            address_format = '%(company_name)s\n' + address_format
        return address_format % args

    # noinspection PyMethodMayBeStatic
    def _get_default_address_format(self):
        return "%(street)s\n%(street2)s\n%(zip)s %(city)s"
