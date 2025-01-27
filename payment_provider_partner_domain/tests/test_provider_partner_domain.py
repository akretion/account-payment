# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html


from odoo.tests.common import TransactionCase


class TestProviderPartnerDomain(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_allowed = cls.env["res.partner"].create({"name": "Partner allowed"})
        cls.partner_not_allowed = cls.env["res.partner"].create({"name": "Partner not allowed"})
        cls.provider = cls.env.ref("payment.payment_provider_demo")
        partner_filter = cls.env["ir.filters"].create(
            {
                "name": "Partner allowed",
                "model_id": "res.partner",
                "domain": [("id", "=", cls.partner_allowed.id)]
            }
        )
        cls.provider.partner_filter_id = partner_filter.id
        cls.provider.state = "test"

    def test_partner_domain(self):
        providers = self.env["payment.provider"]._get_compatible_providers(
            self.env.company.id, self.partner_allowed.id, 10
        )
        self.assertIn(self.provider.id, providers.ids)
        providers = self.env["payment.provider"]._get_compatible_providers(
            self.env.company.id, self.partner_not_allowed.id, 10
        )
        self.assertNotIn(self.provider.id, providers.ids)
