/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { BackButton } from "@point_of_sale/app/navbar/back_button/back_button";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";

patch(BackButton.prototype, {
    // Shown on small screens, including the payment screen, where the desktop
    // Back button in PaymentScreenTop is not rendered.
    async onClick() {
        if (this.pos.mainScreen.component === TicketScreen) {
            return super.onClick(...arguments);
        }
        const handled = await this.pos.marketpayLeavePaymentScreen(() => {
            this.pos.mobile_pane = "right";
            this.pos.showScreen("ProductScreen");
        });
        if (!handled) {
            return super.onClick(...arguments);
        }
    },
});
