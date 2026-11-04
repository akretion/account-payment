# Copyright 2026 Akretion (https://www.akretion.com).
# @author Benoît Guillot <benoit.guillot@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression

LEVEL1_GROUP = "account_payment_validation.group_payment_validation_level1"
LEVEL2_GROUP = "account_payment_validation.group_payment_validation_level2"

STEP_LEVEL1 = "to_validate_level1"
STEP_LEVEL2 = "to_validate_level2"
STEP_VALIDATED = "validated"
PENDING_STEPS = (STEP_LEVEL1, STEP_LEVEL2)


class AccountMove(models.Model):
    _inherit = "account.move"

    status_in_payment = fields.Selection(
        selection_add=[
            (STEP_LEVEL1, "Waiting Payment Approval (Level 1)"),
            (STEP_LEVEL2, "Waiting Payment Approval (Level 2)"),
        ]
    )
    payment_validation_level1_user_id = fields.Many2one(
        "res.users",
        string="Level 1 Approver",
        compute="_compute_payment_validation_users_from_partner",
        store=True,
        readonly=False,
        precompute=True,
        domain=lambda self: [("groups_id", "in", self.env.ref(LEVEL1_GROUP).ids)],
        help="User of the group 'Payment Approval: Level 1 Approvers' who must "
        "approve the payment of this document (first step). This step is "
        "optional: when no level 1 approver is set, the payment approval is "
        "directly requested to the level 2 approver. It is defaulted from the "
        "partner of the document and can be changed here.",
    )
    payment_validation_level2_user_id = fields.Many2one(
        "res.users",
        string="Level 2 Approver",
        compute="_compute_payment_validation_users_from_partner",
        store=True,
        readonly=False,
        precompute=True,
        domain=lambda self: [("groups_id", "in", self.env.ref(LEVEL2_GROUP).ids)],
        help="User of the group 'Payment Approval: Level 2 Approvers' who must "
        "approve the payment of this document (second step). It is mandatory "
        "to approve the payment of a vendor bill. It is defaulted from the "
        "partner of the document and can be changed here.",
    )
    payment_validation_step = fields.Selection(
        [
            (STEP_LEVEL1, "Waiting Approval (Level 1)"),
            (STEP_LEVEL2, "Waiting Approval (Level 2)"),
            (STEP_VALIDATED, "Approved for Payment"),
        ],
        string="Payment Approval",
        readonly=True,
        copy=False,
        tracking=True,
        help="Step of the approval of the payment of this document by the "
        "approvers. It starts when the vendor bill is validated (posted).",
    )

    @api.depends("partner_id")
    def _compute_payment_validation_users_from_partner(self):
        """Default the approvers from the partner of the document.

        The values proposed by the partner are only defaults: they can be
        changed on each document, and changing the defaults of the partner does
        not change the documents already created.
        """
        empty_partner = self.env["res.partner"]
        for move in self:
            partner = move.partner_id.commercial_partner_id or empty_partner
            move.payment_validation_level1_user_id = (
                partner.payment_validation_level1_user_id
            )
            move.payment_validation_level2_user_id = (
                partner.payment_validation_level2_user_id
            )

    @api.constrains(
        "payment_validation_level1_user_id", "payment_validation_level2_user_id"
    )
    def _check_payment_validation_users(self):
        for move in self:
            for field_name, group_xmlid, group_label in (
                (
                    "payment_validation_level1_user_id",
                    LEVEL1_GROUP,
                    _("level 1 approvers"),
                ),
                (
                    "payment_validation_level2_user_id",
                    LEVEL2_GROUP,
                    _("level 2 approvers"),
                ),
            ):
                user = move[field_name]
                if user and self.env.ref(group_xmlid) not in user.groups_id:
                    raise ValidationError(
                        _(
                            "%(user)s is not a user of the group of the "
                            "%(group)s. Please select another user.",
                            user=user.display_name,
                            group=group_label,
                        )
                    )

    def _is_payment_validation_applicable(self):
        self.ensure_one()
        return self.move_type == "in_invoice"

    def _get_payment_validation_user(self, step):
        self.ensure_one()
        if step == STEP_LEVEL1:
            return self.payment_validation_level1_user_id
        if step == STEP_LEVEL2:
            return self.payment_validation_level2_user_id
        return self.env["res.users"]

    def _get_payment_validation_mail_template(self, step):
        xmlid = {
            STEP_LEVEL1: "payment_validation_level1_mail_template",
            STEP_LEVEL2: "payment_validation_level2_mail_template",
        }[step]
        return self.env.ref("account_payment_validation." + xmlid)

    def _write_payment_validation_step(self, step):
        """Write the validation step, even for a user without write access.

        The validators are not accountants: they must not get the write access
        on the accounting entries to be able to validate the document.
        """
        self.ensure_one()
        self.sudo().write({"payment_validation_step": step})

    def _send_payment_validation_mail(self, step=None):
        """Send the validation request e-mail to the validator of the step.

        The recipients are configured on the mail template.
        """
        self.ensure_one()
        step = step or self.payment_validation_step
        if step not in PENDING_STEPS:
            raise UserError(
                _(
                    "There is no payment approval request to send for %s.",
                    self.display_name,
                )
            )
        user = self._get_payment_validation_user(step)
        if not user:
            raise UserError(
                _(
                    "No approver is set for the step '%(step)s' of %(move)s.",
                    step=self._get_payment_validation_step_label(step),
                    move=self.display_name,
                )
            )
        self.message_post(
            body=_(
                "Payment approval request (%(step)s) sent by e-mail to %(user)s.",
                step=self._get_payment_validation_step_label(step),
                user=user.display_name,
            )
        )
        self._get_payment_validation_mail_template(step).send_mail(self.id)
        return True

    def _get_payment_validation_step_label(self, step):
        selection = dict(
            self._fields["payment_validation_step"]._description_selection(self.env)
        )
        return selection.get(step, step)

    def _start_payment_validation(self):
        """Start the approval of the payment of a just posted vendor bill."""
        self.ensure_one()
        if self.payment_validation_step:
            # the validation already started (the bill was posted again)
            return
        if self.payment_validation_level1_user_id:
            self._write_payment_validation_step(STEP_LEVEL1)
        else:
            self._write_payment_validation_step(STEP_LEVEL2)
        self._send_payment_validation_mail()

    def action_post(self):
        for move in self:
            if (
                move._is_payment_validation_applicable()
                and move.state == "draft"
                and not move.payment_validation_level2_user_id
            ):
                raise UserError(
                    _(
                        "The level 2 approver must be set on %s before "
                        "validating the bill.",
                        move.display_name,
                    )
                )
        res = super().action_post()
        for move in self:
            if move._is_payment_validation_applicable() and move.state == "posted":
                move._start_payment_validation()
        return res

    def button_draft(self):
        res = super().button_draft()
        for move in self:
            if move._is_payment_validation_applicable():
                move._write_payment_validation_step(False)
        return res

    def _check_payment_validation_user_group(self, group_xmlid):
        group = self.env.ref(group_xmlid)
        if group not in self.env.user.groups_id:
            raise UserError(
                _(
                    "Only the users of the group '%(group)s' can approve the "
                    "payment.",
                    group=group.display_name,
                )
            )

    def action_payment_validation_validate_level1(self):
        """Approve the payment (first step) and request the second one."""
        self._check_payment_validation_user_group(LEVEL1_GROUP)
        for move in self:
            if move.payment_validation_step != STEP_LEVEL1:
                raise UserError(
                    _(
                        "%s is not waiting for the approval of its payment by "
                        "a level 1 approver.",
                        move.display_name,
                    )
                )
            move._write_payment_validation_step(STEP_LEVEL2)
            move._send_payment_validation_mail(STEP_LEVEL2)
        return True

    def action_payment_validation_validate_level2(self):
        """Approve the payment (second step): the document is approved."""
        self._check_payment_validation_user_group(LEVEL2_GROUP)
        for move in self:
            if move.payment_validation_step != STEP_LEVEL2:
                raise UserError(
                    _(
                        "%s is not waiting for the approval of its payment by "
                        "a level 2 approver.",
                        move.display_name,
                    )
                )
            move._write_payment_validation_step(STEP_VALIDATED)
        return True

    def action_payment_validation_resend(self):
        """Send again the approval request e-mail of the current step."""
        for move in self:
            if move.payment_validation_step not in PENDING_STEPS:
                raise UserError(
                    _(
                        "There is no pending payment approval request on %s.",
                        move.display_name,
                    )
                )
            move._send_payment_validation_mail()
        return True

    @api.depends("payment_validation_step")
    def _compute_status_in_payment(self):
        res = super()._compute_status_in_payment()
        for move in self:
            if move.payment_validation_step in PENDING_STEPS:
                move.status_in_payment = move.payment_validation_step
        return res

    def _search_status_in_payment(self, operator, value):
        values = list(value) if isinstance(value, list | tuple | set) else [value]
        validation_values = [step for step in values if step in PENDING_STEPS]
        if not validation_values:
            return super()._search_status_in_payment(operator, value)
        negative = operator in ("!=", "not in")
        domain = [
            (
                "payment_validation_step",
                "not in" if negative else "in",
                validation_values,
            )
        ]
        other_values = [step for step in values if step not in PENDING_STEPS]
        if other_values:
            other_domain = super()._search_status_in_payment(
                operator, other_values if len(values) > 1 else other_values[0]
            )
            combine = expression.AND if negative else expression.OR
            domain = combine([domain, other_domain])
        return domain
