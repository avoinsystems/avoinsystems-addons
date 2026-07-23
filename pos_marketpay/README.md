# PoS — Market Pay (`pos_marketpay`)

## Steps

### Step 1: Upload market pay certificate files to the server

Odoo should be able to read these files and you need to configure paths to the files in the Market Pay payment method.

### Step 2: Install module

- `pos_marketpay`

![Apps: PoS - Market Pay (pos_marketpay) installed](static/description/readme_apps_list.png)

### Step 3: Configure Odoo

**Point of Sale / Configuration / Payment Methods**

Configure the payment method (for example **Market Pay**) with **Integration: Terminal** and **Integrate with: Market Pay**. Set **Path to Certificate**, **Path to Private Key**, and **Terminal Identifier** to valid server paths and values Odoo can use. Adjust **Language Code**, **Printer Available**, and **Test Mode** as needed.

![Payment method: Market Pay terminal settings](static/description/readme_payment_method.png)

### Step 4: Configure Terminal(s)

---

## Important Callback URL Requirement

Market Pay posts transaction updates back to your Odoo instance, so it is very important that Odoo’s `web.base.url` system parameter is set to a correct, publicly reachable URL (for example, no `localhost`).

For localhost testing, expose your Odoo instance to the internet so Market Pay can reach it, for example by using [ngrok](https://ngrok.com/).

---

## Notification Secret

Because the callback endpoint must be public, every notification URL we send to Market Pay carries a per-payment-method secret token. The endpoint rejects any incoming notification whose secret does not match the one stored on the payment method, which prevents anyone who guesses or learns a terminal identifier from forging payment-completed callbacks.

**Format of the URL we register with Market Pay:**

```
{web.base.url}/pos_marketpay/notification/{terminal_id}/{secret}/{transaction_id}
```

**Key facts:**

- The secret is **generated automatically** the first time a payment method is created. There is nothing to configure on the Market Pay side — the secret is part of the callback URL we hand to Market Pay with each transaction.
- It is **per payment method** (i.e. per terminal), so rotating one terminal’s secret does not affect the others.
- The endpoint uses a **constant-time comparison** to validate the secret and returns HTTP 403 on mismatch.
- The secret is stored on the payment method as **Notification Secret** (visible to ERP managers under the **Webhook Security** group on the payment-method form). It is masked by default.

**Rotating the secret:**

If you suspect a notification URL has leaked (for example, it appeared in a screen share, a chat message, or a third-party log), rotate it immediately:

1. Open the payment method form (**PoS → Configuration → Payment Methods**).
2. Under **Webhook Security**, click **Regenerate Secret** and confirm.
3. From that moment, all *new* transactions use the new secret automatically.

> **Heads-up:** Rotating the secret invalidates any Market Pay transaction that is *already in flight* — Market Pay will still call back with the old URL, and our endpoint will (correctly) reject it. Rotate during quiet periods if possible, or accept that any pending payments at the moment of rotation will need to be retried from the POS.

Rotations are recorded in the Odoo server log (the entry includes which payment method was rotated and which user did it), so the action is auditable after the fact.

---

## `waitTime` system parameter (`pos_marketpay.wait_time`)

The Market Pay Cloud API `process-transaction` and `cancel-transaction` endpoints accept a `waitTime` query parameter (in seconds). It controls **how long the Market Pay Cloud holds the HTTP request open** before responding with `202 Accepted` and continuing the transaction asynchronously via the notification callback. If the payment finishes on the terminal within `waitTime`, the client gets the final result inline; if not, Market Pay returns `202` and the final outcome arrives later on the callback URL described in the **Notification Secret** section.

This value is configured through the system parameter `pos_marketpay.wait_time` (default **`20`**, allowed range **`1..300`**). It is created automatically by the module (`data/ir_config_parameter.xml`) and can be edited under **Settings → Technical → Parameters → System Parameters**.

**Important — impact on Odoo workers in multi-terminal / multi-threaded environments:**

While an ECR call is in flight, the Odoo HTTP worker handling the POS request is **blocked** for up to `waitTime` seconds waiting for Market Pay to reply. Odoo has a **fixed pool of HTTP workers** (`--workers` / `--limit-request`), so a high `waitTime` combined with several payment terminals can quickly exhaust the pool:

- With, say, 4 HTTP workers and 4 cashiers each starting a card payment at the same time, **all workers can be occupied waiting on Market Pay** for up to `waitTime` seconds. During that window, other Odoo requests (POS UI, backend, other webhooks, even the Market Pay notification callback itself) will queue up or time out.
- The effect scales with the number of concurrently active terminals — the more terminals, the more likely worker starvation becomes.
- Setting `waitTime` **too low** (e.g. `1..5`) causes Market Pay to return `202` almost immediately for every transaction, which is safe for workers but means the POS almost always has to wait for the asynchronous notification callback to learn the outcome, so the cashier-visible latency does not really improve.
- Setting `waitTime` **too high** (e.g. close to the maximum of `300`) keeps workers tied up for long periods even when nothing is happening on the terminal (e.g. the customer walked away), which is what causes the delays described above.

**Recommendation:** keep the default of **`20`** seconds unless you have a specific reason to change it. If you do raise it, make sure the Odoo HTTP worker count is scaled accordingly (roughly: at least as many workers as concurrently active terminals, plus headroom for the notification callback and normal traffic). If you lower it, remember that the module still relies on the notification callback being reachable — see the **Important Callback URL Requirement** section above.

---

## What must an Odoo partner do when they need to enable the Market Pay integration for their customer?

1. The Odoo partner contacts **Market Pay** via [https://market-pay.com/en/contact](https://market-pay.com/en/contact) to request the Market Pay module for Odoo (currently supported versions are **17** and **19**). Module access and distribution follow Market Pay’s process.

2. The Odoo partner adds the module to their **customer’s** repository.

3. Market Pay (or the end customer) sends the **certificate** file and the **key** file to the Odoo partner. The Odoo partner adds these to the server.

4. The Odoo partner configures the integration in the customer’s **test** environment as follows:

   1. Install the Market Pay module.

   2. Go to **PoS → Configuration → Settings** and select **Automatically validate order** (this setting must be enabled for the integration to work correctly).

   3. Go to **PoS → Configuration → Payment Methods** and create a new one.

   4. Fill in the following fields for the payment method:

      - **Name:** This can be, for example, Market Pay. *Note:* If multiple payment terminals are in use, a separate payment method must be created for each terminal. In that case, it may be good to include, for example, the last two digits of the terminal’s serial number in the payment method name so it is clear which terminal is selected when paying in PoS.

      - **Integration:** Select **Terminal** here.

      - **Integrate with:** **Market Pay**.

      - **Path to Certificate:** The location of the Market Pay certificate file on the server. The certificate is customer-specific and can be obtained from Market Pay. *Important:* Market Pay requires a CSR (Certificate Signing Request) to issue the certificate. More information: [Cloud API integration](https://assist.market-pay.com/hc/en-us/articles/41507382201361-Cloud-API-integration?brand_id=10480669413777#h_01K6WEBVHDZN9S83XMZ6B8XPF5).

      - **Path to Private Key:** The same as above but for the key file.

      - **Terminal Identifier:** The payment terminal’s serial number. *Important:* The terminal identifier should be prefixed with the manufacturer code, for example: `PAX:12345678`.

      - **Test Mode:** This is selected when testing.

      - **Notification Secret** (under **Webhook Security**, manager-only): Generated automatically — you do not need to set or share this value with Market Pay. It secures the callback URL Market Pay uses to deliver transaction notifications. If it ever leaks, rotate it with the **Regenerate Secret** button. See the **Notification Secret** section above for details.

      - **Store Code** (behind Debug Mode): By filling this in and pressing the **Refresh** button, you can see which payment terminals are linked to the respective customer-specific store code. The Store Code can be obtained from Market Pay.

---

For licensing, see the **LICENSE** file in this module.
