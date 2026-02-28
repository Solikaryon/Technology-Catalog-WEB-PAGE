# Flask Technology Catalog — Documentation

Summary
-------
Small Flask application to browse and display tables related to technologies and proposals.
This application was developed for Jabil to support technology and proposal visualization workflows.
It provides:
- Main view (`/`) with a list of technologies.
- Search view (`/search`) to filter equipment by PCB size / thickness / weight.
- Proposal viewer (`/propuestas`) that shows `Proposal_*` tables with an image row and measurement tooltips.
- Auxiliary admin pages under `/admin`.

Requirements
------------
- Python 3.9+
- Main packages: `Flask`, `pandas`, `werkzeug`, and `xlsxwriter`/`openpyxl` for Excel export.

If you do not have `requirements.txt`, install the minimum dependencies:

```powershell
pip install Flask pandas werkzeug xlsxwriter openpyxl
```

Project structure
-----------------
- `app.py`: main Flask app and routes.
- `db.py`: helper to get the database connection (configured by you).
- `templates/`: Jinja templates (`_site_header.html`, `_site_footer.html`, `index.html`, `propuestas.html`, `search.html`, `tecnologia.html`, `admin.html`).
- `static/`:
  - `style.css` - global styles
  - `img/` - icons and logos (includes `Jabilito.png`, `Jabil.svg`, `placeholder.svg`, etc.)
  - `js/` - client-side scripts (`admin.js`, `loading.js`, `popover.js`, `proposal_builder.js`)

Setup and run
-------------
1. Create/activate a virtual environment (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies (if `requirements.txt` exists):

```powershell
pip install -r requirements.txt
```

3. Run the application (development mode):

```powershell
python app.py
```

The app will be served at `http://0.0.0.0:5000`.

Important: Change `app.secret_key` in `app.py` to a secure value before deploying.

How it works (technical summary)
--------------------------------
- Main routes:
  - `/`: lists technologies (reads from `Tecnologias_Tecnologias`).
  - `/search`: form and results; also searches technical tables and can return related proposals.
  - `/propuestas`: looks for tables whose names contain `PROPOSAL` and renders them as cards; it **inserts an image row in each table** (first row after the header) with one `img` per column and a `data-info` attribute containing dimensions and metadata.
  - `/tecnologia` and `/tecnologia_inline`: show tables by technology (used by index for inline loading).
  - `/image_for_headers`: POST endpoint that returns a header -> image mapping (used by the JS preview).

- Image logic:
  - `detect_image_in_column(df, col)` in `app.py` tries to detect data URI values, URLs, or file names in the table column and uses them directly when available.
  - `resolve_tech_image_src(header)` returns a static icon path based on heuristics from the header name (e.g., `KohYoungAoi.png`, `Conveyor.png`, `7Aimex.png`, etc.).
  - To add more icons, place the file in `static/img/` and extend `resolve_tech_image_src` in `app.py` to map the desired header.

- Proposal measurement tooltips:
  - In `/propuestas`, the code now uses `get_equipment_pcb_sizes(header, conn)` to collect Min/Max PCB, variants (M/L/XL), thickness, and weight, then injects this data into `img` `data-info` for UI display.

Client interactions
-------------------
- `proposal_builder.js` and `popover.js` control the proposal preview modal interactions. The modal uses `img` `data-info` to display details.
- A global helper was added for loading overlay: `window.showAppLoading()` / `window.hideAppLoading()` (implemented in `_site_footer.html`). The script also intercepts same-origin links, form submissions, and `fetch`/XHR requests to show the loading screen automatically.

Header and Jabilito adjustments
-------------------------------
- `templates/_site_header.html` includes the `Jabil.svg` logo and `Jabilito.png` image. `title` and `aria-label` were added for tooltip/accessibility, and `Jabilito` was wrapped in `<a href="/">` to navigate to the main menu.
- To improve visibility in dark theme, you can adjust styles in `static/style.css` (suggestions below).

Improve logo visibility in dark theme
-------------------------------------
In `static/style.css`, you can add rules like this (example):

```css
/* Increase saturation and add a subtle shadow in dark mode */
body.dark-mode .site-logo {
  filter: saturate(1.2) brightness(1.05);
  transition: filter .18s ease;
}
body.dark-mode .jabilito-img {
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5)) saturate(1.15);
}
```

Tune `saturate()` and `brightness()` as needed; if you want this to apply only to SVG or PNG, add more specific selectors.

Add/update icons
----------------
- Add the file to `static/img/` (e.g., `MyVendor.png`).
- Edit `resolve_tech_image_src(header)` in `app.py` to return `/static/img/MyVendor.png` when the header matches your rules.

Debugging and common issues
---------------------------
- Jinja templates with embedded JS: avoid nested quotes; use `data-` attributes to pass values or `|tojson` for safe serialization.
- If an image does not appear: open DevTools and check for 404 errors (expected path `/_static/img/...`), or verify the file exists in `static/img/`.
- If the app does not start: check `db.py` and the connection string; `app.py` depends on `get_connection()` to read tables.

Suggested extensions
--------------------
- Add unit tests for `resolve_tech_image_src` and `detect_image_in_column`.
- Add a `make` or `invoke` script for common tasks (run, lint, tests).

Contact / Author
----------------
- Changes made by the local team. If you want a live review or want me to start the server for testing, let me know and I can run it.

---

Main file: `app.py` — review key functions: `detect_image_in_column`, `resolve_tech_image_src`, `get_equipment_pcb_sizes`, `/propuestas`, and `/image_for_headers`.

