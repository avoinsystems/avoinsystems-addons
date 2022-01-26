import datetime

from odoo.tests import common


class TestBankBarcode(common.TransactionCase):

    inputs = [
        ({
            # v5
            'iban': 'FI2350000110000238',
            'amount': 30.00,
            'payment_reference': 'RF123891798',
            'date': '2016-06-09',
        }, '523500001100002380000300012000000000000003891798160609'),
        ({
            # v4
            'iban': 'FI9657202320053451',
            'amount': 384.70,
            'payment_reference': '902296556534',
            'date': '2016-06-01',
        },'496572023200534510003847000000000000902296556534160601'),
        ({
            # Invalid iban. No FI
            'iban': '9657202320053451',
            'amount': 384.70,
            'payment_reference': '902296556534',
            'date': '2016-06-01',
        }, False),
        ({
            # Invalid iban. Too short
            'iban': 'FI965720232005345',
            'amount': 384.70,
            'payment_reference': '902296556534',
            'date': '2016-06-01',
        }, False),
        ({
            # Invalid iban. Only FI* allowed
            'iban': 'DE9657202320053451',
            'amount': 384.70,
            'payment_reference': '902296556534',
            'date': '2016-06-01',
        }, False),
        ({
            # payment_reference just long enough
            'iban': 'FI9657202320053452',
            'amount': 384.70,
            'payment_reference': '20981958478930298394',
            'date': '2016-06-01',
        },'496572023200534520003847000020981958478930298394160601'),
        ({
            # payment_reference just short enough
            'iban': 'FI9657202320053453',
            'amount': 384.70,
            'payment_reference': '6534',
            'date': '2016-06-01',
        },'496572023200534530003847000000000000000000006534160601'),
        ({
            # payment_reference too short
            'iban': 'FI9657202320053454',
            'amount': 384.70,
            'payment_reference': '90',
            'date': '2016-06-01',
        }, False),
        ({
            # payment_reference too long
            'iban': 'FI9657202320053455',
            'amount': 384.70,
            'payment_reference': '1092878509387829382910293',
            'date': '2016-06-01',
        }, False),
        ({
            # RF payment_reference just short enough
            'iban': 'FI2350000110000237',
            'amount': 30.00,
            'payment_reference': 'RF12389179829012211567802',
            'date': '2016-06-09',
        }, '523500001100002370000300012389179829012211567802160609'),
        ({
            # RF payment_reference just long enough
            'iban': 'FI2350000110000236',
            'amount': 30.00,
            'payment_reference': 'RF121798',
            'date': '2016-06-09',
        }, '523500001100002360000300012000000000000000001798160609'),
        ({
            # RF payment_reference too long
            'iban': 'FI2350000110000235',
            'amount': 30.00,
            'payment_reference': 'RF123891798290122115678202',
            'date': '2016-06-09',
        }, False),
        ({
            # RF payment_reference too short
            'iban': 'FI2350000110000234',
            'amount': 30.00,
            'payment_reference': 'RF12334',
            'date': '2016-06-09',
        }, False),
        ({
            # Rounding of amount
            'iban': 'FI2034499400115782',
            'amount': 2176.20,
            'payment_reference': '10084579',
            'date': '2018-02-23',
        }, '420344994001157820021762000000000000000010084579180223'),
    ]

    def setUp(self):
        super(TestBankBarcode, self).setUp()

        self.partner = self.env['res.partner'].create({
            'name': 'testpartner',
        })

    def _create_invoice(self, invoice_fields):
        acc = self.env['res.partner.bank'].create({
            'acc_number': invoice_fields['iban'],
            'bank_bic': 'TESTBANKBIC',
            'partner_id': self.partner.id,
        })

        inv = self.env['account.move'].with_context(test_bank_barcode=True).create({
            'move_type': 'in_invoice',
            'partner_bank_id': acc.id,
            'partner_id': self.partner.id,
            'payment_reference': invoice_fields['payment_reference'],
            'invoice_date_due': datetime.datetime.strptime(invoice_fields['date'], '%Y-%m-%d'),
        })

        line = self.env['account.move.line'].with_context(check_move_validity=False).create({
            'move_id': inv.id,
            'account_id':  self.partner.property_account_payable_id.id,
            'quantity': 1,
            'price_unit': invoice_fields['amount'],
            'name': "row"
        })

        return inv

    def test_barcode(self):
        assert self.partner
        barcode_len = 54
        for test_input, expected in self.inputs:
            result = self._create_invoice(test_input).bank_barcode
            self.assertEqual(result, expected,
                             'Invalid bank barcode. Expected: {}, got: {}'.format(expected, result))
            if result:
                self.assertEqual(len(result), barcode_len,
                                 'Invalid bank barcode length. Expected: {}, got: {}'.format(barcode_len, len(result)))
