/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import "@pos_marketpay/app/screens/payment_screen/payment_screen";
import "@pos_marketpay/app/services/pos_store";

const LATE_NOTICE = "Payment completed — the cancellation came too late.";

QUnit.module("pos_marketpay back button", () => {
    function makeLine(status = "waiting") {
        return {
            cid: "line-1",
            status,
            payment_method: {
                use_payment_terminal: "marketpay",
                payment_terminal: {
                    calls: 0,
                    send_payment_cancel() {
                        this.calls++;
                        return Promise.resolve(true);
                    },
                },
            },
            is_done() {
                return this.status === "done";
            },
            get_payment_status() {
                return this.status;
            },
            set_payment_status(value) {
                this.status = value;
            },
        };
    }

    function makePos({ line = null, onDialog } = {}) {
        const order = {
            finalized: false,
            removed: [],
            paymentlines: line ? [line] : [],
            remove_paymentline(paymentLine) {
                this.removed.push(paymentLine);
                this.paymentlines = this.paymentlines.filter((item) => item !== paymentLine);
            },
        };
        if (line) {
            line.order = order;
        }
        const pos = {
            mainScreen: { component: PaymentScreen },
            navigated: [],
            notifications: [],
            blocked: 0,
            unblocked: 0,
            get_order() {
                return order;
            },
            showScreen(name) {
                pos.navigated.push(name);
            },
            env: {
                services: {
                    pos_notification: {
                        add(message) {
                            pos.notifications.push(message);
                        },
                    },
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
            popup: {
                add() {
                    if (onDialog) {
                        return Promise.resolve(onDialog(line));
                    }
                    // Confirm the dialog. That is the "Yes" button.
                    return Promise.resolve({ confirmed: true });
                },
            },
        };
        return { pos, order, line };
    }

    function clickBack(pos) {
        // PaymentScreen.onClickBack calls marketpayLeavePaymentScreen, which
        // lives on PosStore.prototype. The stub keeps its own get_order and showScreen.
        Object.setPrototypeOf(pos, PosStore.prototype);
        const screen = { pos };
        Object.setPrototypeOf(screen, PaymentScreen.prototype);
        return screen.onClickBack();
    }

    QUnit.test("No busy Market Pay line leaves the payment screen", async function (assert) {
        const { pos } = makePos();

        await clickBack(pos);
        // Check that Back left for the product screen.
        assert.deepEqual(pos.navigated, ["ProductScreen"]);
        // Check that the cancellation spinner was not shown.
        assert.strictEqual(pos.blocked, 0);
    });

    QUnit.test("Cancelling the confirmation stays on the payment screen", async function (assert) {
        const line = makeLine();
        const { pos } = makePos({
            line,
            onDialog() {
                return { confirmed: false }; // Cancel the dialog. That is the "No" button.
            },
        });

        await clickBack(pos);

        // Check that the terminal's send_payment_cancel was never called.
        assert.strictEqual(line.payment_method.payment_terminal.calls, 0);
        // Check that Back did not leave and the spinner was not shown.
        assert.deepEqual(pos.navigated, []);
        assert.strictEqual(pos.blocked, 0);
        // Check that the payment line is still waiting. Cancelling the dialog did not change it.
        assert.strictEqual(line.get_payment_status(), "waiting");
    });

    QUnit.test("Confirmed back removes a line that is no longer busy", async function (assert) {
        const line = makeLine();
        const { pos, order } = makePos({
            line,
            onDialog(paymentLine) {
                // The payment failed while the dialog was open, so the line is no longer busy.
                paymentLine.set_payment_status("retry");
                return { confirmed: true }; // Confirm the dialog. That is the "Yes" button.
            },
        });

        await clickBack(pos);

        // Check that the terminal was not asked to abort, because the line was no longer busy.
        assert.strictEqual(line.payment_method.payment_terminal.calls, 0);
        // Check that the leftover line was removed.
        assert.deepEqual(order.removed, [line]);
        // Check that Back left for the product screen.
        assert.deepEqual(pos.navigated, ["ProductScreen"]);
    });

    QUnit.test("Confirmed back stays when the payment already completed", async function (assert) {
        const line = makeLine();
        const { pos, order } = makePos({
            line,
            onDialog(paymentLine) {
                // The payment completed while the dialog was open.
                paymentLine.set_payment_status("done");
                return { confirmed: true }; // Confirm the dialog. That is the "Yes" button.
            },
        });

        await clickBack(pos);

        // Check that the terminal was not asked to abort, because the payment already completed.
        assert.strictEqual(line.payment_method.payment_terminal.calls, 0);
        // Check that the completed line was kept and the screen did not leave.
        assert.deepEqual(order.removed, []);
        assert.deepEqual(pos.navigated, []);
        // Check that the cashier was warned the cancellation came too late.
        assert.deepEqual(pos.notifications, [LATE_NOTICE]);
    });

    QUnit.test("Successful abort removes the line and leaves", async function (assert) {
        const line = makeLine();
        // The dialog confirms itself. That is the "Yes" button, and the abort succeeds.
        const { pos, order } = makePos({ line });

        await clickBack(pos);

        // Check that the terminal was asked to abort once.
        assert.strictEqual(line.payment_method.payment_terminal.calls, 1);
        // Check that the cancelled line was removed.
        assert.deepEqual(order.removed, [line]);
        // Check that the cancellation spinner was shown and then hidden.
        assert.strictEqual(pos.blocked, 1);
        assert.strictEqual(pos.unblocked, 1);
        // Check that Back left for the product screen.
        assert.deepEqual(pos.navigated, ["ProductScreen"]);
    });

    QUnit.test("Timed out abort keeps the line on the payment screen", async function (assert) {
        const line = makeLine();
        // The abort wait times out, so send_payment_cancel resolves to null.
        line.payment_method.payment_terminal.send_payment_cancel = function () {
            this.calls++;
            return Promise.resolve(null);
        };
        const { pos, order } = makePos({ line });

        await clickBack(pos);

        // Check that the terminal was asked to abort once.
        assert.strictEqual(line.payment_method.payment_terminal.calls, 1);
        // Check that the line was put back to waiting for the card and was not removed.
        assert.strictEqual(line.get_payment_status(), "waitingCard");
        assert.deepEqual(order.removed, []);
        // Check that the screen stayed and no warning was shown.
        assert.deepEqual(pos.navigated, []);
        assert.deepEqual(pos.notifications, []);
        // Check that the cancellation spinner was hidden again.
        assert.strictEqual(pos.unblocked, 1);
    });

    QUnit.test(
        "Abort that loses to a completed payment shows a warning and stays",
        async function (assert) {
            const line = makeLine();
            // The card is approved while the abort is in flight, so send_payment_cancel returns false.
            line.payment_method.payment_terminal.send_payment_cancel = function () {
                this.calls++;
                line.set_payment_status("done");
                return Promise.resolve(false);
            };
            const { pos, order } = makePos({ line });

            await clickBack(pos);

            // Check that the completed line was kept and the screen did not leave.
            assert.deepEqual(order.removed, []);
            assert.deepEqual(pos.navigated, []);
            // Check that the cashier was warned the cancellation came too late.
            assert.deepEqual(pos.notifications, [LATE_NOTICE]);
            // Check that the cancellation spinner was hidden again.
            assert.strictEqual(pos.unblocked, 1);
        }
    );

    QUnit.test("Abort request failure keeps the line on the payment screen", async function (assert) {
        const line = makeLine();
        // The abort request fails, so the terminal state is unknown.
        line.payment_method.payment_terminal.send_payment_cancel = function () {
            this.calls++;
            return Promise.reject(new Error("down"));
        };
        const { pos, order } = makePos({ line });

        await clickBack(pos);

        // Check that the line was put back to waiting for the card and was not removed.
        assert.strictEqual(line.get_payment_status(), "waitingCard");
        assert.deepEqual(order.removed, []);
        // Check that the screen stayed and no warning was shown.
        assert.deepEqual(pos.navigated, []);
        assert.deepEqual(pos.notifications, []);
        // Check that the cancellation spinner was hidden again.
        assert.strictEqual(pos.unblocked, 1);
    });
});
