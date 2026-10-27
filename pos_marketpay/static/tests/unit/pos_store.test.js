import { describe, expect, test } from "@odoo/hoot";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import "@pos_marketpay/app/services/pos_store";

describe("pos_marketpay back button", () => {
    function makeLine(status = "waiting") {
        const line = {
            uuid: "line-1",
            status,
            payment_method_id: {
                use_payment_terminal: "marketpay",
                payment_terminal: {
                    calls: 0,
                    sendPaymentCancel() {
                        this.calls++;
                        return Promise.resolve(true);
                    },
                },
            },
            isDone() {
                return this.status === "done";
            },
            getPaymentStatus() {
                return this.status;
            },
            setPaymentStatus(value) {
                this.status = value;
            },
        };
        return line;
    }

    function makePos({ line = null, screen = "PaymentScreen", onDialog } = {}) {
        const order = {
            uuid: "order-1",
            finalized: false,
            removed: [],
            payment_ids: line ? [line] : [],
            getPaymentlineByUuid(uuid) {
                return this.payment_ids.find((paymentLine) => paymentLine.uuid === uuid);
            },
            removePaymentline(paymentLine) {
                this.removed.push(paymentLine);
                this.payment_ids = this.payment_ids.filter((item) => item !== paymentLine);
            },
        };
        if (line) {
            line.pos_order_id = order;
        }
        const pos = {
            router: { state: { current: screen } },
            mobile_pane: "right",
            navigated: [],
            notifications: [],
            blocked: 0,
            unblocked: 0,
            paymentTerminalInProgress: true,
            getOrder() {
                return order;
            },
            navigate(page, params) {
                this.navigated.push({ page, params });
            },
            // Do not read the message. _t() throws when stringified because the
            // unit-test bundle has no translations loaded.
            notification: {
                add(_message, options) {
                    pos.notifications.push(options);
                },
            },
            ui: {
                block() {
                    pos.blocked++;
                },
                unblock() {
                    pos.unblocked++;
                },
            },
            dialog: {
                add(_component, props) {
                    if (onDialog) {
                        onDialog(props, line);
                    } else {
                        props.confirm();
                    }
                },
            },
        };
        return { pos, order, line };
    }

    function clickBack(pos) {
        // The patched method calls this.getBusyMarketpayPaymentLine(), which
        // lives on PosStore.prototype. The stub keeps its own getOrder and navigate.
        Object.setPrototypeOf(pos, PosStore.prototype);
        return pos.onClickBackButton();
    }

    test("No busy Market Pay line leaves the payment screen", async () => {
        const { pos } = makePos();

        await clickBack(pos);
        // Check that the method navigated to the product screen and the order was not removed.
        expect(pos.navigated).toEqual([{ page: "ProductScreen", params: { orderUuid: "order-1" } }]);
        // Check that the cancellation spinner was not shown.
        expect(pos.blocked).toBe(0);
    });

    test("Cancelling the confirmation stays on the payment screen", async () => {
        const line = makeLine();
        const { pos } = makePos({
            line,
            onDialog(props) {
                props.cancel(); // Cancel the dialog. That is the "No" button.
            },
        });

        await clickBack(pos);

        // Check that the terminal's sendPaymentCancel was never called.
        expect(line.payment_method_id.payment_terminal.calls).toBe(0);
        // Check that the method did not navigate away and the spinner was not shown.
        expect(pos.navigated).toEqual([]);
        expect(pos.blocked).toBe(0);
        // Check that the payment line is still waiting. Cancelling the dialog did not change it.
        expect(line.getPaymentStatus()).toBe("waiting");
    });

    test("Confirmed back removes a line that is no longer busy", async () => {
        const line = makeLine();
        const { pos, order } = makePos({
            line,
            onDialog(props, paymentLine) {
                // The payment failed while the dialog was open, so the line is no longer busy.
                paymentLine.setPaymentStatus("retry");
                props.confirm(); // Confirm the dialog. That is the "Yes" button.
            },
        });

        await clickBack(pos);

        // Check that the terminal was not asked to abort, because the line was no longer busy.
        expect(line.payment_method_id.payment_terminal.calls).toBe(0);
        // Check that the leftover line was removed and the terminal is no longer marked in progress.
        expect(order.removed).toEqual([line]);
        expect(pos.paymentTerminalInProgress).toBe(false);
        // Check that the method navigated to the product screen.
        expect(pos.navigated).toEqual([{ page: "ProductScreen", params: { orderUuid: "order-1" } }]);
    });

    test("Confirmed back stays when the payment already completed", async () => {
        const line = makeLine();
        const { pos, order } = makePos({
            line,
            onDialog(props, paymentLine) {
                // The payment completed while the dialog was open.
                paymentLine.setPaymentStatus("done");
                props.confirm(); // Confirm the dialog. That is the "Yes" button.
            },
        });

        await clickBack(pos);

        // Check that the terminal was not asked to abort, because the payment already completed.
        expect(line.payment_method_id.payment_terminal.calls).toBe(0);
        // Check that the completed line was kept and the screen did not leave.
        expect(order.removed).toEqual([]);
        expect(pos.navigated).toEqual([]);
        // Check that the cashier was warned the cancellation came too late.
        expect(pos.notifications).toEqual([{ type: "warning" }]);
    });

    test("Successful abort removes the line and leaves", async () => {
        const line = makeLine();
        // The dialog confirms itself. That is the "Yes" button, and the abort succeeds.
        const { pos, order } = makePos({ line });

        await clickBack(pos);

        // Check that the terminal was asked to abort once.
        expect(line.payment_method_id.payment_terminal.calls).toBe(1);
        // Check that the cancelled line was removed and the terminal is no longer marked in progress.
        expect(order.removed).toEqual([line]);
        expect(pos.paymentTerminalInProgress).toBe(false);
        // Check that the cancellation spinner was shown and then hidden.
        expect(pos.blocked).toBe(1);
        expect(pos.unblocked).toBe(1);
        // Check that the method navigated to the product screen.
        expect(pos.navigated).toEqual([{ page: "ProductScreen", params: { orderUuid: "order-1" } }]);
    });

    test("Timed out abort keeps the line on the payment screen", async () => {
        const line = makeLine();
        // The abort wait times out, so sendPaymentCancel resolves to null.
        line.payment_method_id.payment_terminal.sendPaymentCancel = function () {
            this.calls++;
            return Promise.resolve(null);
        };
        const { pos, order } = makePos({ line });

        await clickBack(pos);

        // Check that the terminal was asked to abort once.
        expect(line.payment_method_id.payment_terminal.calls).toBe(1);
        // Check that the line was put back to waiting for the card and was not removed.
        expect(line.getPaymentStatus()).toBe("waitingCard");
        expect(order.removed).toEqual([]);
        // Check that the screen stayed and no warning was shown.
        expect(pos.navigated).toEqual([]);
        expect(pos.notifications).toEqual([]);
        // Check that the cancellation spinner was hidden again.
        expect(pos.unblocked).toBe(1);
    });

    test("Abort that loses to a completed payment shows a warning and stays", async () => {
        const line = makeLine();
        // The card is approved while the abort is in flight, so sendPaymentCancel returns false.
        line.payment_method_id.payment_terminal.sendPaymentCancel = function () {
            this.calls++;
            line.setPaymentStatus("done");
            return Promise.resolve(false);
        };
        const { pos, order } = makePos({ line });

        await clickBack(pos);

        // Check that the completed line was kept and the screen did not leave.
        expect(order.removed).toEqual([]);
        expect(pos.navigated).toEqual([]);
        // Check that the cashier was warned the cancellation came too late.
        expect(pos.notifications).toEqual([{ type: "warning" }]);
        // Check that the cancellation spinner was hidden again.
        expect(pos.unblocked).toBe(1);
    });

    test("Abort request failure keeps the line on the payment screen", async () => {
        const line = makeLine();
        // The abort request fails, so the terminal state is unknown.
        line.payment_method_id.payment_terminal.sendPaymentCancel = function () {
            this.calls++;
            return Promise.reject(new Error("down"));
        };
        const { pos, order } = makePos({ line });

        await clickBack(pos);

        // Check that the line was put back to waiting for the card and was not removed.
        expect(line.getPaymentStatus()).toBe("waitingCard");
        expect(order.removed).toEqual([]);
        // Check that the screen stayed and no warning was shown.
        expect(pos.navigated).toEqual([]);
        expect(pos.notifications).toEqual([]);
        // Check that the cancellation spinner was hidden again.
        expect(pos.unblocked).toBe(1);
    });
});
