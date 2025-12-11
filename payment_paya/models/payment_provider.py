# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# from hashlib import new as hashnew


_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("paya", "PAYA")], ondelete={"paya": "set default"}
    )
    paya_userid = fields.Char(
        string="API User ID",
        help="The ID solely used to identify the API user with PAYA",
        required_if_provider="paya",
    )
    paya_password = fields.Char(
        string="API User Password",
        required_if_provider="paya",
        groups="base.group_system",
    )
    paya_api_url = fields.Char(
        string="API Url",
        required_if_provider="paya",
    )

    # === COMPUTE METHODS ===#

    def _compute_feature_support_fields(self):
        """Override of `payment` to enable additional features."""
        res = super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "paya").update(
            {
                "support_manual_capture": True,
                "support_tokenization": True,
                "support_refund": "partial",
            }
        )
        return res

    # === BUSINESS METHODS ===#

    @api.model
    def _get_compatible_providers(self, *args, is_validation=False, **kwargs):
        """Override of payment to unlist PAYA providers for validation operations."""
        providers = super()._get_compatible_providers(
            *args, is_validation=is_validation, **kwargs
        )

        if is_validation:
            providers = providers.filtered(lambda p: p.code != "paya")

        return providers

    def _paya_get_api_url(self, api_key):
        """Return the appropriate URL of the requested API for the provider state.

        Note: self.ensure_one()

        :param str api_key: The API whose URL to get: 'hosted_payment_page'
        :return: The API URL
        :rtype: str
        """
        self.ensure_one()
        api_urls = {"hosted_payment_page": self.paya_api_url}
        return api_urls.get(api_key)

    def _paya_make_request(self, payload=None, method="POST"):
        """Make a request to one of PAYA APIs.

        Note: self.ensure_one()

        :param dict payload: The payload of the request
        :param str method: The HTTPS method of the request
        :return The content of the response
        :rtype: bytes
        :raise: ValidationError if an HTTPS error occurs
        """
        self.ensure_one()

        url = self._paya_get_api_url("hosted_payment_page")
        try:
            response = self._paya_request(url, payload, timeout=60)
            response.raise_for_status()
            _logger.info("send request to PAYA with api url '%s'", url)
        except requests.exceptions.ConnectionError as e:
            _logger.exception("unable to reach endpoint at %s", url)
            raise ValidationError(
                _("PAYA: Could not establish the connection to the API.")
            ) from e
        except requests.exceptions.HTTPError as e:
            _logger.exception("invalid API request at %s with data %s", url, payload)
            raise ValidationError(
                _("PAYA: The communication with the API failed.")
            ) from e
        return response.content

    def _paya_request(self, url, payload, timeout):
        return requests.post(url, data=payload, timeout=timeout)
