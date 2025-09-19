# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import pprint
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PAYAController(http.Controller):
    _return_url = "/payment/paya/return"
    _backward_compatibility_urls = [
        "/payment/paya/accept",
        "/payment/paya/test/accept",
        "/payment/paya/decline",
        "/payment/paya/test/decline",
        "/payment/paya/exception",
        "/payment/paya/test/exception",
        "/payment/paya/cancel",
        "/payment/paya/test/cancel",
        "/payment/paya/validate/accept",
        "/payment/paya/validate/decline",
        "/payment/paya/validate/exception",
    ]  # Facilitates the migration of users who registered the URLs in PAYA's backend
    # prior to 14.3

    @http.route(
        [_return_url] + _backward_compatibility_urls,
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )  # Redirect are made with GET requests only.
    # Webhook notifications can be set to GET or POST.
    def paya_return_from_checkout(self, **raw_data):
        """Process the notification data sent by PAYA after redirection from checkout.

        This route can also accept S2S notifications from PAYA if it is configured
        as a webhook in PAYA's backend.
        The user can choose between GET or POST for the webhook notifications.

        :param dict raw_data: The un-formatted notification data
        """
        _logger.info(
            "handling redirection from PAYA with data:\n%s", pprint.pformat(raw_data)
        )
        data = self._normalize_data_keys(raw_data)

        # Check the integrity of the notification
        tx_sudo = (
            request.env["payment.transaction"]
            .sudo()
            ._get_tx_from_notification_data("paya", data)
        )

        # Handle the notification data
        tx_sudo._handle_notification_data("paya", data)
        return request.redirect("/payment/status")

    @staticmethod
    def _normalize_data_keys(data):
        """Set all keys of a dictionary to upper-case.

        The keys received from PAYA APIs have inconsistent formatting and
        must be homogenized to allow re-using the same methods.
        We reformat them to follow a unified nomenclature inspired
        by PAYA API.

        Formatting steps:
        1) Uppercase key strings: 'Something' -> 'SOMETHING', 'something' -> 'SOMETHING'
        2) Remove the prefix: 'CARD.SOMETHING' -> 'SOMETHING', 'ALIAS.SOMETHING' -> 'SOMETHING'

        :param dict data: The data whose keys to normalize
        :return: The normalized data
        :rtype: dict
        """
        return {re.sub(r".*\.", "", k.upper()): v for k, v in data.items()}
