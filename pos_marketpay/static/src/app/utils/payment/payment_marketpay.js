import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { register_payment_method } from "@point_of_sale/app/services/pos_store";

export class PaymentMarketpay extends PaymentInterface {
    setup() {
        super.setup(...arguments);

        this.supports_reversals = true;
        this.marketpayPaymentLineResolvers = {};
    }

    sendPaymentRequest(uuid) {
        super.sendPaymentRequest(uuid);
        return this._marketpayPaymentRequest("marketpay_request_process_transaction");
    }

    sendPaymentReversal(uuid) {
        super.sendPaymentReversal(uuid);
        return this._marketpayPaymentRequest("marketpay_request_cancel_transaction");
    }

    sendPaymentCancel(order, uuid) {
        super.sendPaymentCancel(order, uuid);
        return this._marketpayAbort(uuid);
    }

    pendingMarketpayLine() {
        return this.pos.getPendingPaymentLine("marketpay");
    }

    _handleOdooConnectionFailure(data = {}) {
        var line = this.pendingMarketpayLine();
        if (line) {
            line.setPaymentStatus("retry");
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
                [this.payment_method_id.id],
                data
            ])
            .catch(this._handleOdooConnectionFailure.bind(this));
    }

    _marketpayOrderData() {
        var order = this.pos.getOrder();
        var config = this.pos.config;
        var line = order.getSelectedPaymentline();
        const amountInCents = Math.round(line.amount * 100);

        const orderId = order.pos_reference.replace(" ", "").replaceAll("-", "").toUpperCase();

        var data = {
            "terminalTransactionId": line.transaction_id,
            "ecrTransactionId": `${config.id}-${orderId}--${order.session_id.id}`,
            "cashierId": order.user_id.id,
            "amount": amountInCents,
            "currency": this.pos.currency.iso_numeric,
            "transactionReference": order.uuid,
            "ecrId": `${config.name}-${config.id}`,
            "is_refund": order.isRefund,
        };

        return data;
    }

    _marketpayPaymentRequest(method) {
        var order = this.pos.getOrder();
        var line = order.getSelectedPaymentline();

        if (!this.pos.currency.iso_numeric) {
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

                line.setPaymentStatus("retry");
                this.resolvePaymentFalse(line.uuid);

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

    _marketpayAbort(uuid) {
        this.resolvePaymentFalse(uuid);

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
            this.marketpayPaymentLineResolvers[line.uuid] = resolve;
        });
    }

    resolvePaymentFalse(uuid) {
        const resolver = this.marketpayPaymentLineResolvers ? this.marketpayPaymentLineResolvers[uuid] : false;
        if (resolver) {
            resolver(false);
        }

        delete this.marketpayPaymentLineResolvers[uuid];
    }

    resolvePaymentTrue() {
        const line = this.pendingMarketpayLine();

        if (!line) {
            return;
        }

        const resolver = this.marketpayPaymentLineResolvers ? this.marketpayPaymentLineResolvers[line.uuid] : false;
        if (resolver) {
            resolver(true);
        }

        delete this.marketpayPaymentLineResolvers[line.uuid];
    }

    async handleMarketpayStatusResponse() {
        const notification = await this.env.services.orm.silent.call(
            "pos.payment.method",
            "get_latest_marketpay_message", [
                [this.payment_method_id.id]
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

        switch (notification.message.status) {
            case "WAITING_FOR_CARD":
                line.setPaymentStatus("waitingCard");
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
                    line.setPaymentStatus("retry");
                    this.resolvePaymentFalse(line.uuid);
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
            line.setCashierReceipt(result.cashierReceipt);
        }

        if ("customerReceipt" in result) {
            line.setReceiptInfo(result.customerReceipt);
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
