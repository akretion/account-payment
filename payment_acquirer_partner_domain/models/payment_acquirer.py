from odoo import fields, models
from odoo.tools.safe_eval import safe_eval


class PaymentAcquirer(models.Model):
    _inherit = "payment.acquirer"

    partner_filter_domain = fields.Text(
        string="Partner Filter Domain", related="partner_filter_id.domain"
    )
    partner_filter_id = fields.Many2one(
        "ir.filters",
    )

    def _get_available_payment_input(self, partner=None, company=None):
        result = super()._get_available_payment_input(partner=partner, company=company)
        new_acquirers = self.env["payment.acquirer"]
        for acquirer in result["acquirers"]:
            if partner and acquirer.partner_filter_id:
                if partner.filtered_domain(safe_eval(acquirer.partner_filter_id.domain)):
                    new_acquirers |= acquirer
            else:
                new_acquirers |= acquirer
        return {
            "acquirers": new_acquirers,
            "pms": self.env["payment.token"].search(
                [
                    ("partner_id", "=", partner.id),
                    ("acquirer_id", "in", new_acquirers.ids),
                ]
            ),
        }
