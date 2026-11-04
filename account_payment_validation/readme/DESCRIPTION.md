This module adds a two-step approval of the payment of the vendor bills by
third-party approvers (users who are not accountants). The approval of the
vendor bill itself is done as usual: what is approved here is the payment, the
fact that the bill is ready to be paid.

- at the validation of a vendor bill, an approval request is sent by e-mail to
  the level 1 approver chosen on the bill; the request is also logged in the
  chatter of the bill;
- the level 1 approvers (members of the group *Payment Approval: Level 1
  Approvers*) can approve the first step with a dedicated button on the bill:
  the approval is then requested to the level 2 approver;
- the level 2 approvers (members of the group *Payment Approval: Level 2
  Approvers*) can approve the second step with a dedicated button: the bill is
  then approved for payment and can be paid.

The level 2 approver is mandatory to validate a vendor bill, the level 1
approver is optional: when it is not set, the approval is directly requested
to the level 2 approver.

The approval step is stored on the bill. It is displayed on the bill and in
the list views of the invoices and of the journal items, and in the *Status*
column of the invoices (the field *Status in Payment*).

The approval request can be sent again at any time with the button *Re-send
Approval Request*, which sends the request of the current step.

The approval doesn't block anything: it is a control done after the validation
of the vendor bill, before paying it.
