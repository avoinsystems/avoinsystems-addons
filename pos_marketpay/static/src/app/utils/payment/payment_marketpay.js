/** @odoo-module */

import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/payment/payment_interface";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { register_payment_method } from "@point_of_sale/app/store/pos_store";

// Must stay in sync with MARKETPAY_ABORT_TIMEOUT in client/marketpay.py (30s)
// plus a short buffer. One deadline for the whole Back spinner: the abort
// request and the pending payment resolution share it, so they cannot stack.
// Exported so the QUnit suite can advance this same deadline.
export const MARKETPAY_ABORT_WAIT_MS = 35000;

export class PaymentMarketpay extends PaymentInterface {
    setup() {
        super.setup(...arguments);

        this.supports_reversals = true;
        this.marketpayPaymentLineResolvers = {};
        // The same pending payment send_payment_request is waiting on, keyed by
        // the line cid that the payment screen passes to send_payment_cancel.
        this.marketpayPaymentLinePromises = {};
    }

    send_payment_request(uid) {
        super.send_payment_request(uid);
        return this._marketpayPaymentRequest("marketpay_request_process_transaction");
    }

    send_payment_reversal(uid) {
        super.send_payment_reversal(uid);
        return this._marketpayPaymentRequest("marketpay_request_cancel_transaction");
    }

    send_payment_cancel(order, cid) {
        super.send_payment_cancel(order, cid);
        return this._marketpayAbort(cid);
    }

    pendingMarketpayLine() {
        return this.pos.getPendingPaymentLine("marketpay");
    }

    _handleOdooConnectionFailure(data = {}) {
        var line = this.pendingMarketpayLine();
        if (line) {
            line.set_payment_status("retry");
        }

        this._showError(
            _t(
                "Could not connect to the Odoo server, please check your internet connection and try again."
            )
        );

        return Promise.reject(data);
    }

    _callMarketpay(data, method) {
        return this.env.services.orm.silent
            .call("pos.payment.method", method, [
                [this.payment_method.id],
                data
            ])
            .catch(this._handleOdooConnectionFailure.bind(this));
    }

    _computeEcrTransactionId(order) {
        var config = this.pos.config;
        const orderId = order.uid.replace(" ", "").replaceAll("-", "").toUpperCase();
        return `${config.id}-${orderId}--${order.pos_session_id}`;
    }

    _marketpayOrderData() {
        var order = this.pos.get_order();
        var config = this.pos.config;
        var line = order.selected_paymentline;
        const amountInCents = Math.round(line.amount * 100);

        var data = {
            "terminalTransactionId": line.transaction_id,
            "ecrTransactionId": this._computeEcrTransactionId(order),
            "cashierId": String(order.pos_session_id),
            "amount": amountInCents,
            "currency": this.pos.currency.numeric_code,
            "transactionReference": order.uid,
            "ecrId": `${config.name}-${config.id}`,
            "is_refund": order._isRefundOrder(),
        };

        return data;
    }

    _marketpayPaymentRequest(method) {
        var order = this.pos.get_order();
        var line = order.selected_paymentline;

        if (!this.pos.currency.numeric_code) {
            this._showError(
                _t(
                    "Currency is missing a currency code in ISO 4217 standard."
                )
            )
            return Promise.resolve();
        }

        var data = this._marketpayOrderData();
        var promise = this.waitForPaymentConfirmation();

        this._callMarketpay(data, method).then((response) => {

            if (response.status === "NOK") {
                this.saveResponseValues(line, response);

                line.set_payment_status("retry");
                this.resolvePaymentFalse(line.cid);

                if (response.message) {
                    this._showError(response.message);
                }

                if (response.debug) {
                    console.error("Market Pay: " + response.debug);
                }

            } else if (response.status === "OK") {
                this.handleSuccessResponse(line, response);
            }

            // We may also receive NEUTRAL response status,
            // which means we'll listen to notifications for further responses.
        });

        return promise;
    }

    // Asks the terminal to cancel the running transaction.
    //
    // Market Pay only acknowledges the abort (HTTP 204); it does NOT report
    // whether the card was already approved. The authoritative result is the
    // pending process-transaction response / completion notification. The abort
    // request and that pending resolution share one MARKETPAY_ABORT_WAIT_MS
    // deadline, so a hung abort (up to MARKETPAY_ABORT_TIMEOUT) plus a missing
    // notification cannot stack into a longer spinner.
    //
    // Returns:
    //   true  — transaction was cancelled
    //   false — it completed anyway
    //   null  — wait timed out; the pending promise is still live
    async _marketpayAbort(cid) {
        let timeoutId;
        const timedOut = {};
        // Started before the abort request. The same promise is raced again
        // below, so time spent on the abort call counts against the pending wait.
        // `browser.setTimeout` so the QUnit clock mock can fire this deadline.
        const deadline = new Promise((resolve) => {
            timeoutId = browser.setTimeout(() => resolve(timedOut), MARKETPAY_ABORT_WAIT_MS);
        });

        const reportTimeout = () => {
            // Do NOT resolvePaymentFalse: a late OK would then be treated as a
            // cancelled payment and can clobber a successful charge.
            this._showError(
                _t(
                    "Payment cancellation failed. If the transaction is still active, please cancel it manually on the payment terminal."
                )
            );
            return null;
        };

        // Let a genuine ORM/connection failure propagate (it is handled by
        // _handleOdooConnectionFailure) so the caller keeps the line and stays put.
        // The catch is only for a rejection that arrives after this race has
        // already timed out; otherwise it would be an unhandled rejection.
        const abortCall = this._callMarketpay({}, "marketpay_request_abort_transaction").then(
            () => true
        );
        abortCall.catch(() => {});

        try {
            const abortSettled = await Promise.race([abortCall, deadline]);
            if (abortSettled === timedOut) {
                return reportTimeout();
            }

            const pending = this.marketpayPaymentLinePromises
                ? this.marketpayPaymentLinePromises[cid]
                : null;

            if (!pending) {
                // The payment already resolved (e.g. while the confirmation dialog was
                // open); there is nothing left to wait for.
                return true;
            }

            const result = await Promise.race([
                pending.then((succeeded) => ({ succeeded })),
                deadline,
            ]);

            if (result === timedOut) {
                return reportTimeout();
            }

            return !result.succeeded;
        } finally {
            browser.clearTimeout(timeoutId);
        }
    }

    waitForPaymentConfirmation() {
        const line = this.pendingMarketpayLine();

        const promise = new Promise((resolve) => {
            this.marketpayPaymentLineResolvers[line.cid] = resolve;
        });
        this.marketpayPaymentLinePromises[line.cid] = promise;
        return promise;
    }

    resolvePaymentFalse(cid) {
        const resolver = this.marketpayPaymentLineResolvers ? this.marketpayPaymentLineResolvers[cid] : false;
        if (resolver) {
            resolver(false);
        }

        delete this.marketpayPaymentLineResolvers[cid];
        delete this.marketpayPaymentLinePromises[cid];
    }

    resolvePaymentTrue() {
        const line = this.pendingMarketpayLine();

        if (!line) {
            return;
        }

        const resolver = this.marketpayPaymentLineResolvers ? this.marketpayPaymentLineResolvers[line.cid] : false;
        if (resolver) {
            resolver(true);
        }

        delete this.marketpayPaymentLineResolvers[line.cid];
        delete this.marketpayPaymentLinePromises[line.cid];
    }

    async handleMarketpayStatusResponse() {
        const notification = await this.env.services.orm.silent.call(
            "pos.payment.method",
            "get_latest_marketpay_message", [
                [this.payment_method.id]
            ]
        );

        if (!notification) {
            this._handleOdooConnectionFailure();
            return;
        }
        const line = this.pendingMarketpayLine();

        // It may be that the line was already resolved by an initial `process-transaction` response or a notification
        if (!line) {
            return;
        }

        // Make sure the notification belongs to the current pending line. The
        // backend forwards the `ecrTransactionId` we sent in the original
        // request as `transaction_id`, so we recompute it from the line's
        // order and compare. This guards against stale notifications from a
        // previous order/line being applied to the wrong payment.
        const expectedEcrTransactionId = this._computeEcrTransactionId(line.order);
        if (notification.transaction_id !== expectedEcrTransactionId) {
            return;
        }

        switch (notification.message.status) {
            case "WAITING_FOR_CARD":
                line.set_payment_status("waitingCard");
                return;

            case "PIN_REQUIRED":
                // @todo: display a message on the UI?
                return;

            case "BANK_AUTHORIZATION":
                // @todo: display a message on the UI?
                return;

            case "COMPLETED":
                const payment_status = notification.message.result.status;
                if (payment_status === "OK")
                {
                    this.handleSuccessResponse(line, notification.message);
                } else {
                    line.set_payment_status("retry");
                    this.resolvePaymentFalse(line.cid);
                }
                break;
        }
    }

    saveResponseValues(line, response) {
        if (!line) {
            return;
        }

        // This function expects `response` to be in one of two formats: API or Notification.
        // The Notification response contains the required values inside a nested `result` array.
        let result = {};
        if ("result" in response) {
            result = response.result;
        } else {
            result = response;
        }

        if ("cashierReceipt" in result) {
            line.set_cashier_receipt(result.cashierReceipt);
        }

        if ("customerReceipt" in result) {
            line.set_receipt_info(result.customerReceipt);
        }

        if ("terminalTransactionId" in result)
        {
            line.transaction_id = result.terminalTransactionId;
        }

        if ("cardData" in result)
        {
            line.card_type = result.cardData.schema;
        }
    }

    handleSuccessResponse(line, response) {
        this.saveResponseValues(line, response);
        this.resolvePaymentTrue();
    }

    _showError(msg, title) {
        if (!title) {
            title = _t("Market Pay Error");
        }
        this.env.services.dialog.add(AlertDialog, {
            title: title,
            body: msg,
        });
    }
}

register_payment_method("marketpay", PaymentMarketpay);
