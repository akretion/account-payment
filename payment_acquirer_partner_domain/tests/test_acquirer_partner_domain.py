# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html


from odoo.tests.common import SavepointCase


class TestPaymentReturn(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_allowed = cls.env["res.partner"].create({"name": "Partner allowed"})
        cls.partner_not_allowed = cls.env["res.partner"].create({"name": "Partner not allowed"})
        cls.acquirer = cls.env.ref("payment.payment_acquirer_transfer")
        partner_filter = cls.env["ir.filters"].create(
            {
                "name": "Partner allowed",
                "model_id": "res.partner",
                "domain": [("id", "=", cls.partner_allowed.id)]
            }
        )
        cls.acquirer.partner_filter_id = partner_filter.id

    def test_partner_domain(self):
        acquirers = self.env["payment.acquirer"]._get_available_payment_input(partner=self.partner_allowed)
        self.assertIn(self.acquirer.id, acquirers["acquirers"].ids)
        acquirers = self.env["payment.acquirer"]._get_available_payment_input(partner=self.partner_not_allowed)
        self.assertNotIn(self.acquirer.id, acquirers["acquirers"].ids)
