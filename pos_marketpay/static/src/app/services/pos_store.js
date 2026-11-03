/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PosBus } from "@point_of_sale/app/bus/pos_bus_service";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ConfirmPopup } from "@point_of_sale/app/utils/confirm_popup/confirm_popup";

// Payment statuses in which a Market Pay transaction is actively running on the
// terminal and must be aborted before leaving the payment screen.
const MARKETPAY_BUSY_STATUSES = ["waiting", "waitingCard", "timeout"];

patch(PosStore.prototype, {
    // Returns the current order's Market Pay payment line that is actively
    // running on the terminal (if any).
    getBusyMarketpayPaymentLine() {
        const order = this.get_order();
        if (!order) {
            return false;
        }
        return (
            order.paymentlines.find(
                (line) =>
                    line.payment_method.use_payment_terminal === "marketpay" &&
                    !line.is_done() &&
                    MARKETPAY_BUSY_STATUSES.includes(line.get_payment_status())
            ) || false
        );
    },

    // The payment screen Back button and the mobile navbar Back button both
    // call this before leaving. When a Market Pay transaction is in progress
    // we confirm with the cashier, then abort the terminal transaction
    // (showing a spinner while we wait) so the terminal stays in sync with
    // the UI. `navigate` is the caller's normal way off this screen.
    //
    // Returns true when this click was handled. Returns false when there is
    // nothing to abort and the caller should navigate as usual.
    async marketpayLeavePaymentScreen(navigate) {
        if (this.mainScreen.component !== PaymentScreen) {
            return false;
        }
        const busyLine = this.getBusyMarketpayPaymentLine();
        if (!busyLine) {
            return false;
        }

        const order = busyLine.order;
        const { confirmed } = await this.popup.add(ConfirmPopup, {
            title: _t("Cancel payment"),
            body: _t(
                "Are you sure you want to move away from here? It will cancel the payment."
            ),
            confirmText: _t("Yes"),
            cancelText: _t("No"),
        });
        if (!confirmed) {
            return true;
        }

        // The payment may have resolved while the dialog was open. The cashier
        // already confirmed they want to leave; honor that unless the payment
        // completed (in which case we must not walk back to the basket).
        if (this.mainScreen.component !== PaymentScreen) {
            return true;
        }
        const lineAfterDialog = order.paymentlines.find((line) => line.cid === busyLine.cid);
        if (lineAfterDialog && lineAfterDialog.is_done()) {
            this._marketpayLateCancellationNotice();
            return true;
        }
        const stillBusy =
            lineAfterDialog &&
            MARKETPAY_BUSY_STATUSES.includes(lineAfterDialog.get_payment_status());
        if (!stillBusy) {
            // retry / line gone: no live terminal transaction to abort.
            if (lineAfterDialog && !order.finalized) {
                order.remove_paymentline(lineAfterDialog);
            }
            navigate();
            return true;
        }

        const terminal = busyLine.payment_method.payment_terminal;
        let abortOutcome;
        this.ui.block({ message: _t("Cancelling the payment on the terminal…") });
        try {
            busyLine.set_payment_status("waitingCancel");
            // Best-effort cancel. Resolves once the terminal reports the real
            // outcome, or null if that wait times out.
            abortOutcome = await terminal.send_payment_cancel(order, busyLine.cid);
        } catch {
            // ORM/connection failure during abort: terminal state is unknown.
            // Keep the line and stay on the payment screen.
            busyLine.set_payment_status("waitingCard");
            return true;
        } finally {
            this.ui.unblock();
        }

        if (this.mainScreen.component !== PaymentScreen) {
            return true;
        }

        const finalLine = order.paymentlines.find((line) => line.cid === busyLine.cid);
        if (abortOutcome === false || (finalLine && finalLine.is_done())) {
            // The card was approved before the abort took effect. The standard
            // flow finalizes the order and navigates to the receipt; just inform
            // the cashier.
            if (finalLine && finalLine.is_done()) {
                this._marketpayLateCancellationNotice();
            }
            return true;
        }

        if (abortOutcome === null) {
            // Timed out waiting for Market Pay's authoritative outcome. The
            // pending payment promise is still live so a late notification can
            // still complete or fail the payment. Keep the line and stay.
            if (finalLine && !order.finalized) {
                finalLine.set_payment_status("waitingCard");
            }
            return true;
        }

        // Cancelled: clear the line and return to the basket, but only while
        // the order is still editable.
        if (!order.finalized) {
            if (finalLine) {
                order.remove_paymentline(finalLine);
            }
            navigate();
        }
        return true;
    },

    _marketpayLateCancellationNotice() {
        this.env.services.pos_notification.add(
            _t("Payment completed — the cancellation came too late."),
            5000
        );
    },
});

patch(PosBus.prototype, {
    dispatch(message) {
        super.dispatch(...arguments);

        if (message.type === "MARKETPAY_LATEST_RESPONSE") {
            const pendingLine = this.pos.getPendingPaymentLine("marketpay");

            if (pendingLine) {
                pendingLine.payment_method.payment_terminal.handleMarketpayStatusResponse();
            }
        }
    },
});
