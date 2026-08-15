# N Designs — Discovery Report

**Date:** 15 August 2026  
**Scope:** Read-only map of the current FastAPI repo, plus a staging copy of the new storefront.  
**No app/ or `template/` files were edited.**

Source of the new frontend (originals left in place):  
`/Users/millionaire/Documents/PROJECT/N Designs/files/`

---

## Part 1 — Backend map

### 1. Entry point

| Item | Detail |
|---|---|
| Boot file | `run.py` |
| What it does | Calls `uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)` |
| FastAPI instance | `app` in `app/main.py` |
| Host / port | Hardcoded in `run.py`: `127.0.0.1:8000` (not read from `.env`) |
| Config source | `app/core/config.py` → pydantic-settings `Settings` class, loaded from `.env` |
| Env vars used | `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES` |
| Built URL | `DATABASE_URL` is computed as `mysql+pymysql://user:quoted_password@host:port/dbname` |
| Lifespan | Empty `lifespan` context manager in `app/main.py` (startup/shutdown do nothing) |
| App metadata | `title="Pod Café POS"`, `version="1.0.0"`, description says “coffee shop point-of-sale backend” |

There is no `app/__init__.py`. Uvicorn loads `app.main:app` as a package because `app/` is a directory with modules.

---

### 2. Routing

There is **no** router under `views/`. `views/` is Jinja2 HTML only. All routes live under `app/`.

#### JSON API — prefix `/api/v1`

Mounted in `app/main.py` via `app.include_router(router)` from `app/api/v1/router.py`.

| Module | Prefix | Method | Path | Auth | Returns |
|---|---|---|---|---|---|
| `app/api/v1/endpoints/health.py` | `/api/v1` | GET | `/api/v1/health` | none | JSON `{status: ok}` |
| `app/api/v1/endpoints/health.py` | `/api/v1` | GET | `/api/v1/db-check` | none | JSON connected / 503 |
| `app/api/v1/endpoints/auth.py` | `/api/v1/auth` | POST | `/api/v1/auth/login` | none | JSON JWT |
| `app/api/v1/endpoints/auth.py` | `/api/v1/auth` | GET | `/api/v1/auth/me` | Bearer JWT | JSON user |

#### HTML (Jinja2) — no URL prefix

Mounted in `app/main.py` via `app.include_router(web_router)` from `app/api/v1/endpoints/web.py`. Hidden from Swagger (`include_in_schema=False`).

| Route | Handler | Template |
|---|---|---|
| `GET /` | redirect to `/login` | — |
| `GET /login` | `login_page` | `views/login.html` |
| `GET /dashboard` | `dashboard_page` | `views/dashboard.html` |

There are **no** storefront routes yet (`/`, `/about`, `/products`, `/cart`, etc. as shop pages). `/` currently goes to the admin login.

FastAPI also exposes `/docs` and `/redoc` automatically.

---

### 3. Templating

**Important correction vs the prompt:** live Jinja2 templates are in `views/`, not `template/`.

| Folder | Role |
|---|---|
| `views/` | Actual Jinja2 templates wired to FastAPI |
| `template/` | Vendor **Maxton** Bootstrap 5 admin kit (static HTML demos + CSS/JS/images). FastAPI does **not** render these HTML files. |

Jinja2 is created in `app/api/v1/endpoints/web.py`:

```python
templates = Jinja2Templates(directory=<project_root>/views)
```

#### Inheritance

```
views/login.html          standalone (does not extend base)
views/base.html           layout: head, header include, sidebar include, content block, footer, auth JS
  └── views/dashboard.html    {% extends "base.html" %}
views/components/header.html   {% include %} from base
views/components/sidebar.html  {% include %} from base
```

**Blocks in `base.html`:** `title`, `extra_css`, `content`, `extra_js`.

`login.html` is a separate full page (no sidebar/header). After login it stores a JWT in `localStorage` and redirects to `/dashboard`.

---

### 4. Static files

Mounted in `app/main.py`:

| URL prefix | Disk folder |
|---|---|
| `/assets` | `template/assets/` |
| `/sass` | `template/sass/` |

On disk:

```
template/
  assets/
    css/          bootstrap, pace, bootstrap-extended, extra-icons
    js/           jquery, bootstrap.bundle, pace, main.js, unused dashboard JS
    images/       favicon, logo-icon.png, logo1.png, auth/, avatars/, gallery/, …
    plugins/      metismenu, simplebar, perfect-scrollbar, apexchart, + many unused
    fonts/        boxicons, LineIcons
  sass/           main / dark / blue / semi-dark / bordered / responsive (.css + .scss)
  *.html          ~80 vendor demo pages (not served as Jinja)
```

Live admin pages only pull a small subset (see Part 3). There is **no** mount yet for the new storefront `files/static/`.

---

### 5. Admin dashboard

There is no separate `admin/` package. The current “admin” **is** the whole HTML app.

| Piece | Location |
|---|---|
| Layout | `views/base.html` |
| Page | `views/dashboard.html` |
| Nav | `views/components/sidebar.html` |
| Top bar | `views/components/header.html` |
| Login | `views/login.html` |

**Protection**

- **No FastAPI middleware. No server-side check on `/dashboard`.** Anyone can load the HTML.
- Guard is client-side in `base.html`: if `localStorage.access_token` is missing → redirect to `/login`.
- API protection is JWT Bearer on `GET /api/v1/auth/me` only. Login itself is public.
- Email shown in the UI is decoded from the JWT `sub` claim in the browser, not fetched from `/me`.

**UI structure**

- Maxton “blue-theme” admin chrome: top header + left sidebar + `main-wrapper`.
- Sidebar brand: Maxton `logo-icon.png` + text **“Pod Café”**.
- Sidebar items: Dashboard (only real link), then placeholder `javascript:;` items for a **café POS**: New Order, Orders, Menu, Tables, Staff, Reports, Inventory, Settings, Logout.
- Header: search (“Search orders…”), fake notifications (coffee orders), avatar dropdown (“Pod Café Staff”).
- Dashboard body: hardcoded café KPIs (IQD revenue, tables, cappuccino/latte, recent orders). Not bound to the database.

---

### 6. Database layer

**Models:** `app/models/user.py` only.

`User` → table `users`: `id`, `email` (unique), `hashed_password`, `is_active`, `created_at`, `updated_at`.

Exported from `app/models/__init__.py`. No Product, Category, Order, Cart, or Customer models.

**Engine / sessions:** `app/core/database.py` — SQLAlchemy 2 engine, `SessionLocal`, `get_db()`, `check_db_connection()`.

**Auth helpers:** `app/core/security.py` — bcrypt + JWT (`HS256`, expiry from `.env`).

**Alembic**

| File | Role |
|---|---|
| `alembic.ini` | `script_location = alembic`; `sqlalchemy.url` is a placeholder |
| `alembic/env.py` | Overrides URL from `settings.DATABASE_URL`; imports `app.models` so metadata is registered |
| `alembic/versions/bfdba3781ae2_create_users_table.py` | Only migration. Creates `users` + indexes. `down_revision = None` |

No product/order migrations exist.

**Seed script:** `scripts/create_admin.py` — create/update a user from `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

---

## Part 2 — Current branding references

### Names in use

| Name | Where it belongs |
|---|---|
| **Pod Café** / **Pod Café POS** | Live app title, login, dashboard, sidebar, footer, FastAPI metadata |
| **podcafe** | Default admin email domain in `scripts/create_admin.py` |
| **poscafe** | Example DB user/name in `.env.example` |
| **Maxton** | Vendor admin kit titles/sidebar in `template/*.html` (not rendered by FastAPI) |
| **FastAPI + MySQL Starter** | README boilerplate title |

No email templates, invoice/PDF templates, or old public domain (e.g. `podcafe.com`) were found in the live app.  
`template/app-invoice.html` and `template/app-emailbox.html` are vendor demos only.

`.env` is gitignored and already uses `n_designs` — not listed below.

### Live app + config (every occurrence)

| File | Line | What it is | Suggested replacement |
|---|---|---|---|
| `app/main.py` | 19 | FastAPI `title="Pod Café POS"` | `title="N Designs"` |
| `app/main.py` | 21 | Description: coffee shop POS backend | Clothing e-commerce backend for N Designs |
| `views/base.html` | 6 | Default `<title>`: Pod Café | N Designs |
| `views/base.html` | 7 | Favicon: Maxton `favicon-32x32.png` | N Designs favicon (from new logos) |
| `views/base.html` | 41 | Footer: `Pod Café POS © 2026` | `N Designs © 2026` |
| `views/login.html` | 6 | `<title>Pod Café — Login` | `N Designs — Login` (or Admin Login) |
| `views/login.html` | 7 | Same Maxton favicon | N Designs favicon |
| `views/login.html` | 29 | Heading `☕ Pod Café` | N Designs (use logo-dark.png) |
| `views/login.html` | 41 | Placeholder `admin@example.com` | e.g. `admin@n-designs` / keep generic |
| `views/dashboard.html` | 3 | Title `Pod Café — Dashboard` | `N Designs — Dashboard` |
| `views/dashboard.html` | 9 | Breadcrumb brand `Pod Café` | N Designs |
| `views/components/sidebar.html` | 4 | Logo image `/assets/images/logo-icon.png` (Maxton) | N Designs logo (dark) |
| `views/components/sidebar.html` | 7 | Sidebar text `Pod Café` | N Designs |
| `views/components/header.html` | 74 | Dropdown subtitle `Pod Café Staff` | N Designs Staff / Admin |
| `scripts/create_admin.py` | 5 | Doc example `admin@podcafe.local` | `admin@n-designs.local` (or real ops email) |
| `scripts/create_admin.py` | 21 | Default `ADMIN_EMAIL` `admin@podcafe.local` | `admin@n-designs.local` |
| `.env.example` | 4 | `DB_USER=poscafe` | `DB_USER=n_designs` |
| `.env.example` | 6 | `DB_NAME=poscafe` | `DB_NAME=n_designs` |
| `README.md` | 1 | Title `FastAPI + MySQL Starter` | N Designs |
| `README.md` | 3 | “boilerplate” / generic starter copy | N Designs clothing e-commerce |

### Logo files currently on disk

| File | Used by |
|---|---|
| `template/assets/images/logo-icon.png` | Admin sidebar (`views/components/sidebar.html`) |
| `template/assets/images/logo1.png` | Vendor kit only (not referenced by `views/`) |
| `template/assets/images/favicon-32x32.png` | `views/base.html`, `views/login.html` |
| `files/logo-dark.png` | New storefront originals |
| `files/logo-light.png` | New storefront originals |
| `files/static/img/logo/logo-dark.png` | Staging copy (Part 4) |
| `files/static/img/logo/logo-light.png` | Staging copy (Part 4) |

### Vendor kit branding (not live)

All ~80 files under `template/*.html` use:

- `<title>Maxton | Bootstrap 5 Admin Dashboard Template</title>` (usually line 6–9)
- Sidebar text `Maxton` (usually ~line 633–636)
- `assets/images/logo-icon.png` and `assets/images/favicon-32x32.png`

These pages are **not** Jinja-rendered. Treat as vendor leftovers, not product brand — unless you keep the kit as a design reference.

### New storefront (already branded N Designs)

Files under `files/*.html` already say **N Designs** in titles and `alt` text. They are not old-brand leftovers. Placeholder contact: `https://wa.me/97300000000` (Bahrain country code, dummy number).

---

## Part 3 — Dead / unnecessary candidates

Nothing below was deleted. Items marked **UNSURE** should not be removed without a decision.

### 1. Routes / endpoints

| Item | Reason | Verdict |
|---|---|---|
| `GET /api/v1/auth/me` | Defined and documented; **no template or JS calls it**. UI reads email from the JWT instead. | Keep for API; unused by current UI |
| `GET /api/v1/health` | Not linked from nav/templates | Keep — ops check |
| `GET /api/v1/db-check` | Not linked from nav/templates | Keep — ops check |
| Sidebar: New Order, Orders, Menu, Tables, Staff, Reports, Inventory, Settings | `href="javascript:;"` — **no matching routes exist** | Not dead code; unfinished café POS chrome to replace |

No `/test`, `/demo`, or `/example` app routes.

### 2. Orphaned templates

| Item | Reason |
|---|---|
| `views/*` | All five files are used. None orphaned. |
| `template/*.html` (~80 files) | Never passed to `TemplateResponse`. Vendor demos only. |

**UNSURE:** deleting the whole `template/*.html` set is safe for the running app, but you may want to keep a few (e.g. `ecommerce-*.html`) as visual reference for a future admin.

### 3. Commented-out / unused Python (best-effort)

| Item | Reason | Verdict |
|---|---|---|
| `app/main.py` empty `lifespan` | Does nothing | Harmless; **UNSURE** if you want a hook later |
| Python unused imports | None found in `app/` | — |
| Large commented-out blocks in `app/` | None found | — |
| Alembic `# ### commands auto generated` | Standard Alembic markers | Keep |

### 4. Boilerplate / demo content

| Item | Reason it looks leftover |
|---|---|
| `views/dashboard.html` | Fake café metrics: IQD 245K, 6/12 tables, Cappuccino/Latte/Espresso/Croissant, orders #1038–#1042, staff Ahmad/Sara |
| `views/components/header.html` | Fake notifications: Order #1042, espresso beans stock |
| `views/components/sidebar.html` | Entire café POS menu (tables, coffee, inventory) |
| `views/login.html` | Coffee emoji + café name; illustration `/assets/images/auth/login1.png` |
| `scripts/create_admin.py` | Default `admin@podcafe.local` |
| README | Generic “starter boilerplate” copy |

Safe to rewrite for N Designs. Not “delete the files” — replace the content.

### 5. Unused static assets

**Referenced by live `views/`** (keep while admin still uses Maxton chrome):

- CSS: `pace.min.css`, `bootstrap.min.css`, `bootstrap-extended.css`
- Sass: `main`, `dark-theme`, `blue-theme`, `semi-dark`, `bordered-theme`, `responsive`
- JS: `pace.min.js`, `jquery.min.js`, `bootstrap.bundle.min.js`, `main.js`
- Plugins: perfect-scrollbar, metismenu, simplebar, apexcharts
- Images: `favicon-32x32.png`, `logo-icon.png`, `auth/login1.png`, `avatars/01.png`, `gallery/welcome-back-3.png`

**Not referenced by any `views/` file** (safe-looking removal *if* you drop the vendor kit):

| Path | Why it looks unused |
|---|---|
| `template/*.html` (all ~80) | Not rendered |
| `template/assets/js/index.js`, `index2.js`, `dashboard1.js`, `dashboard2.js`, `data-widgets.js` | Vendor dashboard scripts; `views/` never include them |
| `template/assets/css/extra-icons.css` | Not linked |
| `template/assets/plugins/vectormap/` | No map page |
| `template/assets/plugins/select2/` | No select2 |
| `template/assets/plugins/datatable/` | No datatable page |
| `template/assets/plugins/chartjs/` | Dashboard uses Apex, not Chart.js |
| `template/assets/plugins/gmaps/`, `fullcalendar/`, `form-repeater/`, `fancy-file-uploader/`, `bs-stepper/`, `input-tags/`, `validation/`, `notifications/`, `peity/` | Vendor-only |
| `template/assets/images/apps/`, `bg-themes/`, `carousels/`, `cat/`, `county/`, `megaIcons/`, `orders/`, `projects/`, `top-products/` | Demo image packs |
| `template/assets/images/logo1.png` | Not used by views |
| `template/sass/*.scss` and `*.css.map` | App links compiled `.css` only |

**UNSURE:** `template/assets/js/main.js` is required today (sidebar/PerfectScrollbar). Do not remove it until the admin chrome is replaced. `base.html` even includes a hidden `.search-content` stub so `main.js` does not crash.

---

## Part 4 — New frontend staging folder

**Done.** `app/` and `template/` were not touched.

Originals remain at:

```
files/index.html
files/about.html
files/category.html
files/products.html
files/product.html
files/cart.html
files/checkout.html
files/terms.html
files/404.html
files/style.css
files/script.js
files/logo-dark.png
files/logo-light.png
```

Copies + path updates:

```
files/
  pages/          9 HTML pages (paths updated)
  static/
    css/style.css
    js/script.js          (logo swap paths updated so they work from pages/)
    img/logo/
      logo-dark.png
      logo-light.png
```

In each copied HTML page only:

- `style.css` → `../static/css/style.css`
- `script.js` → `../static/js/script.js`
- `assets/logo-dark.png` → `../static/img/logo/logo-dark.png`
- `assets/logo-light.png` → `../static/img/logo/logo-light.png`

No other markup in those copies was changed. Page-to-page links (`index.html`, `cart.html`, …) still assume files sit next to each other inside `pages/`.

**Note:** the copied `script.js` also had hardcoded `assets/logo-*.png` (hero nav swap). Those two strings were updated in the **copy only**, otherwise the logo would 404 when opening `files/pages/index.html` in a browser. The original `files/script.js` is unchanged.

To preview the staging storefront, open:

`/Users/millionaire/Documents/PROJECT/N Designs/files/pages/index.html`

---

## Stop

Discovery only. No renames, deletions, or FastAPI wiring of the new pages until you review this report and send the next prompt.
