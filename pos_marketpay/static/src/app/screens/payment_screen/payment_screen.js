import { _t } from "@web/core/l10n/translation";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            const pendingPaymentLine = this.currentOrder.payment_ids.find(
                (paymentLine) =>
                    paymentLine.payment_method_id.use_payment_terminal === "marketpay" &&
                    !paymentLine.isDone() &&
                    paymentLine.getPaymentStatus() !== "pending"
            );
            if (pendingPaymentLine) {
                if (odoo.debug) {
                    console.info("[MarketPay] PaymentScreen mount detected stuck Market Pay line, forcing 'force_done'", {
                        ts: new Date().toISOString(),
                        line_uuid: pendingPaymentLine.uuid,
                        previous_status: pendingPaymentLine.getPaymentStatus(),
                        order_uuid: this.currentOrder && this.currentOrder.uuid,
                    });
                }
                pendingPaymentLine.setPaymentStatus("force_done");
            }
        });
    },

    // Core treats every non-true abort as a failed cancel and sets the line
    // back to waitingCard. A false result means the card was approved, so that
    // overwrite drops the payment and the order is saved unpaid.
    async sendPaymentCancel(line) {
        if (line.payment_method_id.use_payment_terminal !== "marketpay") {
            return super.sendPaymentCancel(...arguments);
        }
        line.setPaymentStatus("waitingCancel");
        const outcome = await line.payment_method_id.payment_terminal.sendPaymentCancel(
            this.currentOrder,
            line.uuid
        );
        if (outcome === false || line.isDone()) {
            this.notification.add(
                _t("Payment completed — the cancellation came too late."),
                { type: "warning" }
            );
            return;
        }
        if (outcome) {
            line.setPaymentStatus("retry");
            this.pos.paymentTerminalInProgress = false;
            return;
        }
        if (!line.isDone()) {
            line.setPaymentStatus("waitingCard");
        }
    },
});
