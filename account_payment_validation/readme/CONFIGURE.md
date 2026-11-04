To configure this module, you need to:

- add the users who must approve the payment of the vendor bills to the group
  *Payment Approval: Level 1 Approvers* and/or *Payment Approval: Level 2
  Approvers* (menu *Settings > Users & Companies > Users*, the groups are in
  the *Accounting* section),
- set the *Default Level 1 Approver* and/or the *Default Level 2 Approver* on
  the vendor form (tab *Invoicing*, section *Payment Approval*): they are then
  used on the vendor bills of that vendor, where they can still be changed
  bill by bill,
- check the recipients of the mail templates *Payment Approval: Level 1
  Request* and *Payment Approval: Level 2 Request* (menu *Settings >
  Technical > E-mail > Templates*): they default to the approver chosen on the
  bill, through their *Partner To* field.

The e-mails are queued by Odoo: they are sent by the scheduled action *Mail:
Email Queue Manager*.
