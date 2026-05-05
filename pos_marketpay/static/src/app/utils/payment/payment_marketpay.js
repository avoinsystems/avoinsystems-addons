/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/payment/payment_interface";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { register_payment_method } from "@point_of_sale/app/store/pos_store";

export class PaymentMarketpay extends PaymentInterface {
    setup() {
        super.setup(...arguments);

        this.supports_reversals = true;
        this.marketpayPaymentLineResolvers = {};
    }

    send_payment_request(uid) {
        super.send_payment_request(uid);
        return this._marketpayPaymentRequest("marketpay_request_process_transaction");
    }

    send_payment_reversal(uid) {
        super.send_payment_reversal(uid);
        return this._marketpayPaymentRequest("marketpay_request_cancel_transaction");
    }

    send_payment_cancel(order, uid) {
        super.send_payment_cancel(order, uid);
        return this._marketpayAbort(uid);
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
                this.resolvePaymentFalse(line.uid);

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

    _marketpayAbort(uid) {
        this.resolvePaymentFalse(uid);

        return this._callMarketpay({}, "marketpay_request_abort_transaction").then((data) => {
            if (data.status !== "OK") {
                this._showError(
                    _t("Payment cancellation failed. If the transaction is still active, please cancel it manually on the payment terminal.")
                );
            }

            return Promise.resolve(true);
        });
    }

    waitForPaymentConfirmation() {
        const line = this.pendingMarketpayLine();

        return new Promise((resolve) => {
            this.marketpayPaymentLineResolvers[line.uid] = resolve;
        });
    }

    resolvePaymentFalse(uid) {
        const resolver = this.marketpayPaymentLineResolvers ? this.marketpayPaymentLineResolvers[uid] : false;
        if (resolver) {
            resolver(false);
        }

        delete this.marketpayPaymentLineResolvers[uid];
    }

    resolvePaymentTrue() {
        const line = this.pendingMarketpayLine();

        if (!line) {
            return;
        }

        const resolver = this.marketpayPaymentLineResolvers ? this.marketpayPaymentLineResolvers[line.uid] : false;
        if (resolver) {
            resolver(true);
        }

        delete this.marketpayPaymentLineResolvers[line.uid];
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
                    this.resolvePaymentFalse(line.uid);
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
