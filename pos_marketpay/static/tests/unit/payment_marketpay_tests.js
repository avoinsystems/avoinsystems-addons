/** @odoo-module */

import { makeDeferred, mockTimeout } from "@web/../tests/helpers/utils";
import {
    MARKETPAY_ABORT_WAIT_MS,
    PaymentMarketpay,
} from "@pos_marketpay/app/utils/payment/payment_marketpay";

const TIMEOUT_MESSAGE =
    "Payment cancellation failed. If the transaction is still active, please cancel it manually on the payment terminal.";

QUnit.module("pos_marketpay abort", (hooks) => {
    let advanceTime;

    hooks.beforeEach(() => {
        advanceTime = mockTimeout().advanceTime;
    });

    function makeTerminal() {
        const terminal = new PaymentMarketpay({ env: {} }, { id: 1 });
        terminal.errors = [];
        terminal._showError = (msg) => terminal.errors.push(msg);
        return terminal;
    }

    async function flush() {
        for (let i = 0; i < 8; i++) {
            await Promise.resolve();
        }
    }

    // Register the payment the way send_payment_request does. resolvePaymentFalse
    // settles this promise; a Deferred placed straight into the map does not.
    function trackPendingPayment(terminal) {
        terminal.pendingMarketpayLine = () => ({ cid: "line-1" });
        const pending = terminal.waitForPaymentConfirmation();
        let pendingSettled = false;
        pending.then(() => {
            pendingSettled = true;
        });
        return {
            isSettled() {
                return pendingSettled;
            },
        };
    }

    QUnit.test("Cancelled payment returns true", async function (assert) {
        const terminal = makeTerminal();
        const pending = makeDeferred();
        // The abort request resolves at once. _marketpayAbort ignores its body.
        terminal._callMarketpay = () => Promise.resolve({ status: "OK" });
        // The in-progress payment for "line-1". send_payment_request returns this same promise.
        terminal.marketpayPaymentLinePromises = { "line-1": pending };

        const result = terminal._marketpayAbort("line-1");
        // Let the resolved abort call finish, so the method is waiting on the payment.
        await flush();
        // The payment did not succeed, so the transaction was cancelled.
        pending.resolve(false);

        // Check that the abort reports the payment as cancelled.
        assert.strictEqual(await result, true);
        // Check that the timeout path did not run. Only that path calls _showError.
        assert.deepEqual(terminal.errors, []);
    });

    QUnit.test("Payment that completed anyway returns false", async function (assert) {
        const terminal = makeTerminal();
        const pending = makeDeferred();
        terminal._callMarketpay = () => Promise.resolve({ status: "OK" });
        terminal.marketpayPaymentLinePromises = { "line-1": pending };

        const result = terminal._marketpayAbort("line-1");
        await flush();
        // The payment succeeded.
        pending.resolve(true);

        // Check that the abort reports the payment as not cancelled.
        assert.strictEqual(await result, false);
        assert.deepEqual(terminal.errors, []);
    });

    QUnit.test("No pending payment returns true", async function (assert) {
        const terminal = makeTerminal();
        terminal._callMarketpay = () => Promise.resolve({ status: "OK" });
        // No in-progress payment. It already resolved, for example while the dialog was open.
        terminal.marketpayPaymentLinePromises = {};

        // The abort request still runs, but there is no payment to wait for, so this returns true.
        assert.strictEqual(await terminal._marketpayAbort("line-1"), true);
        assert.deepEqual(terminal.errors, []);
    });

    QUnit.test("Connection failure during abort propagates", async function (assert) {
        const terminal = makeTerminal();
        // The abort request fails. That stands in for an Odoo connection error.
        terminal._callMarketpay = () => Promise.reject(new Error("down"));
        // A payment is registered, but the failure happens before it is awaited.
        terminal.marketpayPaymentLinePromises = { "line-1": makeDeferred() };

        // Check that the failure rejects the abort instead of returning true, false, or null.
        try {
            await terminal._marketpayAbort("line-1");
            assert.ok(false, "the abort should reject");
        } catch (error) {
            assert.strictEqual(error.message, "down");
        }
        assert.deepEqual(terminal.errors, []);
    });

    QUnit.test("Abort request and pending payment share one deadline", async function (assert) {
        const terminal = makeTerminal();
        const abortCall = makeDeferred();
        const pending = trackPendingPayment(terminal);
        // The abort request stays open until resolve() is called.
        terminal._callMarketpay = () => abortCall;

        // settled becomes true only when _marketpayAbort finishes.
        // The 35s timer starts now, while the abort request is still open.
        let settled = false;
        const result = terminal._marketpayAbort("line-1").then((value) => {
            settled = true;
            return value;
        });

        // 20s of the shared deadline pass with the abort request still open.
        await advanceTime(20_000);
        await flush();
        assert.strictEqual(settled, false);

        // The abort is acknowledged. The method now waits on the payment with the same timer.
        abortCall.resolve({ status: "OK" });
        await flush();
        assert.strictEqual(settled, false);

        // The remaining 15s reach the original deadline. A timer restarted after
        // the abort returned would still be waiting.
        await advanceTime(MARKETPAY_ABORT_WAIT_MS - 20_000);
        // Check that the wait timed out. Awaiting result also means the abort finished.
        assert.strictEqual(await result, null);
        // Check that the payment was never resolved.
        assert.strictEqual(pending.isSettled(), false);
        // Check that the timeout reported the cancellation failure.
        assert.deepEqual(terminal.errors, [TIMEOUT_MESSAGE]);
    });

    QUnit.test("Hung abort request times out without resolving the payment", async function (assert) {
        const terminal = makeTerminal();
        const pending = trackPendingPayment(terminal);
        // The abort request never settles, so the deadline fires while it is still open.
        terminal._callMarketpay = () => makeDeferred();

        const result = terminal._marketpayAbort("line-1");
        await advanceTime(MARKETPAY_ABORT_WAIT_MS);

        assert.strictEqual(await result, null);
        await flush();
        // Check that the timeout did not resolve the payment.
        assert.strictEqual(pending.isSettled(), false);
        assert.deepEqual(terminal.errors, [TIMEOUT_MESSAGE]);
    });
});
