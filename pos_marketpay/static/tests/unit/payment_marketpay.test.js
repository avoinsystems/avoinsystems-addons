import { advanceTime, Deferred, describe, expect, microTick, test } from "@odoo/hoot";
import {
    MARKETPAY_ABORT_WAIT_MS,
    PaymentMarketpay,
} from "@pos_marketpay/app/utils/payment/payment_marketpay";

describe("payment_marketpay abort", () => {
    function makeTerminal() {
        const terminal = new PaymentMarketpay({ env: {} }, { id: 1 });
        terminal.errors = [];
        terminal._showError = (msg) => terminal.errors.push(msg);
        return terminal;
    }

    async function flush() {
        for (let i = 0; i < 8; i++) {
            await microTick();
        }
    }

    test("Cancelled payment returns true", async () => {
        const terminal = makeTerminal();
        const pending = new Deferred();
        // The abort request resolves at once. _marketpayAbort ignores its body.
        terminal._callMarketpay = () => Promise.resolve({ status: "OK" });
        // The in-progress payment for "line-1". sendPaymentRequest returns this same promise.
        terminal.marketpayPaymentLinePromises = { "line-1": pending };

        const result = terminal._marketpayAbort("line-1");
        // Let the resolved abort call finish, so the method is waiting on the payment.
        await flush();
        // The payment did not succeed, so the transaction was cancelled.
        pending.resolve(false);

        // Check that the abort reports the payment as cancelled.
        expect(await result).toBe(true);
        // Check that the timeout path did not run. Only that path calls _showError.
        expect(terminal.errors).toEqual([]);
    });

    test("Payment that completed anyway returns false", async () => {
        const terminal = makeTerminal();
        const pending = new Deferred();
        terminal._callMarketpay = () => Promise.resolve({ status: "OK" });
        terminal.marketpayPaymentLinePromises = { "line-1": pending };

        const result = terminal._marketpayAbort("line-1");
        await flush();
        // The payment succeeded.
        pending.resolve(true);

        // Check that the abort reports the payment as not cancelled.
        expect(await result).toBe(false);
        expect(terminal.errors).toEqual([]);
    });

    test("No pending payment returns true", async () => {
        const terminal = makeTerminal();
        terminal._callMarketpay = () => Promise.resolve({ status: "OK" });
        // No in-progress payment. It already resolved, for example while the dialog was open.
        terminal.marketpayPaymentLinePromises = {};

        // The abort request still runs, but there is no payment to wait for, so this returns true.
        expect(await terminal._marketpayAbort("line-1")).toBe(true);
        expect(terminal.errors).toEqual([]);
    });

    test("Connection failure during abort propagates", async () => {
        const terminal = makeTerminal();
        // The abort request fails. That stands in for an Odoo connection error.
        terminal._callMarketpay = () => Promise.reject(new Error("down"));
        // A payment is registered, but the failure happens before it is awaited.
        terminal.marketpayPaymentLinePromises = { "line-1": new Deferred() };

        // Check that the failure rejects the abort instead of returning true, false, or null.
        await expect(terminal._marketpayAbort("line-1")).rejects.toThrow("down");
        expect(terminal.errors).toEqual([]);
    });

    test("Abort request and pending payment share one deadline", async () => {
        const terminal = makeTerminal();
        const abortCall = new Deferred();
        const pending = new Deferred();
        let pendingSettled = false;
        pending.then(() => {
            pendingSettled = true;
        });
        // The abort request stays open until resolve() is called.
        terminal._callMarketpay = () => abortCall;
        terminal.marketpayPaymentLinePromises = { "line-1": pending };

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
        expect(settled).toBe(false);

        // The abort is acknowledged. The method now waits on the payment with the same timer.
        abortCall.resolve({ status: "OK" });
        await flush();
        expect(settled).toBe(false);

        // The remaining 15s reach the original deadline. A timer restarted after
        // the abort returned would still be waiting.
        await advanceTime(MARKETPAY_ABORT_WAIT_MS - 20_000);
        // Check that the wait timed out.
        expect(await result).toBe(null);
        // Check that the abort finished.
        expect(settled).toBe(true);
        // Check that the payment was never resolved.
        expect(pendingSettled).toBe(false);
        // Check that the timeout reported one error. Do not read the message:
        // _t() throws here because the unit-test bundle has no translations.
        expect(terminal.errors.length).toBe(1);
    });

    test("Hung abort request times out without resolving the payment", async () => {
        const terminal = makeTerminal();
        const pending = new Deferred();
        let pendingSettled = false;
        pending.then(() => {
            pendingSettled = true;
        });
        // The abort request never settles, so the deadline fires while it is still open.
        terminal._callMarketpay = () => new Deferred();
        terminal.marketpayPaymentLinePromises = { "line-1": pending };

        const result = terminal._marketpayAbort("line-1");
        await advanceTime(MARKETPAY_ABORT_WAIT_MS);

        expect(await result).toBe(null);
        await flush();
        expect(pendingSettled).toBe(false);
        expect(terminal.errors.length).toBe(1);
    });
});
