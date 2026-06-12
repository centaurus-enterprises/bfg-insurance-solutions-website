# Brown Financial Group — Project Summary

A family-run independent life insurance brokerage website with a Flask + PostgreSQL backend,
agent dashboard, and lead management system. Built by Josh and John Brown under Symmetry
Financial Group (IMO).

---

## Status

| Area | Status |
|---|---|
| Frontend (all pages) | ✅ Complete |
| Flask backend | ✅ Complete locally |
| PostgreSQL schema | ✅ Complete locally |
| Agent login + dashboard | ✅ Complete |
| Lead notifications (Gmail SMTP) | ✅ Complete |
| Thank you page | ⬜ Not built |
| Calendly redirect on book_appointment | ⬜ Not wired |
| DigitalOcean deployment | ⬜ Not started |
| Domain cutover (GoDaddy → DO) | ⬜ Not started |

---

## Tech Stack

**Frontend:** Pure HTML/CSS/JS — no frameworks. Raleway (headings) + DM Sans (body) via
Google Fonts. One shared `style.css` using CSS custom properties throughout.

**Backend:** Python 3.12, Flask, PostgreSQL 16. psycopg2 for DB connection. python-dotenv
for environment variables. Flask-CORS enabled. Gmail SMTP for lead notifications.

**Local dev:** VS Code + Live Server (frontend). Flask on port 5000 (backend). pgAdmin 4
for DB inspection.

**Deployment target:** DigitalOcean VPS + Nginx (reverse proxy) + Gunicorn (WSGI server).
Domain registered on GoDaddy — DNS will point to DO droplet.

---

## File Structure

```
/ (project root)
├── index.html
├── about.html
├── careers.html
├── products.html
├── qualify.html               ← main lead intake form
├── mortgage_protection.html
├── term_life.html
├── whole_life.html
├── final_expense.html
├── iul.html
├── living_benefits.html
├── login.html                 ← agent login
├── dashboard.html             ← lead management dashboard (dark mode)
├── settings.html              ← agent management (admin only)
├── style.css                  ← all frontend styles
├── app.py                     ← Flask application
├── db.py                      ← PostgreSQL connection helper
├── create_agent.py            ← CLI script to create agent accounts
├── pyvenv.cfg / activate.bat  ← Python venv
└── _env                       ← rename to .env before deployment
```

---

## Design System

All colors are CSS variables defined in `style.css`:

```css
--espresso:   #4B2E2B   /* headings, footer, CTA banners */
--cognac:     #C08552   /* buttons, key interactive elements */
--saddle:     #8C5A3C   /* accents, borders, eyebrows */
--parchment:  #FFF8F0   /* page backgrounds */
```

Typography: Raleway for headings, DM Sans for body copy.
Icons: Feather-style inline SVGs (no icon library dependency).

---

## Pages

- **index.html** — Homepage. Hero, trust bar (carrier logos), product overview cards, CTA.
- **about.html** — Agency story, principals (Josh + John Brown), values.
- **careers.html** — Agent recruiting page with application form (not wired to backend yet).
- **products.html** — Product catalog with all 6 product cards.
- **qualify.html** — 4-section lead intake form. Conditional Section 2 modules per product.
  URL param detection (`?product=mortgage-protection`) for ad traffic routing. POSTs JSON
  to `http://localhost:5000/submit` (update to production URL on deploy).
- **mortgage_protection.html / term_life.html / whole_life.html / final_expense.html /
  iul.html / living_benefits.html** — Individual product education pages.
- **login.html** — Agent login. POSTs to `/login`.
- **dashboard.html** — Lead table with inline expand, status updates, notes, CSV/XLSX
  export, delete. Dark mode. Admin agents see all leads; non-admin see only their own.
- **settings.html** — Add/deactivate/reactivate agents. Admin only.

---

## Backend Routes (app.py)

| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/submit` | Public | Saves lead from qualify form to DB, fires email notification |
| GET/POST | `/login` | Public | Agent login, sets session cookie |
| GET | `/logout` | Login | Clears session |
| GET | `/dashboard` | Login | Renders dashboard with leads |
| POST | `/leads/<id>/status` | Login | Updates lead status |
| POST | `/leads/<id>/notes` | Login | Saves call notes |
| DELETE | `/leads/<id>` | Login | Deletes lead |
| POST | `/export` | Login | Returns CSV or XLSX of selected leads |
| GET | `/settings` | Admin | Renders settings page |
| GET | `/agents` | Admin | Returns agent list as JSON |
| POST | `/agents` | Admin | Creates new agent |
| POST | `/agents/<id>/deactivate` | Admin | Deactivates agent |
| POST | `/agents/<id>/reactivate` | Admin | Reactivates agent |

---

## Database Schema (PostgreSQL)

Database name: `brown_agency` (local) — update name in `.env` for production.

**leads** — one row per form submission from qualify.html  
Key columns: `id`, `first_name`, `last_name`, `age`, `email`, `mobile_phone`, `state`,
`product_type`, `contact_preference`, `best_time`, `hobby`, `status`, `notes`,
`submitted_at`, plus product-specific fields for all 6 product modules and medical fields
(tobacco, height_ft, height_in, weight, major_conditions, minor_conditions, medications).

**agents** — one row per agent account  
Key columns: `id`, `full_name`, `email`, `username`, `password_hash`, `is_admin`,
`is_active`, `notify_on_lead`, `created_at`.

**sessions** — Flask session management table.

---

## Environment Variables

Rename `_env` → `.env` and fill in values before running locally or deploying:

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=brown_agency
DB_USER=postgres
DB_PASSWORD=your_password

SECRET_KEY=generate_with_secrets.token_hex(32)

MAIL_SENDER=your_gmail@gmail.com
MAIL_PASSWORD=your_gmail_app_password   # Gmail App Password, not account password
```

Email notifications are silently skipped if `MAIL_SENDER` / `MAIL_PASSWORD` are unset.

---

## What's Left

### 1. Thank You Page (`thank_you.html`)
After successful form submission, redirect to a thank you page. The redirect is already
stubbed out in `qualify.html` (search for `// window.location.href = 'thank_you.html'`).

Two cases to handle:
- `contact_preference === 'call_me'` → standard thank you message
- `contact_preference === 'book_appointment'` → redirect to Calendly URL

Pass the preference as a URL param: `thank_you.html?pref=book_appointment`

### 2. Careers Form Backend
`careers.html` has a working front-end form but `submitApplication()` is not wired to
any backend route. Needs a `/apply` route in `app.py` and a separate `applications` table,
or just email delivery similar to lead notifications.

### 3. DigitalOcean Deployment
Recommended sequence:
1. Create Ubuntu 22.04 droplet on DigitalOcean
2. Install Python 3.12, PostgreSQL 16, Nginx, Certbot
3. Clone repo to `/var/www/brown-agency/`
4. Create `.env` with production credentials
5. Run `create_agent.py` to seed the first admin account
6. Set up Gunicorn as a systemd service (`brown-agency.service`)
7. Configure Nginx to reverse-proxy `localhost:5000` and serve static HTML files directly
8. Point GoDaddy DNS A record to droplet IP
9. Run Certbot for SSL (`sudo certbot --nginx -d yourdomain.com`)
10. Update `qualify.html` fetch URL from `http://localhost:5000/submit` to production URL

### 4. qualify.html Production URL
Search for `http://localhost:5000/submit` in `qualify.html` and update to the production
domain before go-live.

---

## Agency Context

- **Agency:** Brown Financial Group (also considering Brown Financial Group)
- **Principals:** Josh Brown (tech + sales) and John Brown (sales)
- **IMO:** Symmetry Financial Group
- **Licensed:** California-based, nationwide
- **Carrier partners:** Mutual of Omaha, Foresters Financial, Americo, North American,
  Royal Neighbors, Gerber Life
- **Target client:** Someone ready to get coverage who needs a trustworthy guide —
  not a high-pressure sales experience
- **Tagline direction:** "A family helping families"

---

## Editorial Standards

These apply to any copy added to the site:

- Write as a knowledgeable industry professional — impartial and informative, not salesy
- Avoid: em-dash sentence structures, "possibly yes"-style openers, promotional closing lines
- Only name specific carriers when citing a verifiable, specific product feature
- Comparative content (e.g. IUL vs. alternatives) should accurately represent where
  competing products outperform — not just upsell
- Each page's layout should adapt to its content, not follow a rigid template
