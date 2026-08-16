# N Designs — Project conventions

This file records standing decisions made during development that are not obvious from the code alone. Check it before starting new UI work, and add a note here whenever a similar decision is made.

## UI/UX conventions

**Never use native browser dialogs.** Do not use `confirm()`, `alert()`, or `prompt()` anywhere in this project — admin or storefront. Any confirmation, warning, or input request must be a custom-styled in-app modal or toast that matches the current page's theme (Semi Dark charcoal for admin, the N Designs brand theme for storefront). This applies to all future features, not just category delete — if a future action (deleting a product, cancelling an order, etc.) needs user confirmation, reuse or extend the existing `confirm-modal.html` / `confirmAction()` helper in the admin, or build an equivalent for the storefront if one doesn't exist yet, rather than falling back to a native dialog.

Admin helper: `confirmAction({ title, message, confirmLabel, cancelLabel, danger })` → `Promise<boolean>`. Markup lives in `views/admin/components/confirm-modal.html` and is included from `views/admin/base.html`. Forms can opt in with `data-confirm` plus `data-confirm-title`, `data-confirm-message`, `data-confirm-label`, and optional `data-confirm-danger="false"` for a non-destructive confirm (uses `btn-admin-primary` instead of `btn-admin-danger`).

## URL conventions

Admin section pages live directly under `/admin/{section}`, not `/admin/dashboard/{section}`. Only the dashboard home page itself is `/admin/dashboard`.

Examples: `/admin/categories`, `/admin/categories/new`, `/admin/products`, `/admin/orders`, `/admin/customers`, `/admin/settings`. Login stays `/admin/login`.
