import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.data.connectWebSocket("MARKETPAY_LATEST_RESPONSE", (payload) => {
            const pendingLine = this.getPendingPaymentLine("marketpay");

            if (odoo.debug) {
                console.info("[MarketPay] websocket MARKETPAY_LATEST_RESPONSE received", {
                    ts: new Date().toISOString(),
                    payload,
                    pending_line_uuid: pendingLine && pendingLine.uuid,
                    pending_line_status: pendingLine && pendingLine.getPaymentStatus && pendingLine.getPaymentStatus(),
                });
            }

            if (pendingLine) {
                pendingLine.payment_method_id.payment_terminal.handleMarketpayStatusResponse();
            } else if (odoo.debug) {
                console.info("[MarketPay] websocket fired but no pending Market Pay line was found", {
                    ts: new Date().toISOString(),
                    payload,
                });
            }
        });
    },
});
