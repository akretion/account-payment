# Copyright 2026 Akretion (https://www.akretion.com).
# @author Benoît Guillot <benoit.guillot@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

MOD = "account_payment_validation"
LEVEL1 = "to_validate_level1"
LEVEL2 = "to_validate_level2"
VALIDATED = "validated"


@tagged("post_install", "-at_install")
class TestPaymentValidation(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.level1_user = new_test_user(
            cls.env,
            login="validator-level1",
            name="Level 1 Validator",
            email="level1@example.com",
            groups=MOD + ".group_payment_validation_level1",
        )
        cls.level2_user = new_test_user(
            cls.env,
            login="validator-level2",
            name="Level 2 Validator",
            email="level2@example.com",
            groups=MOD + ".group_payment_validation_level2",
        )
        cls.no_group_user = new_test_user(
            cls.env,
            login="no-validation-group",
            name="No Validation Group",
            email="nobody@example.com",
            groups="account.group_account_invoice",
        )

    def _create_vendor_bill(self, level1=None, level2=None):
        bill = self.init_invoice(
            "in_invoice",
            partner=self.partner_a,
            invoice_date=fields.Date.context_today(self.env["account.move"]),
            post=False,
            products=self.product_a,
        )
        bill.write(
            {
                "payment_validation_level1_user_id": level1 and level1.id,
                "payment_validation_level2_user_id": level2 and level2.id,
            }
        )
        return bill

    def _new_vendor_bill(self, partner=None):
        """Create a vendor bill without touching its approvers."""
        return self.init_invoice(
            "in_invoice",
            partner=partner or self.partner_a,
            invoice_date=fields.Date.context_today(self.env["account.move"]),
            post=False,
            products=self.product_a,
        )

    def _mails(self, bill, user):
        return self.env["mail.mail"].search(
            [
                ("model", "=", "account.move"),
                ("res_id", "=", bill.id),
                ("recipient_ids", "in", user.partner_id.id),
            ]
        )

    def _chatter(self, bill):
        return " ".join(bill.message_ids.mapped(lambda m: m.body or ""))

    def test_level2_validator_is_mandatory(self):
        bill = self._create_vendor_bill(level1=self.level1_user)
        with self.assertRaises(UserError):
            bill.action_post()
        self.assertEqual(bill.state, "draft")
        self.assertFalse(bill.payment_validation_step)

        bill.payment_validation_level2_user_id = self.level2_user
        bill.action_post()
        self.assertEqual(bill.state, "posted")

    def test_post_with_level1_starts_with_level1(self):
        bill = self._create_vendor_bill(self.level1_user, self.level2_user)

        bill.action_post()

        self.assertEqual(bill.payment_validation_step, LEVEL1)
        # the status of the bill shows the pending validation
        self.assertEqual(bill.status_in_payment, LEVEL1)
        # the request is sent by e-mail to the level 1 validator
        mails = self._mails(bill, self.level1_user)
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails.recipient_ids, self.level1_user.partner_id)
        # the request is also logged on the bill
        self.assertIn("Payment approval request", self._chatter(bill))
        self.assertIn(self.level1_user.display_name, self._chatter(bill))

    def test_post_without_level1_starts_with_level2(self):
        bill = self._create_vendor_bill(level2=self.level2_user)

        bill.action_post()

        self.assertEqual(bill.payment_validation_step, LEVEL2)
        self.assertEqual(bill.status_in_payment, LEVEL2)
        mails = self._mails(bill, self.level2_user)
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails.recipient_ids, self.level2_user.partner_id)

    def test_level1_validation_requests_level2(self):
        bill = self._create_vendor_bill(self.level1_user, self.level2_user)
        bill.action_post()

        # the level 1 validator is not an accountant: he can validate the bill
        bill.with_user(self.level1_user).action_payment_validation_validate_level1()

        self.assertEqual(bill.payment_validation_step, LEVEL2)
        self.assertEqual(bill.status_in_payment, LEVEL2)
        mails = self._mails(bill, self.level2_user)
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails.recipient_ids, self.level2_user.partner_id)

    def test_level2_validation_ends_the_validation(self):
        bill = self._create_vendor_bill(self.level1_user, self.level2_user)
        bill.action_post()
        bill.with_user(self.level1_user).action_payment_validation_validate_level1()

        bill.with_user(self.level2_user).action_payment_validation_validate_level2()

        self.assertEqual(bill.payment_validation_step, VALIDATED)
        # the status of the bill is back on its payment status
        self.assertEqual(bill.status_in_payment, bill.payment_state)

    def test_validator_must_belong_to_the_group(self):
        bill = self._create_vendor_bill(level2=self.level2_user)
        with self.assertRaises(ValidationError):
            bill.payment_validation_level1_user_id = self.no_group_user
        with self.assertRaises(ValidationError):
            bill.payment_validation_level2_user_id = self.level1_user

    def test_validator_field_domain(self):
        bill = self._create_vendor_bill()
        fields_info = bill.fields_get(
            ["payment_validation_level1_user_id", "payment_validation_level2_user_id"]
        )
        level1_domain = str(fields_info["payment_validation_level1_user_id"]["domain"])
        level2_domain = str(fields_info["payment_validation_level2_user_id"]["domain"])
        level1_group = self.env.ref(MOD + ".group_payment_validation_level1")
        level2_group = self.env.ref(MOD + ".group_payment_validation_level2")
        # only the users of the right group can be selected
        self.assertIn("groups_id", level1_domain)
        self.assertIn(str(level1_group.id), level1_domain)
        self.assertIn(str(level2_group.id), level2_domain)

    def test_resend_request(self):
        bill = self._create_vendor_bill(self.level1_user, self.level2_user)
        bill.action_post()
        self.assertEqual(len(self._mails(bill, self.level1_user)), 1)

        bill.action_payment_validation_resend()

        self.assertEqual(len(self._mails(bill, self.level1_user)), 2)
        # nothing to re-send once the validation is finished
        bill.with_user(self.level1_user).action_payment_validation_validate_level1()
        bill.with_user(self.level2_user).action_payment_validation_validate_level2()
        with self.assertRaises(UserError):
            bill.action_payment_validation_resend()

    def test_validation_button_of_the_wrong_step(self):
        bill = self._create_vendor_bill(self.level1_user, self.level2_user)
        bill.action_post()
        # the level 2 validator cannot validate the document before the
        # validation of the level 1 validator
        with self.assertRaises(UserError):
            bill.with_user(self.level2_user).action_payment_validation_validate_level2()

    def test_reset_to_draft_clears_the_validation(self):
        bill = self._create_vendor_bill(self.level1_user, self.level2_user)
        bill.action_post()

        bill.button_draft()

        self.assertFalse(bill.payment_validation_step)
        self.assertEqual(bill.status_in_payment, "draft")

    def test_journal_item_shows_the_validation_step(self):
        bill = self._create_vendor_bill(self.level1_user, self.level2_user)
        bill.action_post()

        self.assertEqual(set(bill.line_ids.mapped("payment_validation_step")), {LEVEL1})
        # the journal items list is readable by the validators
        self.assertEqual(
            bill.line_ids.with_user(self.level1_user).mapped("payment_validation_step"),
            [LEVEL1] * len(bill.line_ids),
        )

    def test_validator_can_read_the_bill(self):
        bill = self._create_vendor_bill(self.level1_user, self.level2_user)
        bill.action_post()

        data = bill.with_user(self.level1_user).read(["name", "amount_total", "ref"])[0]
        self.assertEqual(data["name"], bill.name)
        # the level 2 validator cannot validate the level 1 step
        with self.assertRaises(UserError):
            bill.with_user(self.level2_user).action_payment_validation_validate_level1()

    def test_bill_gets_the_default_validators_of_the_vendor(self):
        """The approvers of a new vendor bill are the defaults of the vendor."""
        self.partner_a.write(
            {
                "payment_validation_level1_user_id": self.level1_user.id,
                "payment_validation_level2_user_id": self.level2_user.id,
            }
        )

        bill = self._new_vendor_bill()

        self.assertEqual(bill.payment_validation_level1_user_id, self.level1_user)
        self.assertEqual(bill.payment_validation_level2_user_id, self.level2_user)
        # the level 2 approver is set: the bill can be validated
        bill.action_post()
        self.assertEqual(bill.payment_validation_step, LEVEL1)

    def test_bill_gets_the_default_validators_of_the_vendor_company(self):
        """The defaults are read on the commercial partner of the vendor contact."""
        vendor = self.env["res.partner"].create(
            {
                "name": "Vendor Company",
                "is_company": True,
                "payment_validation_level2_user_id": self.level2_user.id,
            }
        )
        contact = self.env["res.partner"].create(
            {
                "name": "Vendor Contact",
                "parent_id": vendor.id,
                "type": "invoice",
            }
        )

        bill = self._new_vendor_bill(contact)

        self.assertEqual(bill.payment_validation_level2_user_id, self.level2_user)
        self.assertFalse(bill.payment_validation_level1_user_id)

    def test_default_validators_can_be_changed_on_the_bill(self):
        self.partner_a.payment_validation_level2_user_id = self.level2_user
        other_level2_user = new_test_user(
            self.env,
            login="validator-level2-other",
            name="Other Level 2 Validator",
            groups=MOD + ".group_payment_validation_level2",
        )

        bill = self._new_vendor_bill()
        self.assertEqual(bill.payment_validation_level2_user_id, self.level2_user)

        bill.payment_validation_level2_user_id = other_level2_user

        self.assertEqual(bill.payment_validation_level2_user_id, other_level2_user)
        # the default of the vendor is not changed
        self.assertEqual(
            self.partner_a.payment_validation_level2_user_id, self.level2_user
        )

    def test_default_validators_follow_the_vendor_of_the_bill(self):
        self.partner_b.payment_validation_level1_user_id = self.level1_user
        bill = self._new_vendor_bill()
        self.assertFalse(bill.payment_validation_level1_user_id)

        bill.partner_id = self.partner_b

        self.assertEqual(bill.payment_validation_level1_user_id, self.level1_user)

    def test_default_change_on_the_vendor_does_not_change_existing_bills(self):
        bill = self._new_vendor_bill()
        self.assertFalse(bill.payment_validation_level2_user_id)

        self.partner_a.payment_validation_level2_user_id = self.level2_user

        self.assertFalse(bill.payment_validation_level2_user_id)
        # a bill created afterwards gets the new defaults
        self.assertEqual(
            self._new_vendor_bill().payment_validation_level2_user_id,
            self.level2_user,
        )

    def test_default_validator_field_domain(self):
        fields_info = self.env["res.partner"].fields_get(
            ["payment_validation_level1_user_id", "payment_validation_level2_user_id"]
        )
        level1_group = self.env.ref(MOD + ".group_payment_validation_level1")
        level2_group = self.env.ref(MOD + ".group_payment_validation_level2")
        # only the users of the right group can be set as default
        self.assertIn(
            str(level1_group.id),
            str(fields_info["payment_validation_level1_user_id"]["domain"]),
        )
        self.assertIn(
            str(level2_group.id),
            str(fields_info["payment_validation_level2_user_id"]["domain"]),
        )
