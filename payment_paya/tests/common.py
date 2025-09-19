# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo.addons.payment.tests.common import PaymentCommon


class PAYACommon(PaymentCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.paya = cls._prepare_provider(
            "paya",
            update_values={
                "paya_userid": "dummy",
                "paya_password": "dummy",
            },
        )

        cls.provider = cls.paya
        cls.currency = cls.currency_euro

        cls.notification_data = {
            "Amount": "1111.11",
            "CARDNO": "XXXXXXXXXXXX1111",
            "CN": "Dummy Customer Name",
            "currency": "USD",
            "IP": "101.00.111.22",
            "SEVERITY": "0",
            "Reference": cls.reference,
            "PAYID": "01234567899",
            "PM": "CreditCard",
            "Code": "0",  # 'Payment requested' (done)
            "TRXDATE": "01/31/22",
        }
