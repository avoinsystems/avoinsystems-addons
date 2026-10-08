import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";

// Payment statuses in which a Market Pay transaction is actively running on the
// terminal and must be aborted before leaving the payment screen.
const MARKETPAY_BUSY_STATUSES = ["waiting", "waitingCard", "timeout"];

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

    // Returns the current order's Market Pay payment line that is actively
    // running on the terminal (if any).
    getBusyMarketpayPaymentLine() {
        const order = this.getOrder();
        if (!order) {
            return false;
        }
        return order.payment_ids.find(
            (line) =>
                line.payment_method_id.use_payment_terminal === "marketpay" &&
                !line.isDone() &&
                MARKETPAY_BUSY_STATUSES.includes(line.getPaymentStatus())
        );
    },

    // The PaymentScreen "Back" button calls pos.onClickBackButton(). When a
    // Market Pay transaction is in progress we intercept it: confirm with the
    // cashier, then abort the terminal transaction (showing a spinner while we
    // wait for the API) so the terminal state stays in sync with the UI.
    // I.e. no payment is left in a busy state if the cashier navigates away.
    async onClickBackButton() {
        const busyLine =
            this.router.state.current === "PaymentScreen"
                ? this.getBusyMarketpayPaymentLine()
                : false;

        if (!busyLine) {
            return super.onClickBackButton(...arguments);
        }

        const order = busyLine.pos_order_id;

        const confirmed = await ask(this.dialog, {
            title: _t("Cancel payment"),
            body: _t(
                "Are you sure you want to move away from here? It will cancel the payment."
            ),
            confirmLabel: _t("Yes"),
            cancelLabel: _t("No"),
        });

        if (!confirmed) {
            return;
        }

        // The payment may have resolved while the dialog was open. The cashier
        // already confirmed they want to leave; honor that unless the payment
        // completed (in which case we must not walk back to the basket).
        if (this.router.state.current !== "PaymentScreen") {
            return;
        }
        const lineAfterDialog = order.getPaymentlineByUuid(busyLine.uuid);
        if (lineAfterDialog && lineAfterDialog.isDone()) {
            this.notification.add(
                _t("Payment completed — the cancellation came too late."),
                { type: "warning" }
            );
            return;
        }
        const stillBusy =
            lineAfterDialog &&
            MARKETPAY_BUSY_STATUSES.includes(lineAfterDialog.getPaymentStatus());
        if (!stillBusy) {
            // retry / line gone: no live terminal transaction to abort.
            if (lineAfterDialog && !order.finalized) {
                order.removePaymentline(lineAfterDialog);
                this.paymentTerminalInProgress = false;
            }
            return super.onClickBackButton(...arguments);
        }

        const terminal = busyLine.payment_method_id.payment_terminal;

        let abortOutcome;
        this.ui.block({ message: _t("Cancelling the payment on the terminal…") });
        try {
            busyLine.setPaymentStatus("waitingCancel");
            // Best-effort cancel. Resolves once the terminal reports the real
            // outcome, or null if that wait times out.
            abortOutcome = await terminal.sendPaymentCancel(order, busyLine.uuid);
        } catch {
            // ORM/connection failure during abort: terminal state is unknown.
            // Keep the line and stay on the payment screen.
            busyLine.setPaymentStatus("waitingCard");
            return;
        } finally {
            this.ui.unblock();
        }

        if (this.router.state.current !== "PaymentScreen") {
            return;
        }

        const finalLine = order.getPaymentlineByUuid(busyLine.uuid);

        if (abortOutcome === false || (finalLine && finalLine.isDone())) {
            // The card was approved before the abort took effect. The standard
            // flow finalizes the order and navigates to the receipt; just inform
            // the cashier.
            if (finalLine && finalLine.isDone()) {
                this.notification.add(
                    _t("Payment completed — the cancellation came too late."),
                    { type: "warning" }
                );
            }
            return;
        }

        if (abortOutcome === null) {
            // Timed out waiting for Market Pay's authoritative outcome. The
            // pending payment promise is still live so a late webhook can still
            // complete or fail the payment. Keep the line and stay.
            if (finalLine && !order.finalized) {
                finalLine.setPaymentStatus("waitingCard");
            }
            return;
        }

        // Cancelled: clear the (now retriable) line and return to the basket,
        // but only while the order is still editable.
        if (!order.finalized) {
            if (finalLine) {
                order.removePaymentline(finalLine);
            }
            this.paymentTerminalInProgress = false;
            return super.onClickBackButton(...arguments);
        }
    },
});
