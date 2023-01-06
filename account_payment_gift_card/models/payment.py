# Copyright (C) 2022 Akretion (<http://www.akretion.com>).
# @author Kévin Roche <kevin.roche@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PaymentAcquirerGiftCard(models.Model):
    _inherit = "payment.acquirer"

    provider = fields.Selection(
        selection_add=[("gift_card", "Gift Card")],
        ondelete={"gift_card": "set default"},
    )


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    gift_card_line_id = fields.One2many(
        comodel_name="gift.card.line",
        inverse_name="transaction_id",
        string="Gift Card Uses",
    )

    def _set_transaction_cancel(self):
        super()._set_transaction_cancel()
        for record in self:
            if record.state == "cancel":
                record.gift_card_line_id.unlink()
