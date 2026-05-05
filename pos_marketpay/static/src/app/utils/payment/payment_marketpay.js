import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { register_payment_method } from "@point_of_sale/app/services/pos_store";

// Centralized logger for Market Pay flow. Easy to grep in DevTools as "[MarketPay]".
// Only emits when Odoo debug mode is enabled (standard or assets).
// The payload is deep-cloned so DevTools shows the values at log time, not
// whatever the live (potentially mutated) object looks like when expanded later.
function mpLog(event, payload = {}) {
    if (!odoo.debug) {
        return;
    }
    try {
        let snapshot;
        try {
            snapshot = JSON.parse(JSON.stringify(payload));
        } catch (_e) {
            // JSON serialization failed (e.g. circular references). Fall back to
            // the live reference so we still capture something useful.
            snapshot = payload;
        }
        console.info(`[MarketPay] ${event}`, {
            ts: new Date().toISOString(),
            ...snapshot,
        });
    } catch (_e) {
        // Never let logging break the payment flow.
    }
}

export class PaymentMarketpay extends PaymentInterface {
    setup() {
        super.setup(...arguments);

        this.supports_reversals = true;
        this.marketpayPaymentLineResolvers = {};
    }

    sendPaymentRequest(uuid) {
        super.sendPaymentRequest(uuid);
        mpLog("sendPaymentRequest", { uuid });
        return this._marketpayPaymentRequest("marketpay_request_process_transaction");
    }

    sendPaymentReversal(uuid) {
        super.sendPaymentReversal(uuid);
        mpLog("sendPaymentReversal", { uuid });
        return this._marketpayPaymentRequest("marketpay_request_cancel_transaction");
    }

    sendPaymentCancel(order, uuid) {
        super.sendPaymentCancel(order, uuid);
        mpLog("sendPaymentCancel", { uuid, order_uuid: order && order.uuid });
        return this._marketpayAbort(uuid);
    }

    pendingMarketpayLine() {
        return this.pos.getPendingPaymentLine("marketpay");
    }

    _handleOdooConnectionFailure(data = {}) {
        var line = this.pendingMarketpayLine();
        mpLog("OdooConnectionFailure", {
            line_uuid: line && line.uuid,
            data,
        });
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
        mpLog("ORM call -> backend", {
            method,
            payment_method_id: this.payment_method_id.id,
            data,
        });
        return this.env.services.orm.silent
            .call("pos.payment.method", method, [
                [this.payment_method_id.id],
                data
            ])
            .then((response) => {
                mpLog("ORM response <- backend", { method, response });
                return response;
            })
            .catch(this._handleOdooConnectionFailure.bind(this));
    }

    _computeEcrTransactionId(order) {
        var config = this.pos.config;
        const orderId = order.pos_reference.replace(" ", "").replaceAll("-", "").toUpperCase();
        return `${config.id}-${orderId}--${order.session_id.id}`;
    }

    _marketpayOrderData() {
        var order = this.pos.getOrder();
        var config = this.pos.config;
        var line = order.getSelectedPaymentline();
        const amountInCents = Math.round(line.amount * 100);

        var data = {
            "terminalTransactionId": line.transaction_id,
            "ecrTransactionId": this._computeEcrTransactionId(order),
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

        mpLog("payment request prepared", {
            method,
            line_uuid: line && line.uuid,
            order_uuid: order && order.uuid,
            ecrTransactionId: data.ecrTransactionId,
            terminalTransactionId: data.terminalTransactionId,
            amountInCents: data.amount,
        });

        this._callMarketpay(data, method).then((response) => {
            mpLog("initial transaction response", {
                method,
                line_uuid: line && line.uuid,
                response_status: response && response.status,
                response,
            });

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
            } else {
                // NEUTRAL: we'll wait for asynchronous notifications via websocket.
                mpLog("waiting for async notifications", {
                    method,
                    line_uuid: line && line.uuid,
                    response_status: response && response.status,
                });
            }
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
        mpLog("registering payment confirmation resolver", {
            line_uuid: line && line.uuid,
        });

        return new Promise((resolve) => {
            this.marketpayPaymentLineResolvers[line.uuid] = resolve;
        });
    }

    resolvePaymentFalse(uuid) {
        const resolver = this.marketpayPaymentLineResolvers ? this.marketpayPaymentLineResolvers[uuid] : false;
        mpLog("resolvePaymentFalse", {
            line_uuid: uuid,
            resolver_present: Boolean(resolver),
        });
        if (resolver) {
            resolver(false);
        }

        delete this.marketpayPaymentLineResolvers[uuid];
    }

    resolvePaymentTrue() {
        const line = this.pendingMarketpayLine();

        if (!line) {
            mpLog("resolvePaymentTrue: no pending line", {
                resolvers: Object.keys(this.marketpayPaymentLineResolvers || {}),
            });
            return;
        }

        const resolver = this.marketpayPaymentLineResolvers ? this.marketpayPaymentLineResolvers[line.uuid] : false;
        mpLog("resolvePaymentTrue", {
            line_uuid: line.uuid,
            resolver_present: Boolean(resolver),
        });
        if (resolver) {
            resolver(true);
        }

        delete this.marketpayPaymentLineResolvers[line.uuid];
    }

    async handleMarketpayStatusResponse() {
        mpLog("handleMarketpayStatusResponse: fetching latest notification");

        const notification = await this.env.services.orm.silent.call(
            "pos.payment.method",
            "get_latest_marketpay_message", [
                [this.payment_method_id.id]
            ]
        );

        mpLog("handleMarketpayStatusResponse: notification fetched", { notification });

        if (!notification) {
            mpLog("handleMarketpayStatusResponse: empty notification, treating as connection failure");
            this._handleOdooConnectionFailure();
            return;
        }
        const line = this.pendingMarketpayLine();

        // It may be that the line was already resolved by an initial `process-transaction` response or a notification
        if (!line) {
            mpLog("handleMarketpayStatusResponse: no pending line, ignoring notification", {
                notification_status: notification.message && notification.message.status,
                transaction_id: notification.transaction_id,
            });
            return;
        }

        // Make sure the notification belongs to the current pending line. The
        // backend forwards the `ecrTransactionId` we sent in the original
        // request as `transaction_id`, so we recompute it from the line's
        // order and compare. This guards against stale notifications from a
        // previous order/line being applied to the wrong payment.
        const expectedEcrTransactionId = this._computeEcrTransactionId(line.pos_order_id);
        if (notification.transaction_id !== expectedEcrTransactionId) {
            mpLog("handleMarketpayStatusResponse: ecrTransactionId mismatch, ignoring notification", {
                line_uuid: line.uuid,
                expected: expectedEcrTransactionId,
                received: notification.transaction_id,
            });
            return;
        }

        const status = notification.message && notification.message.status;
        mpLog("handleMarketpayStatusResponse: dispatching status", {
            line_uuid: line.uuid,
            status,
            transaction_id: notification.transaction_id,
        });

        switch (status) {
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
                const payment_status = notification.message.result && notification.message.result.status;
                mpLog("handleMarketpayStatusResponse: COMPLETED", {
                    line_uuid: line.uuid,
                    payment_status,
                    result: notification.message.result,
                });
                if (payment_status === "OK")
                {
                    this.handleSuccessResponse(line, notification.message);
                } else {
                    line.setPaymentStatus("retry");
                    this.resolvePaymentFalse(line.uuid);
                }
                break;

            default:
                mpLog("handleMarketpayStatusResponse: unknown status", {
                    line_uuid: line.uuid,
                    status,
                    notification,
                });
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
        mpLog("handleSuccessResponse", {
            line_uuid: line && line.uuid,
            response,
        });
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
