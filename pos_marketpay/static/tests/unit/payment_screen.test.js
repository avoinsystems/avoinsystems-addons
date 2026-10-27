import { describe, expect, test } from "@odoo/hoot";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import "@pos_marketpay/app/screens/payment_screen/payment_screen";

describe("pos_marketpay line cancel", () => {
    function makeScreen(sendPaymentCancel) {
        const line = {
            uuid: "line-1",
            status: "waitingCard",
            payment_method_id: {
                use_payment_terminal: "marketpay",
                payment_terminal: { sendPaymentCancel },
            },
            isDone() {
                return this.status === "done";
            },
            setPaymentStatus(value) {
                this.status = value;
            },
        };
        const screen = Object.create(PaymentScreen.prototype);
        // currentOrder is a getter. It looks the order up from the PoS models.
        screen.pos = {
            paymentTerminalInProgress: true,
            models: { "pos.order": { getBy: () => ({}) } },
        };
        screen.props = { orderUuid: "order-1" };
        screen.notifications = [];
        // Do not read the message. _t() throws when stringified because the
        // unit-test bundle has no translations loaded.
        screen.notification = {
            add(_message, options) {
                screen.notifications.push(options);
            },
        };
        return { screen, line };
    }

    test("Approved payment is not put back to waiting for card", async () => {
        const { screen, line } = makeScreen(function () {
            // The approval lands while the abort is in flight.
            line.status = "done";
            return Promise.resolve(false);
        });

        await screen.sendPaymentCancel(line);

        // Check that the paid line was left paid.
        expect(line.status).toBe("done");
        // Check that the late-approval warning was shown.
        expect(screen.notifications).toEqual([{ type: "warning" }]);
        expect(screen.pos.paymentTerminalInProgress).toBe(true);
    });

    test("Completed abort does not demote a line still waiting to be marked paid", async () => {
        const { screen, line } = makeScreen(() => Promise.resolve(false));

        await screen.sendPaymentCancel(line);

        // Check that the line stays as the cancel left it, so pay() can set it done.
        expect(line.status).toBe("waitingCancel");
        expect(screen.notifications).toEqual([{ type: "warning" }]);
    });

    test("Cancelled payment goes back to retry", async () => {
        const { screen, line } = makeScreen(() => Promise.resolve(true));

        await screen.sendPaymentCancel(line);

        // Check that the line can be retried.
        expect(line.status).toBe("retry");
        expect(screen.notifications).toEqual([]);
        expect(screen.pos.paymentTerminalInProgress).toBe(false);
    });

    test("Timed out cancel keeps the line waiting for card", async () => {
        const { screen, line } = makeScreen(() => Promise.resolve(null));

        await screen.sendPaymentCancel(line);

        // Check that a late result can still update the line.
        expect(line.status).toBe("waitingCard");
        expect(screen.notifications).toEqual([]);
        expect(screen.pos.paymentTerminalInProgress).toBe(true);
    });
});
