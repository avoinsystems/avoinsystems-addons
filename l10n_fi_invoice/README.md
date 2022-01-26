# Finnish Invoice

Make Odoo invoices look like these: https://www.isolta.fi/ilmainen-excel-laskupohja/

### How to print "Finnish Invoice"?

"Finnish Invoice" can be printed by opening an invoice and clicking on "Finnish Invoice" under the "Print" dropdown.

### How to set up "Finnish Invoice" as the default invoice when using "Send & Print"?

Normally when you send an invoice via email, you are shown a preview where you can edit the body of the message, 
and it also shows the PDF it is about to send as an attachment.

This module does not automatically replace the PDF: rather you have to set it yourself. Either by replacing it 
per-message (useful if you only need it for some invoices) or by changing it on the template's settings
 (useful if you always want this PDF).
 
If you want to change the setting on the template, Odoo should allow you to open the template for editing when you are 
in the process of sending the invoice. If it doesn't, you can also go to Settings -> Technical 
_[You need to be in developer mode for this]_ -> Email -> Templates. There you should be able to find the 
"Invoice: Send by email" template. Choose "Finnish Invoice" instead of "Invoices" for "Optional report to print and attach" 
field value and that should make it so the Finnish version is sent instead of the usual one.
