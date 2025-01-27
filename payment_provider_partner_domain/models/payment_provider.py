from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.const import REPORT_REASONS_MAPPING


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    partner_filter_domain = fields.Text(
        string="Partner Filter Domain", related="partner_filter_id.domain"
    )
    partner_filter_id = fields.Many2one(
        "ir.filters",
    )

    @api.model
    def _get_compatible_providers(self, company_id, partner_id, *args, report=None, **kwargs):
        providers = super()._get_compatible_providers(
            company_id, partner_id, *args, report=report, **kwargs
        )
        partner = self.env["res.partner"].browse(partner_id)
        new_providers = self.env["payment.provider"]
        for provider in providers:
            if provider.partner_filter_id:
                if partner.filtered_domain(safe_eval(provider.partner_filter_id.domain)):
                    new_providers |= provider
            else:
                new_providers |= provider
        __import__('pdb').set_trace()
        payment_utils.add_to_report(
            report,
            providers - new_providers,
            available=False,
        )
        return new_providers
