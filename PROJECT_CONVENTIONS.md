# N Designs — Project conventions

This file records standing decisions made during development that are not obvious from the code alone. Check it before starting new UI work, and add a note here whenever a similar decision is made.

## UI/UX conventions

**Never use native browser dialogs.** Do not use `confirm()`, `alert()`, or `prompt()` anywhere in this project — admin or storefront. Any confirmation, warning, or input request must be a custom-styled in-app modal or toast that matches the current page's theme (Semi Dark charcoal for admin, the N Designs brand theme for storefront). This applies to all future features, not just category delete — if a future action (deleting a product, cancelling an order, etc.) needs user confirmation, reuse or extend the existing `confirm-modal.html` / `confirmAction()` helper in the admin, or build an equivalent for the storefront if one doesn't exist yet, rather than falling back to a native dialog.

Admin helper: `confirmAction({ title, message, confirmLabel, cancelLabel, danger })` → `Promise<boolean>`. Markup lives in `views/admin/components/confirm-modal.html` and is included from `views/admin/base.html`. Forms can opt in with `data-confirm` plus `data-confirm-title`, `data-confirm-message`, `data-confirm-label`, and optional `data-confirm-danger="false"` for a non-destructive confirm (uses `btn-admin-primary` instead of `btn-admin-danger`).

## Admin UI — Always Use the Template System

**Never hand-roll admin UI from scratch.** Every new admin screen (forms, tables, cards, buttons, inputs, uploads, alerts) MUST reuse the actual markup patterns and CSS classes already present in the `template/` Maxton kit, combined with the project's own overrides in `template/assets/css/n-designs-admin.css` (the `btn-admin-*` / `alert-admin-*` classes, the charcoal theme, etc.). Before building any new admin page, look at how a similar element already looks in `template/*.html` (raw Maxton reference) or in an already-built page like the Categories screens (project-approved reference) and match it exactly — same classes, same structure, same spacing conventions. Do not invent new unstyled HTML elements, new one-off CSS, or a different visual pattern for the same type of component (e.g. a form input, a button, a card) than what's already established elsewhere in the admin. If a needed component genuinely doesn't exist yet in either place, flag it for a design decision instead of guessing.

Approved references: Categories list/form (`views/admin/category/`), Maxton `form-layouts.html`, `form-elements.html`, `form-repeater.html`, `form-radios-and-checkboxes.html`, `table-basic-table.html`, `ecommerce-products.html`.

## Product pricing

`ProductVariant.price` is the regular price. `ProductVariant.compare_at_price` is the optional discounted selling price (UI label: **Discount**; column name unchanged). A variant is on sale when `compare_at_price IS NOT NULL AND compare_at_price < price`. When on sale, `compare_at_price` is what the customer pays and `price` is shown struck through. When the discount field is empty, `price` is the payable price.

## Checkout (COD MVP)

Checkout is `POST /checkout` in one DB transaction via shared `finalize_order()`: find-or-create Customer by email, create Order + OrderItems, apply a cart-level discount code if still valid (increment `DiscountCode.times_used`), decrement `ProductVariant.stock_quantity`, then delete `CartItem` rows and clear `Cart.discount_code_id` (the `Cart` row and `cart_session` cookie stay). After commit, order confirmation and admin new-order emails are queued with FastAPI `BackgroundTasks` — SMTP failure is logged server-side and never rolls back or blocks the order. Shipping is a flat **BHD 3.000** placeholder until real rates exist.

**Cash on Delivery** still finalizes immediately on submit. **Pay Online** creates a `PaymentSession` snapshot (cart lines, totals, customer, discount) and redirects to Tap’s hosted page (`source: src_all`). Stock, cart, and discount usage are not touched until Tap’s charge is `CAPTURED` and verified server-to-server on `GET /payment/callback/{token}`. Failed/abandoned payments leave the cart intact. The displayed payment method on those orders is `Card (Tap)`; `Order.tap_charge_id` is stored for admin/refund lookup. `TAP_SECRET_KEY` lives in `.env` and is never logged. `GET /order-confirmation/{order_id}` requires the owning customer to be logged in when `customer_id` is set; true guest orders (`customer_id` NULL) remain reachable by URL.

## Transactional email

SMTP settings live in `.env` (`MAIL_*`, `ADMIN_NOTIFICATION_EMAIL`, `SITE_URL`). `MAIL_PASSWORD` is never logged. Customer confirmation and admin new-order alerts are sent after checkout commit via `BackgroundTasks`. Templates are inline-styled HTML in `views/emails/` (email clients cannot use the site CSS). Header branding is the “N Designs” wordmark, not an embedded logo.

## URL conventions

Admin section pages live directly under `/admin/{section}`, not `/admin/dashboard/{section}`. Only the dashboard home page itself is `/admin/dashboard`.

Examples: `/admin/categories`, `/admin/categories/new`, `/admin/products`, `/admin/orders`, `/admin/discount-codes`, `/admin/customers`, `/admin/settings`. Login stays `/admin/login`.

## Customers admin

The customers screen is **read-only**. There is no create, edit, or delete — rows come from storefront registration or checkout. Guest vs Registered is whether `hashed_password` is set. Order counts are a single aggregated query; the count links to `/admin/orders?customer_id={id}`.

## Discount codes

Codes are stored uppercase; `summer20` and `SUMMER20` are the same code. There is **no delete** — deactivate (`Active` off) to retire a code, same reasoning as Orders. `times_used` is incremented inside the order-creation transaction (row locked with `FOR UPDATE`) so a failed checkout never counts and two concurrent checkouts cannot both consume the last remaining use.

A code applied on the cart is stored as `Cart.discount_code_id` and carries into checkout automatically. On the Order, `discount_code_id` remains the live FK and `discount_code_snapshot` stores the code string used at checkout (same idea as `price_at_purchase`). Historical order screens and emails display the snapshot, not the current DiscountCode code. Invalid / inactive / maxed-out codes get a generic storefront toast: **“This code is invalid or has expired”** — do not reveal why (max uses, inactive, unknown). If a code becomes invalid between apply and submit, checkout removes it, recalculates without it, and asks the customer to review the total rather than placing the order.

When `applies_to_sale_items` is off, the percentage applies only to line items that are not on sale (`compare_at_price` is missing or not lower than `price`). Sale-line payables stay at the sale price. Shipping is added after the discount.
