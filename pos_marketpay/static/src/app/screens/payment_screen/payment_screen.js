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
});
