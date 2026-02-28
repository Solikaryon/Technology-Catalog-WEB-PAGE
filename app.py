from flask import Flask, render_template, request, session, redirect, url_for, jsonify, send_file
from db import get_connection
import pandas as pd
import re
import io
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import math
import os
import time
import webbrowser
from threading import Timer
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None

# App timezone for local timestamps (used for proposal creation times)
APP_TZ = os.getenv('APP_TZ', 'America/Mexico_City')

def now_local():
    """Return current local datetime in configured timezone.

    Falls back to UTC if timezone database is unavailable.
    """
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(APP_TZ))
        except Exception:
            return datetime.utcnow()
    return datetime.utcnow()

# Desarrolladores: Luis Fernando Monjaraz Briseño, Jesus Enrique Zarate Ortiz
def extract_numbers(value):
    """Return list of floats found in a string or numeric value."""
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    try:
        s = str(value)
    except Exception:
        return []
    # find numbers like 10, 10.5
    nums = re.findall(r"\d+\.?\d*", s)
    return [float(n) for n in nums]


def parse_size(value):
    """Parse a size string into (x, y) floats.

    Accepts formats like '50x40.5', '50 mm x 40.5 mm', '50mm (X) x 40.5mm (Y)'.
    Returns tuple (x, y) or None if not enough numbers found.
    If only one number found, returns (number, None).
    """
    nums = extract_numbers(value)
    if not nums:
        return None
    if len(nums) == 1:
        return (nums[0], None)
    return (nums[0], nums[1])


def find_column_by_keywords(columns, keywords):
    """Return first column name that contains all keywords (case-insensitive)."""
    lowcols = {c: c.lower() for c in columns}
    for col, low in lowcols.items():
        if all(k in low for k in keywords):
            return col
    return None


def get_friendly_name(tabla_name):
    """Map raw table name to a friendly technology title.

    Uses simple heuristics based on keywords present in the table name.
    """
    if not tabla_name:
        return tabla_name
    s = tabla_name.lower()
    # common technology groups
    if 'pick_and_place' in s or 'p&p' in s or 'pick' in s:
        return 'Pick & Place'
    if 'reflow' in s or 'rfo' in s:
        return 'Reflow Oven'
    if 'screen_printer' in s or 'screen' in s or 'sc_' in s:
        return 'Screen Printer'
    if 'spi' in s:
        return 'SPI'
    if 'aoi' in s or 'axi' in s:
        return 'AOI & AXI'
    if 'camalot' in s or 'prodigy' in s or 'dispens' in s:
        return 'Camalot'
    if 'conveyor' in s or 'loader' in s or 'unloader' in s:
        return 'Conveyor'
    # fallback: clean the table name
    cleaned = tabla_name.strip('[]').replace('_', ' ')
    # remove common prefixes like P&P - or similar
    cleaned = re.sub(r'\b(p&p|p & p|p & p -)\b', 'Pick & Place', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


# Unified list of technology-related tables used across routes and helpers.
# Includes proposals so they show up in /tecnologia and /search like before.
# Meta tables like Tecnologias_Tecnologias and Usuarios are intentionally excluded.
TECH_TABLES = [
    """ SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND UPPER(TABLE_NAME) NOT LIKE '%USUARIOS%' AND UPPER(TABLE_NAME) NOT LIKE '%TECNOLOGIAS_TECNOLOGIAS%'""",
]


def _normalize_key(s):
    """Normalize a string to a simple alphanumeric lowercase key for comparisons."""
    if not s:
        return ''
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def resolve_tech_image_src(header_text: str) -> str:
    """Return a static image path for a given column/equipment header.

    Preference is for PNG images whose names reflect the technology/vendor.
    Special case: AOI and KohYoung share the same image.

    Fallback returns the existing placeholder.svg.
    """
    try:
        h = (header_text or '').strip().lower()
    except Exception:
        h = ''

    # AOI & KohYoung share icon
    if any(k in h for k in ('kohyoung', 'koh young', 'koyoung', 'koh')):
        return '/static/img/KohYoungAoi.png'
    if any(k in h for k in ('aoi', 'axi', 'v310', 'v510', 'v810', 'v9i')):
        return '/static/img/KohYoungAoi.png'

    # SPI (keep vendor-specific mapping; KohYoung handled above -> AOI.png by request)
    if 'spi' in h:
        # if explicitly KohYoung SPI it already matched above; otherwise provide a generic SPI if present
        return '/static/img/SPI.png'

    # Camalot / Dispensers
    if any(k in h for k in ('camalot', 'prodigy', 'dispens')):
        return '/static/img/Camalot.png'
    
    # MPM / Dispensers
    if any(k in h for k in ('mpm', 'dispenser')):
        return '/static/img/MPM.png'

    # NXT
    if any(k in h for k in ('nxt_', 'nxt ', 'nxt')):
        return '/static/img/8NTXIII.png'
    
    # Ekra
    if any(k in h for k in ('ekra', 'screen printer ekra')):
        return '/static/img/Ekra.png'

    # Aimex
    if any(k in h for k in ('aimex', 'aimexiii', 'aimex iii')):
        return '/static/img/7Aimex.png'

    # Conveyors / Loaders
    if any(k in h for k in ('conveyor', 'loader', 'unloader', 'linkwork')):
        return '/static/img/Conveyor.png'

    # Reflow Ovens
    if any(k in h for k in ('reflow', 'oven', 'centurion', 'horno')):
        return '/static/img/ReflowOvenHorno.png'

    # Screen Printers
    if any(k in h for k in ('mpm', 'screen', 'printer', 'dek', 'serio', 'gpx', 'neo')):
        return '/static/img/ScreenPrinter.png'

    # Pick & Place
    if any(k in h for k in ('nxt', 'nxtr', 'aimex', 'pick', 'place', 'fuji')):
        return '/static/img/PickPlace.png'

    # Reflow Ovens
    if any(k in h for k in ('reflow', 'oven', 'centurion')):
        return '/static/img/Reflow.png'

    # Laser
    if 'laser' in h:
        return '/static/img/Laser.png'

    # Default placeholder (keep existing SVG fallback if PNG not available)
    return '/static/img/placeholder.svg'


def detect_image_in_column(df, col):
    """If the dataframe column contains an image path or data URI, return it.

    Looks at the first non-null value and heuristically accepts URLs or
    filesystem paths ending in common image extensions, or data URIs.
    """
    try:
        if df is None or col not in df.columns:
            return None
        vals = df[col].dropna().astype(str)
        if vals.empty:
            return None
        v = vals.iloc[0].strip()
        if not v:
            return None
        low = v.lower()
        # data URI
        if low.startswith('data:image/'):
            return v
        # web/static path or filename ending with image extensions
        if any(low.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg')):
            return v
        if low.startswith('/static/') or low.startswith('http://') or low.startswith('https://'):
            return v
        return None
    except Exception:
        return None


def image_for_headers():
    """Return a mapping header -> image src for a list of header names.

    Tries to find explicit image-like values in Proposal tables for each header column.
    Falls back to `resolve_tech_image_src(header)` when no explicit image is found.
    """
    data = request.get_json(silent=True) or {}
    headers = data.get('headers') or []
    if not isinstance(headers, list) or not headers:
        return jsonify({'images': {}})
    conn = get_connection()
    images = {str(h): None for h in headers}
    try:
        try:
            sql = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND UPPER(TABLE_NAME) LIKE ?"
            tables_df = pd.read_sql(sql, conn, params=['%PROPOSAL%'])
            tbls = [str(x) for x in tables_df['TABLE_NAME'].tolist()] if not tables_df.empty else []
        except Exception:
            tbls = []

        for tbl in tbls:
            if all(images[h] for h in images):
                break
            try:
                sdf = pd.read_sql(f"SELECT TOP 5 * FROM [{tbl}]", conn)
            except Exception:
                continue
            if sdf.empty:
                continue
            cols = list(sdf.columns)
            for h in list(images.keys()):
                if images[h]:
                    continue
                # find matching column name (case-insensitive exact match)
                match_col = None
                for c in cols:
                    try:
                        if str(c).strip().lower() == str(h).strip().lower():
                            match_col = c
                            break
                    except Exception:
                        continue
                if not match_col:
                    continue
                # inspect values for image-like content
                try:
                    vals = sdf[match_col].dropna().astype(str).tolist()
                except Exception:
                    vals = []
                for v in vals:
                    if not v:
                        continue
                    low = v.strip().lower()
                    if low.startswith('data:image/') or low.startswith('/static/') or low.startswith('http://') or low.startswith('https://') or any(low.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg')):
                        images[h] = v.strip()
                        break
                if images[h]:
                    continue
                # If values look like bare filenames (e.g. 'img.png'), try to map to /static/img/<name> if file exists
                for v in vals:
                    if not v:
                        continue
                    fname = v.strip()
                    if re.match(r'^[\w\-. ]+\.(png|jpg|jpeg|gif|svg)$', fname, re.I):
                        candidate = os.path.join(os.path.dirname(__file__), 'static', 'img', fname)
                        try:
                            if os.path.exists(candidate):
                                images[h] = '/static/img/' + fname
                                break
                        except Exception:
                            continue

        # Final fallback to resolve_tech_image_src
        for h in list(images.keys()):
            if not images[h]:
                try:
                    images[h] = resolve_tech_image_src(h)
                except Exception:
                    images[h] = '/static/img/placeholder.svg'
        return jsonify({'images': images})
    finally:
        try:
            conn.close()
        except Exception:
            pass


def equipment_matches_filters(equipment_name, conn_search,
                              qmin_x, qmax_x, qmin_y, qmax_y,
                              thickness_min, thickness_max,
                              weight_min, weight_max):
    """Search related tables for an equipment name and determine if any matching row
    satisfies the numeric filters provided. Returns True if a match is found.
    """
    # Use new unified table list, excluding proposal tables for capability searches.
    search_tables = [t for t in TECH_TABLES if 'PROPOSAL' not in t.upper()]

    def overlap_query(pt):
        """Return True if the equipment size tuple (x,y) overlaps the query rectangle.

        We interpret an equipment size (x,y) as an area covering [0, x] x [0, y].
        Overlap occurs when those intervals intersect. If equipment has no Y
        (y is None) and the query has Y constraints, we treat lack of Y info as
        permissive (allow match when X overlaps) to avoid false negatives.
        """
        if not pt:
            return False
        x, y = pt
        if x is None:
            return False
        try:
            eq_x_min, eq_x_max = 0.0, float(x)
            qx_min, qx_max = float(qmin_x), float(qmax_x)
        except Exception:
            return False

        # X overlap test: equipment [0, x] intersects query [qmin_x, qmax_x]
        x_overlaps = not (eq_x_max < qx_min or eq_x_min > qx_max)
        if not x_overlaps:
            return False

        # If the query includes Y constraints, require Y overlap as well.
        if (qmin_y is not None) or (qmax_y is not None):
            # if equipment has no Y info, be permissive (treat as possible overlap)
            if y is None:
                return True
            try:
                eq_y_min, eq_y_max = 0.0, float(y)
                qy_min, qy_max = float(qmin_y), float(qmax_y)
            except Exception:
                return True
            y_overlaps = not (eq_y_max < qy_min or eq_y_min > qy_max)
            return bool(y_overlaps)

        # No Y constraints: X overlap is sufficient
        return True

    for st in search_tables:
        try:
            sdf = pd.read_sql(f"SELECT * FROM {st}", conn_search)
        except Exception:
            continue
        if sdf.empty:
            continue
        try:
            mask = sdf.apply(lambda r: r.astype(str).str.contains(str(equipment_name), case=False, na=False).any(), axis=1)
            matched = sdf[mask]
        except Exception:
            matched = pd.DataFrame()
        if matched.empty:
            continue
        # evaluate first matched row for sizes/thickness/weight
        row = matched.iloc[0]
        # try pcb part/size fields
        for kwords in (['pcb','min','size'], ['pcb','max','size'], ['part','size']):
            col = find_column_by_keywords(sdf.columns, kwords)
            if col and pd.notnull(row.get(col)):
                p = parse_size(str(row.get(col)))
                if p and p[1] is not None and overlap_query(p):
                    return True
                # if only single number, use overlap semantics (treat as [0, x])
                if p and p[1] is None and overlap_query((p[0], None)):
                    return True
        # thickness
        if (thickness_min is not None) or (thickness_max is not None):
            for c in sdf.columns:
                if 'thick' in str(c).lower():
                    if pd.notnull(row.get(c)):
                        tnums = extract_numbers(row.get(c))
                        if tnums:
                            tval = tnums[0]
                            if (thickness_min is None or tval >= thickness_min) and (thickness_max is None or tval <= thickness_max):
                                return True
        # weight
        if (weight_min is not None) or (weight_max is not None):
            for c in sdf.columns:
                lowc = str(c).lower()
                if 'weight' in lowc or 'kg' in lowc:
                    if pd.notnull(row.get(c)):
                        wnums = extract_numbers(row.get(c))
                        if wnums:
                            wval = wnums[0]
                            if (weight_min is None or wval >= weight_min) and (weight_max is None or wval <= weight_max):
                                return True
        # also try configuration / max print area columns for screen printers
        for keyword in ('max print area', 'maxprintarea', 'print area', 'configuration'):
            for c in sdf.columns:
                if keyword in str(c).lower().replace('_',' '):
                    val = row.get(c)
                    if pd.notnull(val):
                        p = parse_size(str(val))
                        if p and p[1] is not None and overlap_query(p):
                            return True
    return False


def get_equipment_pcb_sizes(equipment_name, conn_search):
    """Find Min/Max PCB (L x W) sizes for a given equipment/technology name across tech tables.

    Searches non-proposal tables listed in TECH_TABLES. Returns a dict:
      { 'min': (L, W) or None, 'max': (L, W) or None }
    If only one size column is found (generic PCB Size), it is returned as 'max' and 'min' stays None.
    """
    result = {
        'min': None,
        'max': None,
        'doc': None,
        'docs': [],
        'source_table': None,
        'max_variants': {},
        'thick': {'min': None, 'max': None, 'val': None},
        'weight': {'max': None, 'val': None}
    }
    if not equipment_name:
        return result
    # Base search set: all technology tables (exclude proposals)
    base_tables = [t for t in TECH_TABLES if 'PROPOSAL' not in t.upper()]
    # Heuristic: restrict search to the most likely technology group inferred from the header text
    header = str(equipment_name or '').strip()
    header_low = header.lower()
    inferred = None
    try:
        if any(k in header_low for k in ('conveyor', 'loader', 'unloader', 'linkwork')):
            inferred = 'Conveyor'
        elif any(k in header_low for k in ('camalot', 'prodigy')):
            inferred = 'Camalot'
        elif any(k in header_low for k in ('koh', 'koh_young', 'koyoung', 'spi')):
            inferred = 'SPI'
        elif any(k in header_low for k in ('mpm', 'screen', 'printer', 'dek', 'serio', 'gpx', 'neo')):
            inferred = 'Screen Printer'
        elif any(k in header_low for k in ('nxt', 'aimex', 'pick', 'place', 'nxtr')):
            inferred = 'Pick & Place'
        elif any(k in header_low for k in ('reflow', 'oven', 'centurion')):
            inferred = 'Reflow Oven'
        elif any(k in header_low for k in ('aoi', 'axi', 'v310', 'v510', 'v810', 'v9i')):
            inferred = 'AOI & AXI'
        elif 'laser' in header_low:
            inferred = 'Laser'  # we currently have no Laser tech tables; avoid cross-matches
    except Exception:
        inferred = None

    if inferred == 'Laser':
        # Do not attempt to pull data from unrelated tables when header says 'Laser'
        # Return empty sizes to avoid showing wrong info from another technology.
        result['doc'] = header
        return result

    # If a technology group was inferred, restrict search to those matching get_friendly_name(table)
    if inferred:
        try:
            search_tables = [t for t in base_tables if get_friendly_name(t) == inferred]
            if not search_tables:
                search_tables = base_tables
        except Exception:
            search_tables = base_tables
    else:
        search_tables = base_tables
    target = str(equipment_name).strip()
    low_target = target.lower()

    # Helpers to compare size tuples
    def parse_as_tuple(v):
        try:
            return parse_size(v)
        except Exception:
            return None
    def better_max(a, b):
        # choose the tuple with larger area; if one is None, return the other
        if not a: return b
        if not b: return a
        ax, ay = a[0], a[1] if len(a) > 1 else None
        bx, by = b[0], b[1] if len(b) > 1 else None
        if ay is None and by is None:
            return a if (ax or 0) >= (bx or 0) else b
        if ay is None:
            return b
        if by is None:
            return a
        area_a = (ax or 0) * (ay or 0)
        area_b = (bx or 0) * (by or 0)
        return a if area_a >= area_b else b
    def better_min(a, b):
        # choose the tuple with smaller area; if one is None, return the other
        if not a: return b
        if not b: return a
        ax, ay = a[0], a[1] if len(a) > 1 else None
        bx, by = b[0], b[1] if len(b) > 1 else None
        if ay is None and by is None:
            return a if (ax or 0) <= (bx or 0) else b
        if ay is None:
            return a
        if by is None:
            return b
        area_a = (ax or 0) * (ay or 0)
        area_b = (bx or 0) * (by or 0)
        return a if area_a <= area_b else b
    # Normalization helpers for broader matching
    def _norm(s):
        try:
            s = str(s)
        except Exception:
            return ''
        out = []
        for ch in s:
            out.append(ch.lower() if ch.isalnum() else ' ')
        return ' '.join(''.join(out).split())
    target_norm = _norm(target)
    target_tokens = [t for t in target_norm.split() if len(t) >= 2]

    for st in search_tables:
        try:
            # limit rows for performance
            sdf = pd.read_sql(f"SELECT TOP 300 * FROM {st}", conn_search)
        except Exception:
            continue
        if sdf.empty:
            continue
        # locate rows mentioning the equipment name anywhere
        try:
            # Basic contains
            mask_contains = sdf.apply(lambda r: r.astype(str).str.contains(low_target, case=False, na=False).any(), axis=1)
        except Exception:
            mask_contains = pd.Series(False, index=sdf.index)
        # Token-based relaxed match: require at least two tokens to appear in the row text
        try:
            def row_has_tokens(r):
                try:
                    txt = _norm(' '.join([str(x) for x in r.values]))
                except Exception:
                    return False
                if not target_tokens:
                    return False
                hits = 0
                for t in target_tokens:
                    if t and txt.find(t) != -1:
                        hits += 1
                return hits >= 2 or (len(target_tokens) == 1 and hits == 1)
            mask_tokens = sdf.apply(row_has_tokens, axis=1)
        except Exception:
            mask_tokens = pd.Series(False, index=sdf.index)
        try:
            matched = sdf[mask_contains | mask_tokens]
        except Exception:
            matched = pd.DataFrame()
    # Identify candidate size columns (support multiple Max columns like M/L/XL)
        min_col = None
        max_cols = []
        # detect variant label from column name (M/L/XL)
        def detect_variant_label(colname: str):
            s = str(colname).strip().lower()
            # remove brackets and extra symbols for suffix detection
            s_clean = ''.join([ch if ch.isalnum() or ch.isspace() else ' ' for ch in s]).strip()
            if s_clean.endswith(' xl') or s_clean.endswith(' x l'):
                return 'XL'
            if s_clean.endswith(' l'):
                return 'L'
            if s_clean.endswith(' m'):
                return 'M'
            return None
        max_col_labels = {}
        for c in sdf.columns:
            cl = str(c).lower()
            if ('pcb' in cl and 'min' in cl and ('size' in cl or 'min.pcb' in cl or 'x' in cl)):
                if not min_col:
                    min_col = c
            if ('pcb' in cl and 'max' in cl) and (('size' in cl) or ('max.pcb' in cl) or ('x' in cl)):
                max_cols.append(c)
                lbl = detect_variant_label(c)
                if lbl:
                    max_col_labels[c] = lbl
        # also look for generic pcb size column
        generic_col = None
        if not max_cols:
            for c in sdf.columns:
                cl = str(c).lower()
                if 'pcb' in cl and 'size' in cl and 'max' not in cl and 'min' not in cl:
                    generic_col = c
                    break
        # Camalot and general size synonyms (work/dispense/substrate/board area)
        extra_size_cols = []
        try:
            tbl_friendly = get_friendly_name(st) or ''
        except Exception:
            tbl_friendly = ''
        for c in sdf.columns:
            cl = str(c).lower()
            if any(bad in cl for bad in ('thick', 'weight', 'temp', 'temperature', 'speed', 'kg')):
                continue
            if ('work area' in cl) or ('dispense area' in cl) or ('substrate' in cl) or ('board size' in cl) or ('board' in cl and 'size' in cl) or ('envelope' in cl) or ('range' in cl and ('x' in cl or 'y' in cl)):
                extra_size_cols.append(c)
        # thickness columns (min/max or generic)
        thick_min_col = None
        thick_max_col = None
        thick_any_cols = []
        for c in sdf.columns:
            cl = str(c).lower()
            if 'thick' in cl:
                if 'min' in cl and not thick_min_col:
                    thick_min_col = c
                elif 'max' in cl and not thick_max_col:
                    thick_max_col = c
                else:
                    thick_any_cols.append(c)
        # weight columns (max or generic; prefer ones containing 'weight' or 'kg')
        weight_max_cols = []
        weight_any_cols = []
        for c in sdf.columns:
            cl = str(c).lower()
            if ('weight' in cl) or (' kg' in cl) or cl.endswith('kg'):
                if 'max' in cl:
                    weight_max_cols.append(c)
                else:
                    weight_any_cols.append(c)

        def harvest_from_row(row):
            nonlocal result
            # capture any documento values present (collect multiple docs)
            try:
                doc_cols = [c for c in sdf.columns if 'document' in str(c).lower() or 'documento' in str(c).lower()]
                for dc in doc_cols:
                    dv = row.get(dc)
                    if pd.notnull(dv):
                        dv_str = str(dv).strip()
                        if dv_str and dv_str not in result['docs']:
                            result['docs'].append(dv_str)
            except Exception:
                pass
            # min
            try:
                if min_col and pd.notnull(row.get(min_col)):
                    pmin = parse_as_tuple(row.get(min_col))
                    if pmin and pmin[0] is not None:
                        result['min'] = pmin if result['min'] is None else better_min(result['min'], pmin)
            except Exception:
                pass
            # weight
            try:
                # max from explicit max columns
                wbest = None
                for wc in weight_max_cols:
                    try:
                        if pd.notnull(row.get(wc)):
                            nums = extract_numbers(row.get(wc)) or []
                            if nums:
                                val = float(nums[0])
                                wbest = val if (wbest is None or val > wbest) else wbest
                    except Exception:
                        continue
                if wbest is None:
                    for wc in weight_any_cols:
                        try:
                            if pd.notnull(row.get(wc)):
                                nums = extract_numbers(row.get(wc)) or []
                                if nums:
                                    val = float(nums[0])
                                    if result['weight']['val'] is None or val > result['weight']['val']:
                                        result['weight']['val'] = val
                        except Exception:
                            continue
                if wbest is not None:
                    result['weight']['max'] = wbest if result['weight']['max'] is None or wbest > result['weight']['max'] else result['weight']['max']
            except Exception:
                pass
            # max (consider multiple and variants)
            try:
                best = None
                for mc in max_cols:
                    try:
                        if pd.notnull(row.get(mc)):
                            pmx = parse_as_tuple(row.get(mc))
                            if pmx and pmx[0] is not None:
                                best = better_max(best, pmx)
                                # store variant
                                lbl = max_col_labels.get(mc)
                                if lbl:
                                    cur = result['max_variants'].get(lbl)
                                    result['max_variants'][lbl] = pmx if cur is None else better_max(cur, pmx)
                    except Exception:
                        continue
                if best is None and generic_col and pd.notnull(row.get(generic_col)):
                    best = parse_as_tuple(row.get(generic_col))
                # Try extra size synonyms (use as max)
                if best is None and extra_size_cols:
                    for ec in extra_size_cols:
                        try:
                            val = row.get(ec)
                            if pd.notnull(val):
                                pmx = parse_as_tuple(val)
                                if pmx and pmx[0] is not None:
                                    best = better_max(best, pmx)
                        except Exception:
                            continue
                if best and best[0] is not None:
                    result['max'] = best if result['max'] is None else better_max(result['max'], best)
            except Exception:
                pass
            # thickness
            try:
                # min
                if thick_min_col and pd.notnull(row.get(thick_min_col)):
                    nums = extract_numbers(row.get(thick_min_col)) or []
                    if nums:
                        v = float(nums[0])
                        if result['thick']['min'] is None or v < result['thick']['min']:
                            result['thick']['min'] = v
                # max
                if thick_max_col and pd.notnull(row.get(thick_max_col)):
                    nums = extract_numbers(row.get(thick_max_col)) or []
                    if nums:
                        v = float(nums[0])
                        if result['thick']['max'] is None or v > result['thick']['max']:
                            result['thick']['max'] = v
                # any generic thickness
                if result['thick']['val'] is None:
                    for tc in thick_any_cols:
                        try:
                            if pd.notnull(row.get(tc)):
                                nums = extract_numbers(row.get(tc)) or []
                                if nums:
                                    result['thick']['val'] = float(nums[0])
                                    break
                        except Exception:
                            continue
            except Exception:
                pass

        # If we found matching rows, harvest from them; otherwise, optionally compute global extremes for conveyors
        if not matched.empty:
            row = matched.iloc[0]
            harvest_from_row(row)
        else:
            st_low = str(st).lower()
            looks_like_conveyor_table = ('conveyor' in st_low) or ('loader' in st_low) or ('unloader' in st_low)
            looks_like_conveyor_equipment = ('conveyor' in low_target) or ('loader' in low_target) or ('unloader' in low_target)
            if looks_like_conveyor_table and looks_like_conveyor_equipment:
                # compute global min/max across the whole table to ensure conveyors show dimensions
                try:
                    # global min from min_col
                    if min_col:
                        try:
                            vals = sdf[min_col].dropna().astype(str).tolist()
                        except Exception:
                            vals = []
                        for v in vals:
                            pmin = parse_as_tuple(v)
                            if pmin and pmin[0] is not None:
                                result['min'] = pmin if result['min'] is None else better_min(result['min'], pmin)
                    # global max across all max_cols
                    best = None
                    for mc in max_cols:
                        try:
                            vals = sdf[mc].dropna().astype(str).tolist()
                        except Exception:
                            vals = []
                        for v in vals:
                            pmx = parse_as_tuple(v)
                            if pmx and pmx[0] is not None:
                                best = better_max(best, pmx)
                                # store variant max per label
                                lbl = max_col_labels.get(mc)
                                if lbl:
                                    cur = result['max_variants'].get(lbl)
                                    result['max_variants'][lbl] = pmx if cur is None else better_max(cur, pmx)
                    if best is None and generic_col:
                        try:
                            vals = sdf[generic_col].dropna().astype(str).tolist()
                        except Exception:
                            vals = []
                        for v in vals:
                            pmx = parse_as_tuple(v)
                            if pmx and pmx[0] is not None:
                                best = better_max(best, pmx)
                    if best and best[0] is not None:
                        result['max'] = best if result['max'] is None else better_max(result['max'], best)
                    # global weight
                    try:
                        wbest = None
                        for wc in weight_max_cols:
                            try:
                                vals = sdf[wc].dropna().astype(str).tolist()
                            except Exception:
                                vals = []
                            for v in vals:
                                nums = extract_numbers(v) or []
                                if nums:
                                    val = float(nums[0])
                                    wbest = val if (wbest is None or val > wbest) else wbest
                        if wbest is None:
                            for wc in weight_any_cols:
                                try:
                                    vals = sdf[wc].dropna().astype(str).tolist()
                                except Exception:
                                    vals = []
                                for v in vals:
                                    nums = extract_numbers(v) or []
                                    if nums:
                                        val = float(nums[0])
                                        if result['weight']['val'] is None or val > result['weight']['val']:
                                            result['weight']['val'] = val
                        if wbest is not None:
                            result['weight']['max'] = wbest if (result['weight']['max'] is None or wbest > result['weight']['max']) else result['weight']['max']
                    except Exception:
                        pass
                    # global thickness
                    try:
                        if thick_min_col:
                            vals = sdf[thick_min_col].dropna().astype(str).tolist()
                            for v in vals:
                                nums = extract_numbers(v) or []
                                if nums:
                                    num = float(nums[0])
                                    if result['thick']['min'] is None or num < result['thick']['min']:
                                        result['thick']['min'] = num
                        if thick_max_col:
                            vals = sdf[thick_max_col].dropna().astype(str).tolist()
                            for v in vals:
                                nums = extract_numbers(v) or []
                                if nums:
                                    num = float(nums[0])
                                    if result['thick']['max'] is None or num > result['thick']['max']:
                                        result['thick']['max'] = num
                        if result['thick']['val'] is None:
                            for tc in thick_any_cols:
                                try:
                                    vals = sdf[tc].dropna().astype(str).tolist()
                                except Exception:
                                    vals = []
                                for v in vals:
                                    nums = extract_numbers(v) or []
                                    if nums:
                                        result['thick']['val'] = float(nums[0])
                                        break
                                if result['thick']['val'] is not None:
                                    break
                    except Exception:
                        pass
                    # set source_table if we didn't find an explicit 'document' value
                    if result.get('doc') is None:
                        result['source_table'] = st.strip('[]')
                except Exception:
                    pass

        # stop early if we have both
        if result['min'] and result['max']:
            break
    # finalize doc field from collected docs (keep docs list for callers)
    try:
        if result.get('docs'):
            result['doc'] = result['docs'][0]
    except Exception:
        pass
    return result


# Simple in-memory cache for equipment size lookups to speed up proposals/search pages
_EQUIP_SIZE_CACHE = {}
_EQUIP_SIZE_CACHE_TTL = float(os.getenv('SIZES_CACHE_TTL', '1800'))  # seconds, default 30 minutes

def get_equipment_pcb_sizes_cached(equipment_name, conn_search):
    try:
        key = _normalize_key(equipment_name)
        now = time.time()
        ent = _EQUIP_SIZE_CACHE.get(key)
        if ent and (now - ent['ts'] < _EQUIP_SIZE_CACHE_TTL):
            return ent['val']
        val = get_equipment_pcb_sizes(equipment_name, conn_search)
        _EQUIP_SIZE_CACHE[key] = {'ts': now, 'val': val}
        return val
    except Exception:
        # On any cache error, fall back to direct computation
        return get_equipment_pcb_sizes(equipment_name, conn_search)


def _camalot_extra_info(conn):
    """Return selected Camalot fields as ['Field: value', ...] from [Camalot_Prodigy].

    Uses fuzzy column matching to tolerate minor renames/typos like 'Widht'.
    """
    lines = []
    try:
        try:
            df = pd.read_sql("SELECT TOP 1 * FROM [Camalot_Prodigy]", conn)
        except Exception:
            df = pd.DataFrame()
        if df.empty:
            return lines
        row = df.iloc[0]
        cols = list(df.columns)

        def pick_col(cands):
            # cands is list of keywords; use existing helper to find first column containing all
            try:
                return find_column_by_keywords(cols, cands)
            except Exception:
                return None

        mapping = [
            (['max','dispense','area'], 'Max Dispense Area'),
            (['conveyor','type'], 'Conveyor Type'),
            (['min','conveyor','width'], 'Min Conveyor Width'),
            (['min','conveyor','widht'], 'Min Conveyor Width'),  # tolerate typo
            (['above','board','clearance'], 'Above Board Clearance'),
            (['under','board','clearance'], 'Underboard Clearance'),
            (['underboard','clearance'], 'Underboard Clearance'),
            (['transport','height'], 'Transport Height'),
        ]
        added = set()
        for kws, label in mapping:
            col = pick_col(kws)
            if col and col not in added:
                val = row.get(col)
                if pd.notnull(val):
                    lines.append(f"{label}: {val}")
                    added.add(col)
        return lines
    except Exception:
        return lines

app = Flask(__name__)
app.secret_key = 'change-me-to-a-secure-random-key'

# Register routes that were defined earlier (functions declared before app creation)
try:
    app.add_url_rule('/image_for_headers', 'image_for_headers', image_for_headers, methods=['POST'])
except Exception:
    pass

@app.route('/')
def index():
    conn = get_connection()
    query = "SELECT Tecnologia, Documento FROM [Tecnologias_Tecnologias]"
    df = pd.read_sql(query, conn)
    conn.close()
    # Build a deduplicated list of friendly technology names so the dropdown shows one per type.
    grouped = {}
    for _, r in df.iterrows():
        raw = r.get('Tecnologia')
        friendly = get_friendly_name(raw)
        key = _normalize_key(friendly)
        if key not in grouped:
            # Use a special data-doc marker so the /tecnologia route knows to aggregate by tech
            grouped[key] = {'Tecnologia': friendly, 'Documento': f'GROUP:{friendly}'}

    tecnologias = list(grouped.values())
    return render_template("index.html", tecnologias=tecnologias)


@app.route('/manual')
def manual():
    # Simple user manual page
    return render_template('manual.html')


@app.route('/tecnologia', methods=['POST'])
def tecnologia():
    tecnologia = request.form.get('tecnologia')
    documento = request.form.get('documento')

    conn = get_connection()

    # Listado actualizado de todas las tablas a consultar
    tablas = TECH_TABLES

    resultados = {}

    for tabla in tablas:
        try:
            # If user selected the special 'ALL' option, fetch all rows from each table
            if documento == 'ALL' or tecnologia == 'ALL' or (not documento):
                query = f"SELECT * FROM {tabla}"
                df = pd.read_sql(query, conn)
            # If the cliente selected a grouped technology (DOCUMENTO='GROUP:<friendly>'),
            # only include tables whose friendly name matches the requested technology and
            # fetch all rows from those tables (aggregate across documents).
            elif isinstance(documento, str) and documento.startswith('GROUP:'):
                target = documento.split(':', 1)[1]
                tbl_friendly = get_friendly_name(tabla)
                if _normalize_key(tbl_friendly) == _normalize_key(target):
                    query = f"SELECT * FROM {tabla}"
                    df = pd.read_sql(query, conn)
                else:
                    # skip this table (not part of the requested technology group)
                    continue
            else:
                query = f"SELECT * FROM {tabla} WHERE Documento = ?"
                df = pd.read_sql(query, conn, params=[documento])
            if not df.empty:
                friendly = get_friendly_name(tabla)
                html = df.to_html(classes="data-table", index=False)
                # group multiple tables under the same friendly technology name
                if friendly in resultados:
                    resultados[friendly] += html
                else:
                    resultados[friendly] = html
        except Exception as e:
            print(f"Error en {tabla}: {e}")

    conn.close()

    return render_template("tecnologia.html", tecnologia=tecnologia, documento=documento, resultados=resultados)


@app.route('/tecnologia_inline', methods=['POST'])
def tecnologia_inline():
    """Same logic as /tecnologia but returns JSON so index can render inline.

    Input (JSON or form): tecnologia, documento
    Output: { tecnologia, documento, resultados: { friendly_name: html_table } }
    """
    tecnologia = request.form.get('tecnologia') if request.form else None
    documento = request.form.get('documento') if request.form else None
    if not tecnologia:
        data = request.get_json(silent=True) or {}
        tecnologia = data.get('tecnologia')
        documento = data.get('documento')

    conn = get_connection()

    tablas = TECH_TABLES

    resultados = {}

    for tabla in tablas:
        try:
            if documento == 'ALL' or tecnologia == 'ALL' or (not documento):
                query = f"SELECT * FROM {tabla}"
                df = pd.read_sql(query, conn)
            elif isinstance(documento, str) and documento.startswith('GROUP:'):
                target = documento.split(':', 1)[1]
                tbl_friendly = get_friendly_name(tabla)
                if _normalize_key(tbl_friendly) == _normalize_key(target):
                    query = f"SELECT * FROM {tabla}"
                    df = pd.read_sql(query, conn)
                else:
                    continue
            else:
                query = f"SELECT * FROM {tabla} WHERE Documento = ?"
                df = pd.read_sql(query, conn, params=[documento])
            if not df.empty:
                friendly = get_friendly_name(tabla)
                html = df.to_html(classes="data-table", index=False)
                if friendly in resultados:
                    resultados[friendly] += html
                else:
                    resultados[friendly] = html
        except Exception as e:
            print(f"Error en {tabla}: {e}")

    try:
        conn.close()
    except Exception:
        pass

    return jsonify({ 'tecnologia': tecnologia, 'documento': documento, 'resultados': resultados })


@app.route('/search', methods=['GET', 'POST'])
def search():
    """Independent search across the tables using numeric ranges for PCB sizes, thickness and weight.

    The form supports pcb_min_size and pcb_max_size (search range), and optional
    thickness_min/thickness_max and weight_min/weight_max. Any field may be left empty.
    """
    resultados = {}
    # Prepare dropdown options for tecnologia and documento from Tecnologias_Tecnologias
    tecnologias_options = []
    documentos_options = []
    try:
        conn_meta = get_connection()
        meta_df = pd.read_sql("SELECT Tecnologia, Documento FROM [Tecnologias_Tecnologias]", conn_meta)
        # friendly technology names
        friendlys = [get_friendly_name(x) for x in meta_df['Tecnologia'].dropna().astype(str).unique().tolist()]
        # deduplicate and sort
        seen = set()
        for f in friendlys:
            k = _normalize_key(f)
            if k and k not in seen:
                seen.add(k)
                tecnologias_options.append(f)
        # documentos
        documentos_options = [str(x) for x in meta_df['Documento'].dropna().astype(str).unique().tolist()]
    except Exception:
        tecnologias_options = []
        documentos_options = []
    finally:
        try:
            conn_meta.close()
        except Exception:
            pass
    if request.method == 'POST':
        # parse inputs (allow empty)
        def to_float(v):
            try:
                return float(v)
            except Exception:
                return None

        # Prefer 2D inputs (X and Y), but keep backward-compatible single-value fields
        pcb_min_x = to_float(request.form.get('pcb_min_x'))
        pcb_min_y = to_float(request.form.get('pcb_min_y'))
        pcb_max_x = to_float(request.form.get('pcb_max_x'))
        pcb_max_y = to_float(request.form.get('pcb_max_y'))

        # legacy single-field support (kept for compatibility)
        pcb_min_single = to_float(request.form.get('pcb_min_size'))
        pcb_max_single = to_float(request.form.get('pcb_max_size'))
        thickness_min = to_float(request.form.get('thickness_min'))
        thickness_max = to_float(request.form.get('thickness_max'))
        weight_min = to_float(request.form.get('weight_min'))
        weight_max = to_float(request.form.get('weight_max'))
        # Additional textual filters provided by the form
        tecnologia_filter = (request.form.get('tecnologia') or '').strip()
        documento_filter = (request.form.get('documento') or '').strip()

        # Use only technology capability tables; exclude any Proposal tables from search results
        tablas = [t for t in TECH_TABLES if 'PROPOSAL' not in t.upper()]

        conn = get_connection()

        # keywords to find columns if they exist
        size_min_kw = ['pcb', 'min', 'size']
        size_max_kw = ['pcb', 'max', 'size']
        thickness_kw = ['thickness']
        weight_kw = ['weight']

        for tabla in tablas:
            try:
                query = f"SELECT * FROM {tabla}"
                df = pd.read_sql(query, conn)
                if df.empty:
                    continue

                # --- Apply textual filters (tecnologia / documento) to narrow main search results ---
                try:
                    title = get_friendly_name(tabla) or ''
                    # tecnologia filter: require the table to be related to selected tecnologia
                    if tecnologia_filter:
                        # Strict technology-to-table matching: only include tables whose
                        # friendly technology (get_friendly_name) matches the selected filter.
                        # Do NOT fall back to scanning cell values when a tecnologia is selected.
                        tf_norm = _normalize_key(tecnologia_filter)
                        tbl_friendly = get_friendly_name(tabla) or ''
                        if _normalize_key(tbl_friendly) != tf_norm:
                            # skip tables not belonging to the requested technology
                            continue

                    # documento filter: if proposal/data table has a Documento-like column, filter rows by it
                    if documento_filter:
                        doc = documento_filter
                        doc_cols = [c for c in df.columns if 'document' in str(c).lower() or 'documento' in str(c).lower()]
                        if doc_cols:
                            try:
                                # keep rows where any documento-like column contains the filter
                                mask = pd.Series(False, index=df.index)
                                for dc in doc_cols:
                                    try:
                                        mask = mask | df[dc].astype(str).str.contains(doc, case=False, na=False)
                                    except Exception:
                                        # column might not be str-convertible; skip
                                        continue
                                df = df[mask]
                            except Exception:
                                # if filtering fails, leave df as-is (avoid crashing search)
                                pass
                        else:
                            # no explicit documento column — attempt to find the term in any column values
                            try:
                                mask_any = df.apply(lambda r: r.astype(str).str.contains(doc, case=False, na=False).any(), axis=1)
                                df = df[mask_any]
                            except Exception:
                                pass

                except Exception:
                    # if any unexpected error during textual filtering, continue processing table normally
                    pass

                if df.empty:
                    continue

                # find candidate column names
                col_size_min = find_column_by_keywords(df.columns, size_min_kw)
                col_size_max = find_column_by_keywords(df.columns, size_max_kw)
                col_thickness = find_column_by_keywords(df.columns, thickness_kw)
                col_weight = find_column_by_keywords(df.columns, weight_kw)

                def row_matches(row):
                    # --- SIZE FILTERING: require the row's documented sizes themselves be inside the user range ---
                    # Build query rectangle (defaults allow missing endpoints)
                    qmin_x = pcb_min_x if pcb_min_x is not None else (pcb_min_single if pcb_min_single is not None else -float('inf'))
                    qmax_x = pcb_max_x if pcb_max_x is not None else (pcb_max_single if pcb_max_single is not None else float('inf'))
                    qmin_y = pcb_min_y if pcb_min_y is not None else -float('inf')
                    qmax_y = pcb_max_y if pcb_max_y is not None else float('inf')

                    # Helper: check if a parsed tuple (x,y) lies fully inside the query rectangle
                    def inside_query(pt):
                        if not pt:
                            return False
                        x, y = pt
                        if x is None:
                            return False
                        if not (qmin_x <= x <= qmax_x):
                            return False
                        # if query has Y constraints, require Y present and inside; otherwise ignore Y
                        if (pcb_min_y is not None) or (pcb_max_y is not None):
                            if y is None:
                                return False
                            if not (qmin_y <= y <= qmax_y):
                                return False
                        return True

                    # If explicit min & max columns exist, prefer those
                    min_pt = None
                    max_pt = None
                    if col_size_min and pd.notnull(row.get(col_size_min)):
                        min_pt = parse_size(row.get(col_size_min))
                    if col_size_max and pd.notnull(row.get(col_size_max)):
                        max_pt = parse_size(row.get(col_size_max))

                    if min_pt and max_pt:
                        # require both documented min and max to be inside the query rectangle
                        if not (inside_query(min_pt) and inside_query(max_pt)):
                            return False
                    else:
                        # No explicit min/max pair — try any size-like column (Part Size, PCB Size, etc.)
                        found = False
                        for c in df.columns:
                            low = c.lower()
                            if 'size' in low or ('part' in low and 'size' in low) or ('board' in low and 'size' in low) or ('pcb' in low and 'size' in low):
                                val = row.get(c)
                                if pd.notnull(val):
                                    pt = parse_size(val)
                                    if pt and inside_query(pt):
                                        found = True
                                        break
                        # If user did provide any size constraints and we didn't find any column inside the range -> reject
                        if (pcb_min_x is not None or pcb_min_y is not None or pcb_max_x is not None or pcb_max_y is not None
                            or pcb_min_single is not None or pcb_max_single is not None) and not found:
                            return False

                    # thickness
                    if (thickness_min is not None) or (thickness_max is not None):
                        tnums = []
                        if col_thickness and pd.notnull(row.get(col_thickness)):
                            tnums = extract_numbers(row.get(col_thickness))
                        if not tnums:
                            # try any column that contains 'thick'
                            for c in df.columns:
                                if 'thick' in c.lower():
                                    tnums = extract_numbers(row.get(c))
                                    if tnums:
                                        break
                        if not tnums:
                            return False
                        tval = tnums[0]
                        if thickness_min is not None and tval < thickness_min:
                            return False
                        if thickness_max is not None and tval > thickness_max:
                            return False

                    # weight
                    if (weight_min is not None) or (weight_max is not None):
                        wnums = []
                        if col_weight and pd.notnull(row.get(col_weight)):
                            wnums = extract_numbers(row.get(col_weight))
                        if not wnums:
                            for c in df.columns:
                                if 'weight' in c.lower() or 'kg' in c.lower():
                                    wnums = extract_numbers(row.get(c))
                                    if wnums:
                                        break
                        if not wnums:
                            return False
                        wval = wnums[0]
                        if weight_min is not None and wval < weight_min:
                            return False
                        if weight_max is not None and wval > weight_max:
                            return False

                    return True

                # apply filter
                try:
                    mask = df.apply(row_matches, axis=1)
                    df_filtered = df[mask]
                except Exception as e:
                    print(f"Error aplicando filtro en {tabla}: {e}")
                    df_filtered = pd.DataFrame()

                if not df_filtered.empty:
                    friendly = get_friendly_name(tabla)
                    html = df_filtered.to_html(classes="data-table", index=False)
                    if friendly in resultados:
                        resultados[friendly] += html
                    else:
                        resultados[friendly] = html

            except Exception as e:
                print(f"Error en {tabla}: {e}")

        conn.close()

        # --- Find matching proposals (use similar heuristics as /propuestas) ---
        # ensure variable always exists even if the following try block fails
        proposals_matches = []
        try:
            sql = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND UPPER(TABLE_NAME) LIKE ?"
            tables_df = pd.read_sql(sql, conn, params=['%PROPOSAL%'])

            # build query rectangle values for helper
            qmin_x = pcb_min_x if pcb_min_x is not None else (pcb_min_single if pcb_min_single is not None else -float('inf'))
            qmax_x = pcb_max_x if pcb_max_x is not None else (pcb_max_single if pcb_max_single is not None else float('inf'))
            qmin_y = pcb_min_y if pcb_min_y is not None else -float('inf')
            qmax_y = pcb_max_y if pcb_max_y is not None else float('inf')

            for _, row in tables_df.iterrows():
                tbl = row['TABLE_NAME']
                try:
                    pdf = pd.read_sql(f"SELECT * FROM [{tbl}]", conn)
                except Exception:
                    continue
                if pdf.empty:
                    continue

                # drop ID-like columns
                pdf = pdf.drop(columns=[c for c in pdf.columns if str(c).lower() in ('id','idd','ident','id_')], errors='ignore')
                # compute a cleaned title for the proposal table
                title = tbl.strip('[]').replace('_', ' ')

                # If the user provided a tecnologia filter, quick-reject proposals whose
                # table title and column names don't mention it (helps narrow down results).
                if tecnologia_filter:
                    tf = tecnologia_filter.lower()
                    title_low = str(title).lower()
                    cols_low = [str(c).lower() for c in pdf.columns]
                    if tf not in title_low and not any(tf in c for c in cols_low):
                        # skip this proposal - doesn't look related to requested technology
                        continue

                # If the user provided a documento filter and the proposal table contains
                # a Documento-like column, require it to match at least one row.
                if documento_filter:
                    doc_cols = [c for c in pdf.columns if 'document' in str(c).lower()]
                    if doc_cols:
                        found_doc = False
                        for dc in doc_cols:
                            try:
                                vals = pdf[dc].dropna().astype(str).str.lower().tolist()
                            except Exception:
                                vals = []
                            if documento_filter.lower() in ' '.join(vals):
                                found_doc = True
                                break
                        if not found_doc:
                            continue

                # vertical Equipo/Costo -> horizontal
                try:
                    cols_lower = [str(c).lower() for c in pdf.columns]
                    if len(pdf.columns) == 2 and (('equipo' in cols_lower[0] or 'equipo' in cols_lower[1]) and ('costo' in cols_lower[0] or 'costo' in cols_lower[1])):
                        equipment = pdf.iloc[:, 0].astype(str).tolist()
                        costs = pdf.iloc[:, 1].astype(str).tolist()
                        pdf = pd.DataFrame([costs], columns=equipment)
                except Exception:
                    pass

                # Determine if any equipment/column in this proposal meets the search filters
                matched_proposal = False
                for header in pdf.columns:
                    # Try matching by searching related tables for this equipment
                    try:
                        if equipment_matches_filters(header, conn, qmin_x, qmax_x, qmin_y, qmax_y,
                                                     thickness_min, thickness_max, weight_min, weight_max):
                            matched_proposal = True
                            break
                    except Exception:
                        continue

                if matched_proposal:
                    # create display HTML like in /propuestas (insert placeholder image row)
                    try:
                        def first_nonnull(col):
                            try:
                                vals = pdf[col].dropna().astype(str)
                                if not vals.empty:
                                    return vals.iloc[0]
                            except Exception:
                                return None
                            return None

                        tooltip_parts = []
                        # attempt to collect any direct size/thickness/weight info from the proposal table
                        col = find_column_by_keywords(pdf.columns, ['pcb','min','size'])
                        if col:
                            v = first_nonnull(col)
                            if v:
                                p = parse_size(v)
                                tooltip_parts.append(f"{col}: {p[0]}x{p[1]}" if p and p[1] is not None else f"{col}: {v}")
                        col = find_column_by_keywords(pdf.columns, ['pcb','max','size'])
                        if col:
                            v = first_nonnull(col)
                            if v:
                                p = parse_size(v)
                                tooltip_parts.append(f"{col}: {p[0]}x{p[1]}" if p and p[1] is not None else f"{col}: {v}")
                        col = find_column_by_keywords(pdf.columns, ['part','size'])
                        if col:
                            v = first_nonnull(col)
                            if v:
                                p = parse_size(v)
                                tooltip_parts.append(f"{col}: {p[0]}x{p[1]}" if p and p[1] is not None else f"{col}: {v}")
                        col = find_column_by_keywords(pdf.columns, ['thickness'])
                        if col:
                            v = first_nonnull(col)
                            if v:
                                nums = extract_numbers(v)
                                tooltip_parts.append(f"{col}: {nums[0]}" if nums else f"{col}: {v}")
                        # weight
                        for c in pdf.columns:
                            low = str(c).lower()
                            if 'weight' in low or 'kg' in low:
                                v = first_nonnull(c)
                                if v:
                                    nums = extract_numbers(v)
                                    tooltip_parts.append(f"{c}: {nums[0]}" if nums else f"{c}: {v}")
                                    break

                        # Prefer PCB Min/Max sizes pulled dynamically from tech tables per header
                        sizes_cache = {}
                        image_row = []
                        for header in pdf.columns:
                            h = str(header).strip()
                            key = h.lower()
                            if key not in sizes_cache:
                                try:
                                    sizes_cache[key] = get_equipment_pcb_sizes_cached(h, conn)
                                except Exception:
                                    sizes_cache[key] = {'min': None, 'max': None}
                            sizes = sizes_cache[key]
                            # Base three lines: Documento, Min.PCB, Max.PCB
                            tooltip_lines = []
                            missing_label = 'No info'
                            docs_list = sizes.get('docs') or []
                            # If no docs found in tech tables, try the global Tecnologias_Tecnologias mapping
                            try:
                                if (not docs_list) and (not sizes.get('doc')):
                                    friendly = get_friendly_name(h)
                                    tdf = pd.read_sql("SELECT Tecnologia, Documento FROM [Tecnologias_Tecnologias]", conn)
                                    if not tdf.empty:
                                        for _, rr in tdf.iterrows():
                                            try:
                                                if get_friendly_name(rr['Tecnologia']) == friendly and pd.notnull(rr['Documento']):
                                                    dv = str(rr['Documento']).strip()
                                                    if dv and dv not in docs_list:
                                                        docs_list.append(dv)
                                            except Exception:
                                                continue
                            except Exception:
                                pass
                            doc_val = docs_list[0] if docs_list else (sizes.get('doc') if sizes.get('doc') else missing_label)
                            tooltip_lines.append(f"Documento: {doc_val}")
                            if len(docs_list) > 1:
                                # show secondary documents (comma-separated)
                                tooltip_lines.append(f"Documento Secundario: {', '.join(docs_list[1:])}")
                            # If the lookup found a source table but no explicit document, show the table separately
                            source_tbl = sizes.get('source_table')
                            if source_tbl and (not sizes.get('doc')):
                                tooltip_lines.append(f"Tabla: {source_tbl}")
                            if sizes.get('min'):
                                mn = sizes['min']
                                if mn[1] is None:
                                    tooltip_lines.append(f"Min.PCB (L X W) (mm): {mn[0]}")
                                else:
                                    tooltip_lines.append(f"Min.PCB (L X W) (mm): {mn[0]}x{mn[1]}")
                            else:
                                tooltip_lines.append(f"Min.PCB (L X W) (mm): {missing_label}")
                            # Decide whether to render the generic Max line (skip if Conveyor has XL variant)
                            hlow = h.lower()
                            variants = sizes.get('max_variants') or {} if ('conveyor' in hlow or 'loader' in hlow or 'unloader' in hlow) else {}
                            include_generic_max = True
                            if variants.get('XL'):
                                include_generic_max = False
                            if include_generic_max and sizes.get('max'):
                                mx = sizes['max']
                                if mx[1] is None:
                                    tooltip_lines.append(f"Max.PCB (L X W) (mm): {mx[0]}")
                                else:
                                    tooltip_lines.append(f"Max.PCB (L X W) (mm): {mx[0]}x{mx[1]}")
                            # For conveyors: append M/L/XL if available
                            if 'conveyor' in hlow or 'loader' in hlow or 'unloader' in hlow:
                                def _fmt_tuple(t):
                                    try:
                                        if isinstance(t, (list, tuple)):
                                            if len(t) > 1 and t[1] is not None:
                                                return f"{t[0]}x{t[1]}"
                                            return f"{t[0]}"
                                        return str(t)
                                    except Exception:
                                        return str(t)
                                for label in ['M','L','XL']:
                                    if variants.get(label):
                                        tooltip_lines.append(f"Max.PCB (L X W) (mm) {label}: {_fmt_tuple(variants[label])}")
                                # include any additional labels (if present)
                                for lbl, val in variants.items():
                                    if lbl not in ('M','L','XL'):
                                        tooltip_lines.append(f"Max.PCB (L X W) (mm) {lbl}: {_fmt_tuple(val)}")
                            # Thickness if available
                            thick = sizes.get('thick') or {}
                            th_val = None
                            if (thick.get('min') is not None) and (thick.get('max') is not None) and (thick['min'] != thick['max']):
                                th_val = f"{thick['min']} - {thick['max']}"
                            elif thick.get('max') is not None:
                                th_val = f"{thick['max']}"
                            elif thick.get('min') is not None:
                                th_val = f"{thick['min']}"
                            elif thick.get('val') is not None:
                                th_val = f"{thick['val']}"
                            if th_val is not None:
                                tooltip_lines.append(f"PCB Thickness (mm): {th_val}")
                            # Weight if available
                            weight = sizes.get('weight') or {}
                            w_val = weight.get('max') if (weight.get('max') is not None) else weight.get('val')
                            if w_val is not None:
                                tooltip_lines.append(f"PCB Max. Weight (kg): {w_val}")
                            # Camalot: append key fields from Camalot_Prodigy
                            if ('camalot' in hlow) or ('prodigy' in hlow):
                                try:
                                    extra = _camalot_extra_info(conn)
                                    for line in extra:
                                        if line not in tooltip_lines:
                                            tooltip_lines.append(line)
                                except Exception:
                                    pass
                            # If little core info present, try broader lookup across reference tables
                            has_core = any(('Min.PCB' in t) or ('Max.PCB' in t) or ('Weight' in t) for t in tooltip_lines)
                            if not has_core:
                                try:
                                    # lightweight inline lookup similar to propuestas()
                                    def _first_nonnull(col):
                                        try:
                                            vals = pdf[col].dropna().astype(str)
                                            if not vals.empty:
                                                return vals.iloc[0]
                                        except Exception:
                                            return None
                                        return None
                                    # As a fallback, add any size/weight-like hints present in the proposal table itself
                                    for c in pdf.columns:
                                        low = str(c).lower()
                                        if any(k in low for k in ('size','thick','weight','kg','print area','configuration')):
                                            v = _first_nonnull(c)
                                            if v:
                                                tooltip_lines.append(f"{c}: {v}")
                                    # de-duplicate while preserving order
                                    seen = set()
                                    tooltip_lines = [x for x in tooltip_lines if not (x in seen or seen.add(x))]
                                except Exception:
                                    pass
                            # Special images and info for Usuario/Categoria/Fecha de creacion in search proposals
                            lowh = h.lower().replace('_',' ').strip()
                            # Prefer explicit image values present in the proposal column
                            img_src = detect_image_in_column(pdf, header) or resolve_tech_image_src(h)
                            def _find_col(cols, keywords):
                                for c in cols:
                                    cl = str(c).lower()
                                    if all(k in cl for k in keywords):
                                        return c
                                return None
                            if lowh in ('usuario', 'categoria', 'categoría', 'fecha de creacion', 'fecha de creación'):
                                if lowh in ('usuario', 'categoria', 'categoría'):
                                    img_src = '/static/img/User.svg'
                                    ucol = _find_col(pdf.columns, ['Usuario']) or _find_col(pdf.columns, ['user'])
                                    try:
                                        def first_nonnull(col):
                                            try:
                                                vals = pdf[col].dropna().astype(str)
                                                if not vals.empty:
                                                    return vals.iloc[0]
                                            except Exception:
                                                return None
                                            return None
                                    except Exception:
                                        pass
                                    uval = first_nonnull(ucol) if ucol else None
                                    if uval:
                                        tooltip_lines.append(f"Creado por: {uval}")
                                else:
                                    img_src = '/static/img/Date.svg'
                                    fcol = _find_col(pdf.columns, ['fecha','creacion']) or _find_col(pdf.columns, ['fecha','creación'])
                                    fval = first_nonnull(fcol) if fcol else None
                                    if fval:
                                        tooltip_lines.append(f"Fecha de creación: {fval}")
                            tooltip_text = '; '.join([t for t in tooltip_lines if t])
                            tooltip = tooltip_text.replace('"', "'") if tooltip_text else ''
                            img_tag = f'<img src="{img_src}" alt="placeholder" title="Ver Info" data-info="{tooltip}" style="max-width:120px; max-height:80px;">'
                            image_row.append(img_tag)
                        img_df = pd.DataFrame([image_row], columns=pdf.columns)
                        pdf_display = pd.concat([img_df, pdf], ignore_index=True)
                    except Exception:
                        pdf_display = pdf

                    html = pdf_display.to_html(classes='data-table', index=False, escape=False)
                    title = tbl.strip('[]').replace('_', ' ')
                    proposals_matches.append({'title': title, 'html': html})

        except Exception as e:
            print(f"Error buscando tablas de Proposal dentro de search: {e}")

        return render_template('search.html', resultados=resultados, query=request.form, proposals=proposals_matches,
                               tecnologias_options=tecnologias_options, documentos_options=documentos_options)

    # GET -> render empty search form (provide options lists)
    return render_template('search.html', resultados=None,
                           tecnologias_options=tecnologias_options, documentos_options=documentos_options)


@app.route('/propuestas')
def propuestas():
    """Show tables related to proposals. Searches the database for tables with 'Proposal' in their name
    and renders them as separate proposal cards arranged horizontally. Drops ID column and injects a
    commented image-row placeholder in each table HTML so the user can later add images.
    """
    conn = get_connection()
    proposals = []
    try:
        sql = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND UPPER(TABLE_NAME) LIKE ?"
        tables_df = pd.read_sql(sql, conn, params=['%PROPOSAL%'])
        for _, row in tables_df.iterrows():
            tbl = row['TABLE_NAME']
            try:
                df = pd.read_sql(f"SELECT * FROM [{tbl}]", conn)
                if df.empty:
                    continue
                # drop ID-like columns
                df = df.drop(columns=[c for c in df.columns if str(c).lower() in ('id','idd','ident','id_')], errors='ignore')

                # If the table is in (Equipo, Costo) two-column vertical format,
                # convert to horizontal layout: header row = equipment names, second row = costs.
                try:
                    cols_lower = [str(c).lower() for c in df.columns]
                    if len(df.columns) == 2 and (('equipo' in cols_lower[0] or 'equipo' in cols_lower[1]) and ('costo' in cols_lower[0] or 'costo' in cols_lower[1])):
                        # first column assumed equipment names, second column costs
                        equipment = df.iloc[:, 0].astype(str).tolist()
                        costs = df.iloc[:, 1].astype(str).tolist()
                        # build a single-row dataframe with equipment as columns
                        df = pd.DataFrame([costs], columns=equipment)
                except Exception:
                    # if any error during transformation, keep original df
                    pass

                # Insert a visible image row with <img> in each column (below the header) including medidas.
                # Build a rich tooltip pulling:
                #  - Documento(s) (from tech table lookup)
                #  - Min / Max PCB sizes (+ variants M/L/XL for conveyors)
                #  - Thickness / Weight if available
                #  - Extra Camalot info (helper)
                #  - Special handling for Usuario / Categoria / Fecha de creacion
                try:
                    def _first_nonnull(local_df, col):
                        try:
                            vals = local_df[col].dropna().astype(str)
                            if not vals.empty:
                                return vals.iloc[0]
                        except Exception:
                            return None
                        return None

                    image_row = []
                    sizes_cache = {}
                    for header in df.columns:
                        h = str(header).strip()
                        hlow = h.lower()
                        # choose image (prefer explicit cell-based image)
                        try:
                            img_src = detect_image_in_column(df, header)
                        except Exception:
                            img_src = None
                        if not img_src:
                            try:
                                img_src = resolve_tech_image_src(h)
                            except Exception:
                                img_src = '/static/img/placeholder.svg'

                        # lookup medidas in cache or call helper
                        key = hlow
                        if key not in sizes_cache:
                            try:
                                sizes_cache[key] = get_equipment_pcb_sizes_cached(h, conn)
                            except Exception:
                                sizes_cache[key] = {'min': None, 'max': None, 'doc': None, 'docs': [], 'max_variants': {}, 'thick': {}, 'weight': {}}
                        sizes = sizes_cache[key] or {}
                        tooltip_lines = []
                        # Documento(s)
                        docs_list = sizes.get('docs') or []
                        doc_primary = docs_list[0] if docs_list else (sizes.get('doc') or 'No info')
                        tooltip_lines.append(f"Documento: {doc_primary}")
                        if len(docs_list) > 1:
                            tooltip_lines.append("Documento Secundario: " + ', '.join(docs_list[1:]))
                        # Source table if doc missing
                        if sizes.get('source_table') and not sizes.get('doc'):
                            tooltip_lines.append(f"Tabla: {sizes.get('source_table')}")
                        # Min / Max PCB
                        if sizes.get('min'):
                            mn = sizes['min']
                            tooltip_lines.append("Min.PCB (L X W) (mm): " + (f"{mn[0]}x{mn[1]}" if len(mn)>1 and mn[1] is not None else f"{mn[0]}"))
                        else:
                            tooltip_lines.append("Min.PCB (L X W) (mm): No info")
                        # Decide generic Max vs variants
                        variants = sizes.get('max_variants') or {}
                        include_generic_max = not variants.get('XL')  # skip generic if XL present
                        if include_generic_max and sizes.get('max'):
                            mx = sizes['max']
                            tooltip_lines.append("Max.PCB (L X W) (mm): " + (f"{mx[0]}x{mx[1]}" if len(mx)>1 and mx[1] is not None else f"{mx[0]}"))
                        # Conveyor variants
                        if any(t in hlow for t in ('conveyor','loader','unloader')):
                            def _fmt_tuple(t):
                                try:
                                    if isinstance(t,(list,tuple)):
                                        if len(t)>1 and t[1] is not None:
                                            return f"{t[0]}x{t[1]}"
                                        return f"{t[0]}"
                                    return str(t)
                                except Exception:
                                    return str(t)
                            for label in ['M','L','XL']:
                                if variants.get(label):
                                    tooltip_lines.append(f"Max.PCB (L X W) (mm) {label}: {_fmt_tuple(variants[label])}")
                            # any other variant labels
                            for lbl,val in variants.items():
                                if lbl not in ('M','L','XL'):
                                    tooltip_lines.append(f"Max.PCB (L X W) (mm) {lbl}: {_fmt_tuple(val)}")
                        # Thickness
                        thick = sizes.get('thick') or {}
                        th_val = None
                        if thick.get('min') is not None and thick.get('max') is not None and thick['min'] != thick['max']:
                            th_val = f"{thick['min']} - {thick['max']}"
                        elif thick.get('max') is not None:
                            th_val = f"{thick['max']}"
                        elif thick.get('min') is not None:
                            th_val = f"{thick['min']}"
                        elif thick.get('val') is not None:
                            th_val = f"{thick['val']}"
                        if th_val:
                            tooltip_lines.append(f"PCB Thickness (mm): {th_val}")
                        # Weight
                        weight = sizes.get('weight') or {}
                        w_val = weight.get('max') if weight.get('max') is not None else weight.get('val')
                        if w_val is not None:
                            tooltip_lines.append(f"PCB Max. Weight (kg): {w_val}")
                        # Camalot extra info
                        if 'camalot' in hlow or 'prodigy' in hlow:
                            try:
                                extra = _camalot_extra_info(conn)
                                for line in extra:
                                    if line not in tooltip_lines:
                                        tooltip_lines.append(line)
                            except Exception:
                                pass
                        # Direct fallback: if still minimal info (only Documento line), try proposal intrinsic columns
                        core_count = sum(1 for t in tooltip_lines if any(k in t for k in ('Min.PCB','Max.PCB','Thickness','Weight')))
                        if core_count == 0:
                            for c in df.columns:
                                lowc = str(c).lower()
                                if any(k in lowc for k in ('size','thick','weight','kg','print area','configuration')):
                                    v = _first_nonnull(df, c)
                                    if v:
                                        tooltip_lines.append(f"{c}: {v}")
                        # Special provenance columns
                        plain = hlow.replace('_',' ').strip()
                        def _find_col(cols, keywords):
                            for c in cols:
                                cl = str(c).lower()
                                if all(k in cl for k in keywords):
                                    return c
                            return None
                        if plain in ('usuario','categoria','categoría','fecha de creacion','fecha de creación'):
                            if plain in ('usuario','categoria','categoría'):
                                img_src = '/static/img/User.svg'
                                ucol = _find_col(df.columns,['usuario']) or _find_col(df.columns,['user'])
                                uval = _first_nonnull(df, ucol) if ucol else None
                                if uval:
                                    tooltip_lines.append(f"Creado por: {uval}")
                            else:
                                img_src = '/static/img/Date.svg'
                                fcol = _find_col(df.columns,['fecha','creacion']) or _find_col(df.columns,['fecha','creación'])
                                fval = _first_nonnull(df, fcol) if fcol else None
                                if fval:
                                    tooltip_lines.append(f"Fecha de creación: {fval}")
                        # Final tooltip
                        tooltip_text = '; '.join([t for t in tooltip_lines if t])
                        tooltip_attr = tooltip_text.replace('"', "'") if tooltip_text else ''
                        img_tag = f'<img src="{img_src}" alt="{h}" title="Ver Info" data-info="{tooltip_attr}" style="max-width:120px; max-height:80px;">'
                        image_row.append(img_tag)
                    img_df = pd.DataFrame([image_row], columns=df.columns)
                    df_display = pd.concat([img_df, df], ignore_index=True)
                except Exception:
                    df_display = df

                # produce html, allow raw HTML in cells (escape=False) so <img> renders
                html = df_display.to_html(classes='data-table', index=False, escape=False)
                # cleaned title from table name
                title = tbl.strip('[]').replace('_', ' ')
                proposals.append({'title': title, 'html': html})
            except Exception as e:
                print(f"Error leyendo tabla {tbl}: {e}")
    except Exception as e:
        print(f"Error buscando tablas de Proposal: {e}")
    finally:
        conn.close()

    return render_template('propuestas.html', proposals=proposals)


@app.route('/documentacion')
def documentacion():
    """Render a styled documentation page showing the Tecnologias_Tecnologias table

    The template will show each row and, when a URL-like column is present
    (Enlace/Link/URL), render a prominent button that opens that link.
    """
    conn = get_connection()
    try:
        try:
            df = pd.read_sql("SELECT * FROM [Tecnologias_Tecnologias]", conn)
        except Exception:
            df = pd.DataFrame()
        rows = []
        cols = []
        if not df.empty:
            cols = [str(c) for c in df.columns]
            # convert NaN to empty strings
            df = df.where(pd.notnull(df), '')
            for _, r in df.iterrows():
                row = { c: (r[c] if c in df.columns else '') for c in cols }
                # find first URL-like column name for this row (case-insensitive)
                url_col = None
                for candidate in cols:
                    low = candidate.lower()
                    if 'enlace' in low or 'link' in low or 'url' in low or 'href' in low:
                        val = row.get(candidate) or ''
                        if val and str(val).strip():
                            url_col = candidate
                            break
                row['_url_column'] = url_col
                rows.append(row)
        # show_back ensures the header renders a back button like other pages
        return render_template('documentacion.html', columns=cols, rows=rows, show_back=True, back_url='/')
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.route('/info/conveyor')
def info_conveyor():
    """Return HTML snippet with information from [Conveyor_LoaderUnloader].

    The content is a compact HTML table suitable for the modal body.
    """
    conn = get_connection()
    html = '<p>No hay información disponible.</p>'
    title = 'Conveyor'
    try:
        try:
            df = pd.read_sql("SELECT * FROM [Conveyor_LoaderUnloader]", conn)
        except Exception:
            df = pd.DataFrame()
        if not df.empty:
            # Optional filtering by query string 'q'
            q = (request.args.get('q') or '').strip()
            if q:
                try:
                    mask_any = df.apply(lambda r: r.astype(str).str.contains(q, case=False, na=False).any(), axis=1)
                    df = df[mask_any]
                except Exception:
                    pass
            # Limit number of rows/cols for readability if very large
            df_display = df.copy()
            # Replace NaN with empty for clean render
            df_display = df_display.where(pd.notnull(df_display), '')
            html = df_display.to_html(classes='data-table', index=False)
    except Exception as e:
        html = f'<p>Error al consultar Conveyor: {str(e)}</p>'
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return jsonify({'title': title, 'html': html})


@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json() or {}
    user = data.get('user')
    password = data.get('password')
    # validate against application-level admin users (not DB credentials)
    from db import validate_app_admin
    ok = validate_app_admin(user, password)
    if ok:
        session['admin_authenticated'] = True
        return jsonify({'success': True})
    return jsonify({'success': False})


@app.route('/user/create_account', methods=['POST'])
def user_create_account():
    data = request.get_json() or {}
    user = (data.get('user') or '').strip()
    password = data.get('password') or ''
    if not user or not password:
        return jsonify({'success': False, 'error': 'missing user or password'})
    conn = get_connection()
    try:
        # read users table
        try:
            df = pd.read_sql("SELECT * FROM [dbo].[Usuarios]", conn)
        except Exception:
            try:
                df = pd.read_sql("SELECT * FROM [Usuarios]", conn)
            except Exception as e:
                return jsonify({'success': False, 'error': 'Usuarios table not found'})

        cols = [str(c) for c in df.columns]
        cols_low = [c.lower() for c in cols]
        # find username and password column names
        user_col = None
        pass_col = None
        id_col = None
        for c, cl in zip(cols, cols_low):
            if 'usuario' in cl or 'user' in cl:
                user_col = c
            if 'pass' in cl:
                pass_col = c
            if cl == 'id' or cl.endswith('id') or 'ident' in cl:
                id_col = c

        # default column names if not found
        if not user_col:
            return jsonify({'success': False, 'error': 'no username column in Usuarios table'})

        # check duplicate
        try:
            exists = df[df[user_col].astype(str).str.lower() == user.lower()]
            if not exists.empty:
                return jsonify({'success': False, 'error': 'user exists'})
        except Exception:
            pass

        # Helper to detect if a column is IDENTITY (auto-increment)
        def _is_identity_column(conn, table_name, column_name):
            try:
                sql = (
                    "SELECT 1 "
                    "FROM sys.identity_columns ic "
                    "JOIN sys.objects o ON ic.object_id = o.object_id "
                    "WHERE o.type='U' AND o.name = ? AND COL_NAME(ic.object_id, ic.column_id) = ?"
                )
                iddf = pd.read_sql(sql, conn, params=[table_name, column_name])
                return (not iddf.empty)
            except Exception:
                return False

        # compute next id if id_col exists and is NOT identity; otherwise let SQL Server assign it
        next_id = None
        if id_col:
            is_ident = _is_identity_column(conn, 'Usuarios', id_col)
            if not is_ident:
                if id_col in df.columns and not df.empty:
                    try:
                        nxt = pd.to_numeric(df[id_col], errors='coerce')
                        maxv = int(nxt.max()) if not nxt.isnull().all() else 0
                        next_id = maxv + 1
                    except Exception:
                        next_id = len(df) + 1
                else:
                    next_id = 1

        # ensure password column exists, otherwise try to add PasswordHash column
        if not pass_col:
            try:
                cur = conn.cursor()
                cur.execute("ALTER TABLE [Usuarios] ADD [PasswordHash] NVARCHAR(MAX) NULL")
                conn.commit()
                pass_col = 'PasswordHash'
            except Exception:
                # if we can't add column, fail
                return jsonify({'success': False, 'error': 'no password column and cannot add one'})

        # insert new user
        cur = conn.cursor()
        insert_cols = []
        insert_vals = []
        if next_id is not None and id_col:
            insert_cols.append(f'[{id_col}]')
            insert_vals.append(next_id)
        insert_cols.append(f'[{user_col}]')
        insert_vals.append(user)
        insert_cols.append(f'[{pass_col}]')
        insert_vals.append(generate_password_hash(password))
        cols_sql = ','.join(insert_cols)
        placeholders = ','.join(['?'] * len(insert_vals))
        sql = f"INSERT INTO [Usuarios] ({cols_sql}) VALUES ({placeholders})"
        cur.execute(sql, insert_vals)
        conn.commit()
        return jsonify({'success': True, 'user': user})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


@app.route('/user/login', methods=['POST'])
def user_login():
    data = request.get_json() or {}
    user = (data.get('user') or '').strip()
    password = data.get('password') or ''
    if not user or not password:
        return jsonify({'success': False, 'error': 'missing credentials'})
    conn = get_connection()
    try:
        try:
            df = pd.read_sql("SELECT * FROM [dbo].[Usuarios]", conn)
        except Exception:
            df = pd.read_sql("SELECT * FROM [Usuarios]", conn)
        if df.empty:
            return jsonify({'success': False, 'error': 'no users'})
        cols = [str(c) for c in df.columns]
        cols_low = [c.lower() for c in cols]
        user_col = None
        pass_col = None
        for c, cl in zip(cols, cols_low):
            if 'usuario' in cl or 'user' in cl:
                user_col = c
            if 'pass' in cl:
                pass_col = c
        if not user_col:
            return jsonify({'success': False, 'error': 'no username column'})
        if not pass_col:
            return jsonify({'success': False, 'error': 'no password column'})

        # find user row
        try:
            matches = df[df[user_col].astype(str).str.lower() == user.lower()]
        except Exception:
            matches = df[df[user_col] == user]
        if matches.empty:
            return jsonify({'success': False, 'error': 'user not found'})
        row = matches.iloc[0]
        stored = row.get(pass_col)
        if stored is None:
            return jsonify({'success': False, 'error': 'no password stored'})
        try:
            ok = check_password_hash(str(stored), password)
        except Exception:
            # fallback to plain compare
            ok = (str(stored) == password)
        if ok:
            session['user_authenticated'] = True
            session['user'] = user
            return jsonify({'success': True, 'user': user})
        return jsonify({'success': False, 'error': 'invalid credentials'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


@app.route('/admin')
def admin_index():
    if not session.get('admin_authenticated'):
        return redirect(url_for('index'))
    return render_template('admin.html')


@app.route('/admin/tables')
def admin_tables():
    if not session.get('admin_authenticated'):
        return jsonify({'tables': []})
    conn = get_connection()
    try:
        sql = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'"
        df = pd.read_sql(sql, conn)
        tables = df['TABLE_NAME'].tolist()
        return jsonify({'tables': tables})
    except Exception as e:
        return jsonify({'tables': [], 'error': str(e)})
    finally:
        conn.close()


@app.route('/admin/table')
def admin_table():
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'no auth'})
    name = request.args.get('name')
    if not name:
        return jsonify({'error': 'missing name'})
    conn = get_connection()
    try:
        # Normalize table name (trim spaces and surrounding brackets)
        raw_name = str(name).strip()
        raw_name = raw_name[1:-1] if (raw_name.startswith('[') and raw_name.endswith(']')) else raw_name
        # Determine candidate schemas dynamically (actual schema(s) from INFORMATION_SCHEMA + common fallbacks)
        df = None
        last_error = None
        try:
            sch_df = pd.read_sql("SELECT TABLE_SCHEMA FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", conn, params=[raw_name])
            schemas = [str(s) for s in sch_df['TABLE_SCHEMA'].tolist()] if not sch_df.empty else []
        except Exception:
            schemas = []
        # Add common fallback schemas
        if 'dbo' not in [s.lower() for s in schemas]:
            schemas.append('dbo')
        # Try unqualified first, then schema-qualified variants
        candidates = [f"[{raw_name}]"] + [f"[{s}].[{raw_name}]" for s in schemas]
        for tbl_expr in candidates:
            try:
                sql = f"SELECT TOP 500 * FROM {tbl_expr}"
                df = pd.read_sql(sql, conn)
                break
            except Exception as e:
                last_error = e
                df = None
        if df is None:
            return jsonify({'error': f'error reading table {raw_name}: {last_error}'})
        # convert pandas NaN to Python None for JSON serialization
        df = df.where(pd.notnull(df), None)
        # Ensure all cell values are JSON serializable (convert unsupported types to str)
        def json_safe(v):
            if v is None:
                return None
            try:
                # simple types pass through
                if isinstance(v, (str, int, float, bool)):
                    # Guard against NaN/Infinity which break JSON.parse in browsers
                    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        return None
                    return v
                # for other types (Decimal, datetime, etc.), use str()
                return str(v)
            except Exception:
                return str(v)
        rows = []
        for _, r in df.iterrows():
            row_obj = {}
            for c in df.columns:
                row_obj[c] = json_safe(r[c])
            rows.append(row_obj)
        # look up tecnologia mapping if exists
        try:
            # try both raw name and bracketed name in mapping
            tdf = pd.read_sql("SELECT TOP 1 Tecnologia FROM [Tecnologias_Tecnologias] WHERE Documento = ? OR Documento = ?", conn, params=[raw_name, f'[{raw_name}]'])
            tech = None
            if not tdf.empty:
                tech = tdf.iloc[0,0]
        except Exception:
            tech = None
        return jsonify({'columns': df.columns.tolist(), 'rows': rows, 'tecnologia': tech})
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        conn.close()


@app.route('/admin/export_table_excel')
def admin_export_table_excel():
    if not session.get('admin_authenticated'):
        return jsonify({'success': False, 'error': 'no auth'})
    table = request.args.get('table')
    if not table:
        return jsonify({'success': False, 'error': 'missing table'})
    conn = get_connection()
    try:
        try:
            df = pd.read_sql(f"SELECT * FROM [{table}]", conn)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
        # write to excel in-memory
        buf = io.BytesIO()
        try:
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                sheet = str(table)[:31]
                df.to_excel(writer, index=False, sheet_name=sheet)
            buf.seek(0)
        except Exception:
            # fallback to openpyxl
            with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                sheet = str(table)[:31]
                df.to_excel(writer, index=False, sheet_name=sheet)
            buf.seek(0)
        filename = f"{table}.xlsx"
        return send_file(buf, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    finally:
        conn.close()


@app.route('/admin/export_all_tables_excel')
def admin_export_all_tables_excel():
    if not session.get('admin_authenticated'):
        return jsonify({'success': False, 'error': 'no auth'})
    conn = get_connection()
    try:
        # map table -> tecnologia if present
        try:
            map_df = pd.read_sql("SELECT Tecnologia, Documento FROM [Tecnologias_Tecnologias]", conn)
            mapping = { str(r['Documento']): str(r['Tecnologia']) for _, r in map_df.iterrows() }
        except Exception:
            mapping = {}

        # list all base tables
        try:
            tables_df = pd.read_sql("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'", conn)
            table_names = [str(x) for x in tables_df['TABLE_NAME'].tolist()]
        except Exception:
            table_names = []

        # group by tecnologia
        groups = {}
        for t in table_names:
            tech = mapping.get(t) or 'Sin_Tecnologia'
            groups.setdefault(tech, []).append(t)

        buf = io.BytesIO()
        try:
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                for tech, tabs in groups.items():
                    sheet = str(tech)[:31]
                    startrow = 0
                    for tbl in tabs:
                        try:
                            df = pd.read_sql(f"SELECT * FROM [{tbl}]", conn)
                        except Exception:
                            continue
                        # write a small header row with table name
                        header_df = pd.DataFrame([[f"Table: {tbl}"]])
                        header_df.to_excel(writer, index=False, header=False, sheet_name=sheet, startrow=startrow)
                        startrow += 1
                        df.to_excel(writer, index=False, sheet_name=sheet, startrow=startrow)
                        startrow += len(df) + 2
            buf.seek(0)
        except Exception:
            # fallback engine
            with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                for tech, tabs in groups.items():
                    sheet = str(tech)[:31]
                    startrow = 0
                    for tbl in tabs:
                        try:
                            df = pd.read_sql(f"SELECT * FROM [{tbl}]", conn)
                        except Exception:
                            continue
                        header_df = pd.DataFrame([[f"Table: {tbl}"]])
                        header_df.to_excel(writer, index=False, header=False, sheet_name=sheet, startrow=startrow)
                        startrow += 1
                        df.to_excel(writer, index=False, sheet_name=sheet, startrow=startrow)
                        startrow += len(df) + 2
            buf.seek(0)

        filename = 'all_tables_by_tecnologia.xlsx'
        return send_file(buf, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    finally:
        conn.close()


@app.route('/admin/update', methods=['POST'])
def admin_update():
    if not session.get('admin_authenticated'):
        return jsonify({'success': False, 'error': 'no auth'})
    data = request.get_json() or {}
    table = data.get('table')
    column = data.get('column')
    original_row = data.get('original_row') or {}
    new_value = data.get('new_value')
    if not table or not column:
        return jsonify({'success': False, 'error': 'missing params'})
    conn = get_connection()
    try:
        # Build WHERE clause matching all original_row fields. Use parameterized query.
        where_clauses = []
        params = []
        for k, v in original_row.items():
            if v is None:
                where_clauses.append(f"[{k}] IS NULL")
            else:
                where_clauses.append(f"[{k}] = ?")
                params.append(v)
        if not where_clauses:
            return jsonify({'success': False, 'error': 'cannot identify row'})
        set_clause = f"[{column}] = ?"
        params = [new_value] + params
        sql = f"UPDATE [{table}] SET {set_clause} WHERE {' AND '.join(where_clauses)}"
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return jsonify({'success': True, 'rows_affected': cur.rowcount})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


def _valid_identifier(name):
    """Basic validation for SQL identifiers used by admin actions.

    Reject names containing ']' or ';' to avoid breaking bracket escaping.
    """
    try:
        if not isinstance(name, str):
            return False
        if not name.strip():
            return False
        if ']' in name or ';' in name:
            return False
        return True
    except Exception:
        return False


def _sanitize_identifier(name):
    """Sanitize a friendly name into a SQL-safe identifier: replace non-alnum/_ with underscore."""
    try:
        s = str(name).strip()
        # replace spaces and non-alphanumeric characters with underscore
        s = re.sub(r'[^A-Za-z0-9_]', '_', s)
        # collapse multiple underscores
        s = re.sub(r'__+', '_', s)
        # trim leading/trailing underscores
        s = s.strip('_')
        return s or None
    except Exception:
        return None


@app.route('/admin/delete_table', methods=['POST'])
def admin_delete_table():
    if not session.get('admin_authenticated'):
        return jsonify({'success': False, 'error': 'no auth'})
    data = request.get_json() or {}
    table = data.get('table')
    if not _valid_identifier(table):
        return jsonify({'success': False, 'error': 'invalid table name'})
    conn = get_connection()
    try:
        # double-check existence
        sql_check = "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?"
        df = pd.read_sql(sql_check, conn, params=[table])
        if df.empty or int(df.iloc[0,0]) == 0:
            return jsonify({'success': False, 'error': 'table not found'})
        cur = conn.cursor()
        cur.execute(f"DROP TABLE [{table}]")
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


@app.route('/documents_for_technology')
def documents_for_technology():
    """Return a JSON list of Documento values filtered by friendly Tecnología.

    If no tech (or empty) is provided, returns all unique documentos.
    The comparison uses get_friendly_name over the raw Tecnologia values from
    Tecnologias_Tecnologias to match the same labels shown in the UI.
    """
    tech = (request.args.get('tech') or '').strip()
    conn = get_connection()
    try:
        try:
            df = pd.read_sql("SELECT Tecnologia, Documento FROM [Tecnologias_Tecnologias]", conn)
        except Exception:
            df = pd.DataFrame(columns=['Tecnologia','Documento'])
        docs = []
        if not df.empty:
            if tech:
                try:
                    for _, r in df.iterrows():
                        try:
                            if get_friendly_name(r['Tecnologia']) == tech and pd.notnull(r['Documento']):
                                docs.append(str(r['Documento']))
                        except Exception:
                            continue
                except Exception:
                    docs = []
            else:
                try:
                    docs = [str(x) for x in df['Documento'].dropna().astype(str).unique().tolist()]
                except Exception:
                    docs = []
        # dedupe and sort for stable UX
        seen = set()
        ordered = []
        for d in docs:
            if d not in seen:
                seen.add(d)
                ordered.append(d)
        try:
            ordered.sort()
        except Exception:
            pass
        return jsonify({'documents': ordered})
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.route('/admin/create_table', methods=['POST'])
def admin_create_table():
    if not session.get('admin_authenticated'):
        return jsonify({'success': False, 'error': 'no auth'})
    data = request.get_json() or {}
    table = data.get('table')
    columns = data.get('columns') or []
    rows = data.get('rows') or []
    tecnologia = data.get('tecnologia')
    # build final table name as Tecnologia_TableName when tecnologia provided
    final_table = table
    if tecnologia:
        base = _sanitize_identifier(table) or ''
        tech_part = _sanitize_identifier(tecnologia) or ''
        if tech_part:
            if base:
                final_table = f"{tech_part}_{base}"
            else:
                final_table = tech_part
    if not _valid_identifier(final_table):
        return jsonify({'success': False, 'error': 'invalid table name'})
    # simple columns validation
    if not isinstance(columns, list) or not columns:
        return jsonify({'success': False, 'error': 'invalid columns'})
    for c in columns:
        if not _valid_identifier(str(c)):
            return jsonify({'success': False, 'error': f'invalid column name: {c}'})
    conn = get_connection()
    try:
        # ensure table does not already exist
        sql_check = "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?"
        df = pd.read_sql(sql_check, conn, params=[final_table])
        if not df.empty and int(df.iloc[0,0]) > 0:
            return jsonify({'success': False, 'error': 'table already exists'})

        # build CREATE TABLE statement with NVARCHAR(MAX) columns
        cols_sql = ', '.join([f"[{str(c)}] NVARCHAR(MAX) NULL" for c in columns])
        create_sql = f"CREATE TABLE [{final_table}] ({cols_sql})"
        cur = conn.cursor()
        cur.execute(create_sql)
        # insert rows if provided
        if rows:
            placeholders = ','.join(['?'] * len(columns))
            insert_sql = f"INSERT INTO [{final_table}] ({', '.join(['['+str(c)+']' for c in columns])}) VALUES ({placeholders})"
            for r in rows:
                # ensure row length
                vals = list(r)[:len(columns)]
                # pad with None
                while len(vals) < len(columns):
                    vals.append(None)
                cur.execute(insert_sql, vals)
        conn.commit()
        # Note: do NOT automatically insert a mapping into Tecnologias_Tecnologias here.
        # Mapping between tecnologia and table should be managed explicitly by the admin
        # via the edit/alter flow to avoid accidental mappings.
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


@app.route('/admin/alter_table', methods=['POST'])
def admin_alter_table():
    """Allow adding columns, adding rows and renaming a table.

    Payload:
      {
        old_table: 'OldName',
        columns: ['col1','col2', ...],         # full desired column list
        rows: [[r1c1, r1c2, ...], ...],        # rows to insert (optional)
        new_table: 'NewFinalName',             # optional final table name
        tecnologia: 'TechName'                 # optional tecnologia to update mapping
      }
    """
    if not session.get('admin_authenticated'):
        return jsonify({'success': False, 'error': 'no auth'})
    data = request.get_json() or {}
    old_table = data.get('old_table')
    columns = data.get('columns') or []
    rows = data.get('rows') or []
    new_table = data.get('new_table')
    tecnologia = data.get('tecnologia')
    deleted_rows = data.get('deleted_rows') or []
    deleted_columns = data.get('deleted_columns') or []

    if not _valid_identifier(old_table):
        return jsonify({'success': False, 'error': 'invalid old table name'})
    if not isinstance(columns, list):
        return jsonify({'success': False, 'error': 'invalid columns'})
    for c in columns:
        if not _valid_identifier(str(c)):
            return jsonify({'success': False, 'error': f'invalid column name: {c}'})

    conn = get_connection()
    try:
        # fetch current columns for the table
        sql_cols = "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?"
        df_cols = pd.read_sql(sql_cols, conn, params=[old_table])
        existing_cols = [str(x) for x in df_cols['COLUMN_NAME'].tolist()] if not df_cols.empty else []

        cur = conn.cursor()

        # handle rename first (if requested and different)
        final_table = old_table
        if new_table and new_table != old_table:
            if not _valid_identifier(new_table):
                return jsonify({'success': False, 'error': 'invalid new table name'})
            # check destination does not exist
            df_check = pd.read_sql("SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", conn, params=[new_table])
            if not df_check.empty and int(df_check.iloc[0,0]) > 0:
                return jsonify({'success': False, 'error': 'target table name already exists'})
            # perform rename via sp_rename
            try:
                cur.execute(f"EXEC sp_rename '[{old_table}]', '{new_table}'")
                conn.commit()
                final_table = new_table
            except Exception as e:
                return jsonify({'success': False, 'error': f'rename failed: {e}'})

        # add any missing columns
        # delete specified rows (if any) BEFORE altering columns to avoid dropping columns referenced in original_row
        if isinstance(deleted_rows, list) and deleted_rows:
            for orig in deleted_rows:
                try:
                    where_clauses = []
                    params = []
                    for k, v in (orig.items() if isinstance(orig, dict) else []):
                        if v is None:
                            where_clauses.append(f"[{k}] IS NULL")
                        else:
                            where_clauses.append(f"[{k}] = ?")
                            params.append(v)
                    if not where_clauses:
                        # cannot identify row; skip
                        continue
                    del_sql = f"DELETE FROM [{final_table}] WHERE {' AND '.join(where_clauses)}"
                    cur.execute(del_sql, params)
                except Exception as e:
                    return jsonify({'success': False, 'error': f'delete row failed: {e}'})

        # drop any deleted columns requested
        if isinstance(deleted_columns, list) and deleted_columns:
            for dc in deleted_columns:
                if not _valid_identifier(str(dc)):
                    return jsonify({'success': False, 'error': f'invalid deleted column name: {dc}'})
                try:
                    # attempt to drop (if exists)
                    cur.execute(f"ALTER TABLE [{final_table}] DROP COLUMN [{dc}]")
                except Exception:
                    # if drop fails (not exists or other), continue with caution
                    pass

        # Attempt column renames when the client provided the original column list.
        # The frontend sends `original_columns` (array) so we can detect header edits
        # and perform a proper column rename instead of adding a new column.
        original_columns = data.get('original_columns') or []
        if isinstance(original_columns, list) and original_columns:
            try:
                # get current columns after any drops/renames so far
                try:
                    df_curr = pd.read_sql("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?", conn, params=[final_table])
                    existing_now = [str(x) for x in df_curr['COLUMN_NAME'].tolist()] if not df_curr.empty else []
                except Exception:
                    existing_now = existing_cols

                # iterate by position and rename when names differ
                nm = min(len(original_columns), len(columns))
                for i in range(nm):
                    oldcol = str(original_columns[i]) if original_columns[i] is not None else ''
                    newcol = str(columns[i]) if columns[i] is not None else ''
                    if not oldcol or not newcol or oldcol == newcol:
                        continue
                    # only rename if oldcol exists and newcol does not (avoid collisions)
                    if oldcol in existing_now and newcol not in existing_now:
                        if not _valid_identifier(newcol):
                            return jsonify({'success': False, 'error': f'invalid new column name: {newcol}'})
                        try:
                            # use sp_rename to rename the column
                            cur.execute(f"EXEC sp_rename '[{final_table}].[{oldcol}]', '{newcol}', 'COLUMN'")
                            conn.commit()
                            # update tracking list
                            try:
                                existing_now.remove(oldcol)
                            except Exception:
                                pass
                            existing_now.append(newcol)
                        except Exception as e:
                            return jsonify({'success': False, 'error': f'rename column {oldcol} failed: {e}'})
            except Exception:
                # non-fatal: continue and let subsequent add-column logic run
                pass

        # add any missing columns (recompute existing columns after drops?)
        # fetch current columns again
        try:
            df_cols_after = pd.read_sql("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?", conn, params=[final_table])
            existing_cols_after = [str(x) for x in df_cols_after['COLUMN_NAME'].tolist()] if not df_cols_after.empty else []
        except Exception:
            existing_cols_after = existing_cols

        for c in columns:
            if c not in existing_cols_after:
                try:
                    cur.execute(f"ALTER TABLE [{final_table}] ADD [{c}] NVARCHAR(MAX) NULL")
                except Exception as e:
                    return jsonify({'success': False, 'error': f'add column {c} failed: {e}'})

        # insert rows if provided
        if rows:
            # use the provided columns order for inserts
            cols_escaped = ', '.join([f'[{str(c)}]' for c in columns])
            placeholders = ','.join(['?'] * len(columns))
            insert_sql = f"INSERT INTO [{final_table}] ({cols_escaped}) VALUES ({placeholders})"
            for r in rows:
                vals = list(r)[:len(columns)]
                while len(vals) < len(columns):
                    vals.append(None)
                try:
                    cur.execute(insert_sql, vals)
                except Exception as e:
                    return jsonify({'success': False, 'error': f'insert row failed: {e}'})

        conn.commit()

        # update tecnologia mapping if requested (replace Documento values)
        if tecnologia and new_table:
            try:
                cur.execute("UPDATE [Tecnologias_Tecnologias] SET Documento = ? WHERE Documento = ?", (new_table, old_table))
                conn.commit()
            except Exception:
                pass

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


@app.route('/admin/technologies')
def admin_technologies():
    """Return a JSON list of distinct Tecnologia values from Tecnologias_Tecnologias."""
    if not session.get('admin_authenticated'):
        return jsonify({'technologies': []})
    conn = get_connection()
    try:
        sql = "SELECT DISTINCT Tecnologia FROM [Tecnologias_Tecnologias] WHERE Tecnologia IS NOT NULL"
        df = pd.read_sql(sql, conn)
        techs = []
        if not df.empty:
            techs = [str(x) for x in df['Tecnologia'].dropna().unique().tolist()]
        return jsonify({'technologies': techs})
    except Exception as e:
        return jsonify({'technologies': [], 'error': str(e)})
    finally:
        conn.close()


@app.route('/admin/tech_map')
def admin_tech_map():
    """Return mapping Tecnologia -> [Documento] based on Tecnologias_Tecnologias.

    Admin-only. Used by the frontend to filter tables by selected technology
    using the real relationship (Documento belongs to Tecnología).
    """
    if not session.get('admin_authenticated'):
        return jsonify({'map': {}})
    conn = get_connection()
    try:
        try:
            df = pd.read_sql("SELECT Tecnologia, Documento FROM [Tecnologias_Tecnologias] WHERE Tecnologia IS NOT NULL AND Documento IS NOT NULL", conn)
        except Exception as e:
            return jsonify({'map': {}, 'error': str(e)})
        mapping = {}
        if not df.empty:
            for _, r in df.iterrows():
                tech = str(r['Tecnologia'])
                doc = str(r['Documento'])
                if tech not in mapping:
                    mapping[tech] = []
                # avoid duplicates
                if doc not in mapping[tech]:
                    mapping[tech].append(doc)
        return jsonify({'map': mapping})
    finally:
        conn.close()


@app.route('/admin/tables_for_technology')
def admin_tables_for_technology():
    """Return list of tables that contain at least one row whose [Documento]
    value belongs to the selected Tecnología according to Tecnologias_Tecnologias.

    Excludes proposal tables. Admin-only.
    """
    if not session.get('admin_authenticated'):
        return jsonify({'tables': []})
    tech = request.args.get('tech')
    if not tech:
        return jsonify({'tables': []})
    conn = get_connection()
    try:
        # Get all Documentos linked to the selected technology
        try:
            docs_df = pd.read_sql("SELECT Documento FROM [Tecnologias_Tecnologias] WHERE Tecnologia = ? AND Documento IS NOT NULL", conn, params=[tech])
        except Exception as e:
            return jsonify({'tables': [], 'error': str(e)})
        if docs_df.empty:
            return jsonify({'tables': []})
        documentos = [str(x) for x in docs_df['Documento'].dropna().astype(str).tolist()]

        # Get all base tables except proposals
        all_df = pd.read_sql("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'", conn)
        table_names = [str(x) for x in all_df['TABLE_NAME'].tolist()]
        table_names = [t for t in table_names if 'PROPOSAL' not in t.upper()]

        result = []
        cur = conn.cursor()

        # helper to check column existence
        def has_documento_column(tbl):
            try:
                cdf = pd.read_sql("SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ? AND COLUMN_NAME = 'Documento'", conn, params=[tbl])
                return (not cdf.empty) and int(cdf.iloc[0,0]) > 0
            except Exception:
                return False

        # function to chunk list
        def chunks(lst, n):
            for i in range(0, len(lst), n):
                yield lst[i:i+n]

        # Normalize documentos to check direct table-name mappings (some entries may be stored as
        # the table name itself). Accept values like 'TableName' or '[TableName]'.
        documentos_raw = [str(x).strip() for x in documentos]
        documentos_unbr = [d[1:-1] if d.startswith('[') and d.endswith(']') else d for d in documentos_raw]
        # case-insensitive set for direct name matching
        docs_norm = set([d.lower() for d in (documentos_raw + documentos_unbr)])

        # prepare normalized technology tokens for table-name prefix matching
        tech_low = str(tech or '').strip().lower()
        tech_sanit = re.sub(r'[^A-Za-z0-9_]', '_', str(tech or '')).strip().lower()

        for t in table_names:
            try:
                t_low = str(t or '').strip().lower()
                # 1) If the table name is directly listed as a Documento for the selected tech,
                #    include it immediately (covers tables that don't have a Documento column).
                if t_low in docs_norm or f'[{t}]'.lower() in docs_norm:
                    result.append(t)
                    continue

                # 2) If the table name uses a prefix naming convention like 'Conveyor_*' where
                #    the prefix matches the selected technology, include it.
                if tech_low and (t_low.startswith(tech_low + '_') or (tech_sanit and t_low.startswith(tech_sanit + '_'))):
                    result.append(t)
                    continue

                # 3) If the friendly technology derived from the table name matches the selected tech,
                #    include the table (covers cases where get_friendly_name maps the table to the tech).
                try:
                    if get_friendly_name(t) == tech:
                        result.append(t)
                        continue
                except Exception:
                    pass

                # 4) Otherwise require the table to have a Documento column and check for matching values
                if not has_documento_column(t):
                    continue
                found = False
                for chunk in chunks(documentos, 50):
                    placeholders = ','.join(['?'] * len(chunk))
                    sql = f"SELECT TOP 1 1 AS hasMatch FROM [{t}] WHERE [Documento] IN ({placeholders})"
                    try:
                        df = pd.read_sql(sql, conn, params=chunk)
                        if not df.empty:
                            found = True
                            break
                    except Exception:
                        # if query fails (e.g., permissions or type issues), skip table
                        break
                if found:
                    result.append(t)
            except Exception:
                continue

        return jsonify({'tables': result})
    finally:
        conn.close()

@app.route('/admin/users')
def admin_users():
    """Return list of usernames from Usuarios table. Admin-only."""
    if not session.get('admin_authenticated'):
        return jsonify({'users': []})
    conn = get_connection()
    try:
        try:
            df = pd.read_sql("SELECT * FROM [dbo].[Usuarios]", conn)
        except Exception:
            df = pd.read_sql("SELECT * FROM [Usuarios]", conn)
        if df.empty:
            return jsonify({'users': []})
        # heuristically find username column
        cols = [str(c) for c in df.columns]
        user_col = None
        for c in cols:
            if 'usuario' in c.lower() or 'user' in c.lower():
                user_col = c
                break
        if not user_col:
            # fallback to first column
            user_col = cols[0]
        users = [str(x) for x in df[user_col].dropna().unique().tolist()]
        return jsonify({'users': users})
    except Exception as e:
        return jsonify({'users': [], 'error': str(e)})
    finally:
        conn.close()


@app.route('/create_proposal', methods=['POST'])
def create_proposal():
    """Create a Proposal_<name> table from selected columns.

    Requires a signed-in user (session['user_authenticated']) or admin.
    The created table will have two provenance columns prepended:
      - 'Usuario' : username from session['user']
      - 'Fecha de creacion' : ISO timestamp when the table is created
    """
    if not (session.get('user_authenticated') or session.get('admin_authenticated')):
        return jsonify({'success': False, 'error': 'no auth'})

    data = request.get_json() or {}
    name = data.get('name')
    columns = data.get('columns') or []
    counts = data.get('counts') or []
    rows = data.get('rows') or []
    if not name:
        return jsonify({'success': False, 'error': 'missing name'})
    # build final table name
    safe_suffix = _sanitize_identifier(name) or None
    if not safe_suffix:
        return jsonify({'success': False, 'error': 'invalid name'})
    final_table = f"Proposal_{safe_suffix}"
    if not _valid_identifier(final_table):
        return jsonify({'success': False, 'error': 'invalid final table name'})
    if not isinstance(columns, list) or not columns:
        return jsonify({'success': False, 'error': 'invalid columns'})
    # Expand columns according to counts if provided (counts aligns with columns)
    final_columns = []
    try:
        if isinstance(counts, list) and len(counts) == len(columns):
            for i, col in enumerate(columns):
                try:
                    c = int(counts[i])
                except Exception:
                    c = 1
                if c <= 1:
                    final_columns.append(col)
                else:
                    # first instance keeps original name, subsequent ones get suffixed sanitized names
                    final_columns.append(col)
                    base = _sanitize_identifier(col) or 'col'
                    # ensure we don't collide with previous names
                    for k in range(2, c+1):
                        candidate = f"{base}_{k}"
                        # if candidate already exists, increment suffix until unique
                        idx = 2
                        while candidate in final_columns:
                            idx += 1
                            candidate = f"{base}_{k}_{idx}"
                        final_columns.append(candidate)
        else:
            final_columns = list(columns)
    except Exception:
        final_columns = list(columns)
    # prepend provenance columns
    provenance_user = session.get('user') or 'unknown'
    # Use local time (configurable via APP_TZ) so stored DATETIME2 matches expected local hour
    # Trim microseconds for cleaner display
    provenance_ts = now_local().replace(microsecond=0)

    # Use display-friendly column names for provenance
    prov_cols = ['Usuario', 'Fecha de creacion']

    conn = get_connection()
    try:
        # ensure table does not already exist
        df_check = pd.read_sql("SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", conn, params=[final_table])
        if not df_check.empty and int(df_check.iloc[0,0]) > 0:
            return jsonify({'success': False, 'error': 'table already exists'})
        cur = conn.cursor()
        # final column list includes provenance columns first
        all_columns = list(prov_cols) + list(final_columns)
        # Define SQL types: 'Fecha de creacion' should be DATETIME2, others NVARCHAR
        def _col_sql_def(col_name):
            cn = str(col_name)
            if cn == 'Fecha de creacion':
                return f"[{cn}] DATETIME2 NULL"
            # Keep 'Usuario' and all other dynamic columns as NVARCHAR(MAX)
            return f"[{cn}] NVARCHAR(MAX) NULL"
        cols_sql = ', '.join([_col_sql_def(c) for c in all_columns])
        create_sql = f"CREATE TABLE [{final_table}] ({cols_sql})"
        cur.execute(create_sql)
        # Insert provided rows, prepending provenance values (user, timestamp)
        placeholders = ','.join(['?'] * len(all_columns))
        insert_sql = f"INSERT INTO [{final_table}] ({', '.join(['['+str(c)+']' for c in all_columns])}) VALUES ({placeholders})"
        if rows:
            for r in rows:
                vals = list(r)[:len(final_columns)]
                while len(vals) < len(final_columns):
                    vals.append(None)
                # prepend provenance values (user NVARCHAR, timestamp as DATETIME2)
                row_vals = [provenance_user, provenance_ts] + vals
                cur.execute(insert_sql, row_vals)
        else:
            # If no rows provided, insert a single provenance-only row so the 'Usuario' and 'Fecha de creacion'
            # columns contain the creator info. Other columns will be NULL.
            row_vals = [provenance_user, provenance_ts] + [None] * len(final_columns)
            try:
                cur.execute(insert_sql, row_vals)
            except Exception:
                # If insert fails for any reason, continue without raising to avoid leaving the table partially created
                pass
        conn.commit()
        return jsonify({'success': True, 'table': final_table})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


if __name__ == '__main__':
    # Run the development server. For packaging and single-click runs use
    # the `run_app.py` wrapper which starts the server without the reloader
    # and opens the browser once.
    Timer(1.0, lambda: webbrowser.open_new('http://0.0.0.0:5000')).start()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)