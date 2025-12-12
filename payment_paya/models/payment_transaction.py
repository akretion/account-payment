# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import pprint

import dicttoxml
import xmltodict
from lxml import etree

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.payment import utils as payment_utils

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model
    def _compute_reference(self, provider_code, prefix=None, separator="-", **kwargs):
        """Override of payment to ensure that PAYA requirements for references are satisfied.

        PAYA requirements for references are as follows:
        - References must be unique at provider level for a given merchant account.
          This is satisfied by singularizing the prefix with the current datetime.
          If two transactions are created simultaneously, `_compute_reference` ensures
          the uniqueness of references by suffixing a sequence number.

        :param str provider_code: The code of the provider handling the transaction
        :param str prefix: The custom prefix used to compute the full reference
        :param str separator: The custom separator used to separate the prefix from the suffix
        :return: The unique reference for the transaction
        :rtype: str
        """
        if provider_code != "paya":
            return super()._compute_reference(provider_code, prefix=prefix, **kwargs)

        if not prefix:
            # If no prefix is provided, it could mean that a module has passed a kwarg
            # intended for the `_compute_reference_prefix` method, as it is only called
            # if the prefix is empty.
            # We call it manually here because singularizing the prefix would generate a default
            # value if it was empty, hence preventing the method from ever being called and the
            # transaction from received a reference named after the related document.
            prefix = (
                self.sudo()._compute_reference_prefix(
                    provider_code, separator, **kwargs
                )
                or None
            )
        prefix = payment_utils.singularize_reference_prefix(
            prefix=prefix, max_length=40
        )
        reference = super()._compute_reference(provider_code, prefix=prefix, **kwargs)
        if self._context.get("refund_move_id", False):
            refund_move = self.env["account.move"].browse(
                self._context.get("refund_move_id")
            )
            reference = refund_move.name
        return reference

    def _get_specific_rendering_values(self, processing_values):
        """Override of payment to return PAYA-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values
                                       of the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != "paya":
            return res

        rendering_values = {
            "SupplierID": self.provider_id.paya_userid,
            "RequestType": "PAY",  # to perform authorisation and settlement at the same time
            "Reference": self.reference,
            "TransactionType": "MSAL" or "MREF",  # for any sale or any refunds
            "Amount": int(self.amount),
            "CurrencyCode": self.currency_id.name,
            "CountryCode": self.partner_country_id.code_alpha3 or "",
        }
        if self.tokenize:
            rendering_values.update(
                {
                    "AliasName": payment_utils.singularize_reference_prefix(
                        prefix="ODOO-ALIAS"
                    ),
                    "ALIASUSAGE": _(
                        "Storing your payment details is necessary for future use."
                    ),
                }
            )
        rendering_values.update(
            {
                "api_url": self.provider_id.paya_api_url,
            }
        )
        return rendering_values

    def _get_paya_payment_request_data(self):
        invoice_ref = ""
        invoice = self.env["account.move"].browse()
        if self.env.context.get(
            "active_model"
        ) == "account.move" and self.env.context.get("active_id"):
            invoice = self.env["account.move"].browse(self.env.context.get("active_id"))
            if invoice.payment_reference:
                invoice_ref = invoice.payment_reference[0:20]
        data = {
            "PaymentGatewayRequest": {
                "Header": {
                    "SupplierID": self.provider_id.paya_userid,
                    "Password": self.provider_id.paya_password,
                    "RequestType": "PAY",  # authorisation and settlement at the same time
                },
                "Body": {
                    "Request": {
                        "Reference": self.reference,
                        "TransactionType": "MSAL",  # for any sale from the cardholder
                        "Amount": payment_utils.to_minor_currency_units(
                            self.amount, None, 2
                        ),
                        "CurrencyCode": self.currency_id.name,
                        "CountryCode": self.partner_country_id.code_alpha3 or "",
                        "CardDetails": {
                            "AliasName": self.token_id.provider_ref,
                        },
                        "Addendum": {
                            "PCard": {
                                "LID": {
                                    "AMEXCPC": {
                                        "CustomerReference1": invoice_ref,
                                        "InvoiceReferenceNumber": invoice.name or "",
                                    },
                                    "Details": {
                                        "OrderDate": invoice.invoice_date.strftime(
                                            "%y%m%d"
                                        )
                                        or "",
                                        "InvoiceReferenceNumber": invoice.name or "",
                                        "SupplierOrderReference": invoice.name or "",
                                        "GrossAmount": invoice.amount_total or 0.0,
                                        "VATAmount": invoice.amount_tax or 0.0,
                                        "LineCount": len(
                                            invoice.invoice_line_ids.filtered(
                                                lambda line: line.product_id
                                            )
                                        )
                                        or 0,
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
        return self._get_paya_item_request_data(data, invoice)

    def _send_payment_request(self):
        """Override of payment to send a payment request to PAYA.

        Note: self.ensure_one()

        :return: None
        :raise: UserError if the transaction is not linked to a token
        """
        tx = super()._send_payment_request()
        if (
            self.env.context.get("active_model", False) != "account.move"
            or self.provider_id.code != "paya"
        ):
            return tx

        if not self.token_id:
            raise UserError(_("PAYA: The transaction is not linked to a token."))

        # Make the payment request
        data = self._get_paya_payment_request_data()

        payload = self._dict_to_xml(data)

        _logger.info(
            "payment request response for transaction with reference %s:\n%s",
            self.reference,
            pprint.pformat({k: v for k, v in data.items() if k != "Password"}),
        )  # Log the payment request data without the password
        response_content = self.provider_id._paya_make_request(payload)
        response = xmltodict.parse(response_content)

        # Handle the feedback data
        _logger.info(
            "payment request response (as an etree) for transaction with reference %s:\n%s",
            self.reference,
            response,
        )
        feedback_data = {
            "Reference": response["PaymentGatewayResponse"]["Body"]["PayResponse"].get(
                "Reference"
            ),
            "tree": response,
        }
        _logger.info(
            "handling feedback data from PAYA for transaction with reference %s with"
            " data:\n%s",
            self.reference,
            pprint.pformat(feedback_data),
        )
        self._handle_notification_data("paya", feedback_data)

    def _get_paya_refund_request_data(self, invoice, refund_move, amount_to_refund):
        refund_move_ref = ""
        if refund_move.payment_reference:
            refund_move_ref = refund_move.payment_reference[0:20]
        data = {
            "PaymentGatewayRequest": {
                "Header": {
                    "SupplierID": self.provider_id.paya_userid,
                    "Password": self.provider_id.paya_password,
                    "RequestType": "PAY",  # authorisation and settlement at the same time
                },
                "Body": {
                    "Request": {
                        "Reference": self.reference,
                        "TransactionType": "MREF",  # for any refunds back to the cardholder
                        "Amount": payment_utils.to_minor_currency_units(
                            amount_to_refund, None, 2
                        ),
                        "CurrencyCode": self.currency_id.name,
                        "CountryCode": self.partner_country_id.code_alpha3 or "",
                        "CardDetails": {
                            "AliasName": self.token_id.provider_ref,
                        },
                        "Addendum": {
                            "PCard": {
                                "LID": {
                                    "AMEXCPC": {
                                        "CustomerReference1": refund_move_ref
                                        or invoice.payment_reference
                                        or "",
                                        "OriginalInvoiceNumber": invoice.name or "",
                                        "InvoiceReferenceNumber": refund_move.name
                                        or "",
                                    },
                                    "Details": {
                                        "OrderDate": refund_move.invoice_date.strftime(
                                            "%y%m%d"
                                        )
                                        or "",
                                        "OriginalInvoiceNumber": invoice.name or "",
                                        "InvoiceReferenceNumber": refund_move.name
                                        or "",
                                        "SupplierOrderReference": refund_move.name,
                                        "GrossAmount": refund_move.amount_total or 0.0,
                                        "VATAmount": refund_move.amount_tax or 0.0,
                                        "LineCount": len(
                                            refund_move.invoice_line_ids.filtered(
                                                lambda line: line.product_id
                                            )
                                        )
                                        or 0,
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
        return self._get_paya_item_request_data(data, refund_move)

    def _send_refund_request(self, amount_to_refund=None):
        """Override of payment to send a refund request to PAYA.

        Note: self.ensure_one()

        :param float amount_to_refund: The amount to refund.
        :return: The refund transaction created to process the refund request.
        :rtype: recordset of `payment.transaction`
        """
        self = self.with_context(refund=True)
        provider_is_paya = self._check_provider_is_paya()
        refund_tx = super()._send_refund_request(amount_to_refund=amount_to_refund)
        if not provider_is_paya or len(self.payment_id.reconciled_invoice_ids) != 1:
            return refund_tx

        if self.payment_id.state != "posted":
            raise ValidationError(_("Only accounted payment can be refunded."))

        invoice = self.payment_id.reconciled_invoice_ids[0]
        default_values_list = [
            {
                "ref": _("Reversal of: %s", invoice.name),
                "invoice_origin": invoice.name,
                "payment_token_id": refund_tx.token_id.id,
            }
        ]
        refund_move = invoice._reverse_moves(
            default_values_list=default_values_list, cancel=False
        )
        refund_move.action_post()
        self = self.with_context(refund_move_id=refund_move.id)
        refund_tx.reference = refund_move.name

        if not self.token_id:
            raise UserError(_("PAYA: The transaction is not linked to a token."))

        # Make the refund request to paya.
        invoice = self.payment_id.reconciled_invoice_ids[0]
        data = self._get_paya_refund_request_data(
            invoice=invoice, refund_move=refund_move, amount_to_refund=amount_to_refund
        )

        payload = self._dict_to_xml(data)

        _logger.info(
            "refund request response for transaction with reference %s:\n%s",
            self.reference,
            pprint.pformat({k: v for k, v in data.items() if k != "Password"}),
        )  # Log the refund request data without the password
        response_content = self.provider_id._paya_make_request(payload)
        response = xmltodict.parse(response_content)

        # Handle the feedback data
        _logger.info(
            "refund request response (as an etree) for transaction with reference %s:\n%s",
            self.reference,
            response,
        )
        feedback_data = {
            "Reference": response["PaymentGatewayResponse"]["Body"]["PayResponse"].get(
                "Reference"
            ),
            "tree": response,
        }
        _logger.info(
            "handling feedback data from PAYA for transaction with reference %s with"
            " data:\n%s",
            self.reference,
            pprint.pformat(feedback_data),
        )
        refund_tx._handle_notification_data("paya", feedback_data)

        return refund_tx

    def _check_provider_is_paya(self):
        provider_is_paya = True
        if self.provider_id.code != "paya":
            provider_is_paya = False
        return provider_is_paya

    def _get_paya_item_request_data(self, data, invoice):
        data_line = {}
        idx = 1
        for line in invoice.invoice_line_ids.filtered(lambda line: line.product_id):
            vat_rate = 0.00
            AMEXTaxCategory = ""
            if line.tax_ids:
                vat_rate = round(line.tax_ids[0].amount, 2)
            if vat_rate == 0.00:
                AMEXTaxCategory = "Z"
            data_line = {
                "Quantity": round(line.quantity, 2),
                "UnitCost": round(line.price_unit, 2),
                "VATRate": vat_rate,
                "LineTotal": line.price_subtotal,
                "Description": line.name[:40],
                "UnitOfMeasure": line.product_uom_id.name,
                "AMEXTaxCategory": AMEXTaxCategory,
            }
            data["PaymentGatewayRequest"]["Body"]["Request"]["Addendum"]["PCard"][
                "LID"
            ]["Line" + str(idx)] = data_line
            idx += 1
        return data

    def _dict_to_xml(self, data):
        xml_data = dicttoxml.dicttoxml(
            data, root=False, attr_type=False, encoding="UTF-8"
        )
        tree = etree.XML(xml_data)
        for el in tree.xpath("//LID"):
            for child in el.iterchildren():
                if child.tag[:4] == "Line":
                    child.tag = "Line"
        xml_data = etree.tostring(tree)
        return xml_data

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Override of payment to find the transaction based on PAYA data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if the data match no transaction
        """
        tx = super()._get_tx_from_notification_data(
            provider_code=provider_code, notification_data=notification_data
        )
        if self.provider_id.code != "paya" or len(tx) == 1:
            return tx

        reference = notification_data["PaymentGatewayResponse"]["Body"][
            "PayResponse"
        ].get("Reference")
        tx = self.search(
            [("reference", "=", reference), ("provider_code", "=", "paya")]
        )

        if not tx:
            raise ValidationError(
                _("PAYA: No transaction found matching reference %s.", reference)
            )
        return tx

    def _process_notification_data(self, notification_data):
        """Override of payment to process the transaction based on PAYA data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        """
        res = super()._process_notification_data(notification_data)
        if self.provider_id.code != "paya":
            return res

        if "tree" in notification_data:
            notification_data = notification_data["tree"]

        self.provider_reference = notification_data["PaymentGatewayResponse"]["Body"][
            "PayResponse"
        ].get("Reference", None)
        auth_result_code = notification_data["PaymentGatewayResponse"]["Body"][
            "PayResponse"
        ].get("AuthResultCode", None)
        auth_result_description = notification_data["PaymentGatewayResponse"]["Body"][
            "PayResponse"
        ].get("AuthResultDescription", None)
        settlement_result_code = notification_data["PaymentGatewayResponse"]["Body"][
            "PayResponse"
        ].get("SettlementResultCode", None)
        auth_code = notification_data["PaymentGatewayResponse"]["Body"][
            "PayResponse"
        ].get("AuthCode", None)
        status_code = notification_data["PaymentGatewayResponse"]["Header"][
            "STATUS"
        ].get("CODE", None)
        status_severity = notification_data["PaymentGatewayResponse"]["Header"][
            "STATUS"
        ].get("SEVERITY", None)
        status_description = notification_data["PaymentGatewayResponse"]["Header"][
            "STATUS"
        ].get("Description", None)
        state_message = None
        reason = ""
        if (
            status_code == "0"
            and auth_result_code in ["1001", "1002", "1004"]
            and settlement_result_code == "0"
        ):
            if auth_code:
                state_message = _(
                    "PAYA: The payment has been accepted. "
                    "AMEX authorization code: %(auth_code)s.",
                    auth_code=auth_code,
                )
            self._set_done(state_message=state_message)
            # Immediately post-process the transaction if it is a refund
            if self.operation == "refund":
                self.env.ref("payment.cron_post_process_payment_tx")._trigger()
        elif auth_result_code == "1007" and settlement_result_code != "0":
            if status_code != "0":
                reason += status_severity + ": " + status_description + " "
            if auth_result_description:
                reason += auth_result_description
            else:
                reason = "Unknown reason"
            _logger.info("the payment has been declined: %s.", reason)
            self._set_error(
                "PAYA: "
                + _(
                    "The payment has been declined. Settlement Result Code: "
                    "%(settlement_result_code)s - Description: %(reason)s",
                    settlement_result_code=settlement_result_code,
                    reason=reason,
                )
            )

    def _create_payment(self, **extra_create_values):
        payment = super()._create_payment(**extra_create_values)
        if self.provider_id.code == "paya" and self.amount < 0:
            payment_method_line = (
                self.provider_id.journal_id.outbound_payment_method_line_ids.filtered(
                    lambda l: l.code == self.provider_code
                )
            )
            if payment_method_line:
                payment.payment_method_line_id = payment_method_line.id
            # reconcile reverse move with refund payment
            invoice = payment.source_payment_id.reconciled_invoice_ids[0]
            refund_move = invoice.reversal_move_id[0]
            refund_move.write(
                {
                    "payment_reference": payment.ref,
                }
            )
            (payment.line_ids + refund_move.line_ids).filtered(
                lambda line: line.account_id == payment.destination_account_id
                and not line.reconciled
            ).reconcile()
        return payment
