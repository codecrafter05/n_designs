# N Designs — Roadmap

This file holds future feature ideas that are **not yet decided in detail** and **not yet started**. It is separate from `PROJECT_CONVENTIONS.md`, which records binding standing rules already in effect.

## Known Limitations

- Order confirmation (`/order-confirmation/{id}`): orders tied to a customer account require that customer to be logged in. Unauthenticated guest orders (`customer_id` NULL) still have no access control — anyone with the URL can view them.

## Deferred Features

### Loyalty Points

- Every purchase earns the customer points from an admin-configurable conversion rate (e.g. `1 BHD = 50 points` or `10 BHD = 50 points`). The ratio is a single admin-settable value, not hardcoded.
- Points accumulate in a per-customer balance ("wallet") tied to the Customer record.
- Will need: a conversion-rate setting (likely in the future Settings section), a points balance field/table on Customer, and automatic credit when an Order is marked complete/paid (exact trigger TBD when built).
- Not started. No schema exists for this yet.

### Discount Codes

- Admin creates a discount code with: a code name/string, a maximum number of uses (usage limit), and a discount percentage applied to the order total.
- Will need: a `DiscountCode` model (`code`, `percentage`, `max_uses`, `times_used`, `is_active`, expiry TBD), plus checkout logic to validate/apply a code at the cart or checkout step.
- Not started. No schema exists for this yet.
