/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            const pendingPaymentLine = this.currentOrder.paymentlines.find(
                (paymentLine) =>
                    paymentLine.payment_method.use_payment_terminal === "marketpay" &&
                    !paymentLine.is_done() &&
                    paymentLine.get_payment_status() !== "pending"
            );
            if (pendingPaymentLine) {
                pendingPaymentLine.set_payment_status("force_done");
            }
        });
    },

    async onClickBack() {
        const handled = await this.pos.marketpayLeavePaymentScreen(() => {
            this.pos.showScreen("ProductScreen");
        });
        if (!handled) {
            this.pos.showScreen("ProductScreen");
        }
    },

    // The line's Cancel button reads send_payment_cancel as a boolean. A
    // completed payment resolves that call to false; do not then overwrite
    // the "done" status with waitingCard.
    async sendPaymentCancel(line) {
        if (line.payment_method.use_payment_terminal !== "marketpay") {
            return super.sendPaymentCancel(...arguments);
        }
        const paymentTerminal = line.payment_method.payment_terminal;
        line.set_payment_status("waitingCancel");
        try {
            const isCancelSuccessful = await paymentTerminal.send_payment_cancel(
                this.currentOrder,
                line.cid
            );
            if (line.is_done()) {
                return;
            }
            line.set_payment_status(isCancelSuccessful ? "retry" : "waitingCard");
        } catch {
            if (!line.is_done()) {
                line.set_payment_status("waitingCard");
            }
        }
    },

    // Deleting a busy line also aborts. Only drop the line when the abort
    // actually cancelled it; a late approval or a timeout must leave it in place.
    deletePaymentLine(cid) {
        const line = this.paymentLines.find((paymentLine) => paymentLine.cid === cid);
        const busy = ["waiting", "waitingCard", "timeout"].includes(line.get_payment_status());
        if (line.payment_method.use_payment_terminal !== "marketpay" || !busy) {
            return super.deletePaymentLine(...arguments);
        }
        line.set_payment_status("waitingCancel");
        line.payment_method.payment_terminal
            .send_payment_cancel(this.currentOrder, cid)
            .then((cancelled) => {
                if (line.is_done() || line.order.finalized) {
                    return;
                }
                if (cancelled) {
                    this.currentOrder.remove_paymentline(line);
                    this.numberBuffer.reset();
                } else {
                    line.set_payment_status("waitingCard");
                }
            })
            .catch(() => {
                if (!line.is_done()) {
                    line.set_payment_status("waitingCard");
                }
            });
    },
});
