"""Rebuild the 42 North Retail Flooring Proposals workbook with a premium, consistent design system.
Data comes from model.json (extracted from the original). Every number is carried over unchanged;
every total is a live formula. Run: python3 build.py  ->  out/42_North_Retail_Flooring_Proposals.xlsx
"""
import json, re, math, os, sys, datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
from openpyxl.comments import Comment
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.formatting.rule import DataBarRule
from openpyxl.worksheet.pagebreak import Break, RowBreak
from openpyxl.worksheet.hyperlink import Hyperlink
from PIL import Image as PILImage

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = json.load(open(os.path.join(HERE, 'model.json')))
OUT = os.path.join(HERE, 'out', '42_North_Retail_Flooring_Proposals.xlsx')
MEDIA = os.path.join(HERE, 'unz')

# ----------------------------------------------------------------------------- design tokens
FONT = 'Garamond'
ISSUER = 'Dynamic Home Solutions (DHS)'
CLIENT = '42 North'
DOC_KIND = 'RETAIL FLOORING PROPOSAL'
TODAY = datetime.date(2026, 9, 24)

C = dict(
    NAVY='0E2841',    # titles, TOTAL band (workbook theme dark-2)
    BRAND='156082',   # brand teal-navy (existing brand colour)
    ACCENT='44B3E1',  # sky accent (existing brand colour)
    TINT='E8F4FA',    # light brand tint (existing)
    TINT2='C0E6F5',   # deposit band (existing)
    INK='1B2A38',     # body text
    GRAY='5B6770',    # secondary text
    GRAY_LT='7A8590', # tertiary text / item numbers
    RULE='D9DEE5',    # hairline rules
    RULE_DK='9AA7B2', # stronger rules
    SURFACE='F6F8FA', # very light surface
    WHITE='FFFFFF',
    RED='C00000', AMBER='FFF2CC', AMBER_DK='D4A017',
    TAB_GRAY='B8C4CE', TAB_AMBER='F2C94C',
)
COLS = {'A': 2.5, 'B': 5, 'C': 60, 'D': 11, 'E': 15, 'F': 17, 'G': 2.5}
FMT_MONEY = '$#,##0.00_);($#,##0.00);"–"_)'     # _) pads the right edge by one ")" so figures never touch a rule
FMT_MONEY0 = '$#,##0_);($#,##0);"–"_)'
FMT_PCT = '0.00%_)'
FMT_TEXT_R = '@_)'

STATUS_STYLE = {  # fill, text
    'Completed':     ('BRAND', 'WHITE'),
    'In process':    ('ACCENT', 'NAVY'),
    'Proposal':      ('TINT', 'BRAND'),
    'Needs revisit': ('AMBER', 'RED'),
}
TAB_COLOR = {'Completed': 'BRAND', 'In process': 'ACCENT', 'Proposal': 'TAB_GRAY', 'Needs revisit': 'TAB_AMBER'}

RENAME = {
    'Completed-GD Braintree': 'Completed - GD Braintree',
    'Completed-Abington Fam Dental ': 'Completed - Abington Fam Dental',
    'Completed-GD Peabody ': 'Completed - GD Peabody',
    'Completed-Portland Dental': 'Completed - Portland Dental',
    'Completed- GD Natick ': 'Completed - GD Natick',
    'Completed- Medford': 'Completed - Medford',
    'Completed-Willimantic Dental ': 'Completed - Willimantic Dental',
    'Inprocess-Canton Dental': 'In Process - Canton Dental',
    'In Process-GD Rochester': 'In Process - GD Rochester',
    'Chelmsford Office ': 'Chelmsford Office',
    'Medford- Full (Mat + Labor)': 'Medford - Full (Mat + Labor)',
}
OVERVIEW_LABEL = {   # tab -> label shown on the Overview when practice names repeat
    'Completed - Medford': 'Medford Office — Labor + install materials',
    'Medford - Full (Mat + Labor)': 'Medford Office — Full (materials + labor)',
    'New Haven Dental Flooring': 'New Haven Dental — Flooring',
    'New Haven Dental Painting': 'New Haven Dental — Painting',
    'Great Hill Dental - Partial': 'Great Hill Dental — Partial (465 SF)',
    'Great Hill Dental Full LVP': 'Great Hill Dental — Full LVP (2,818 SF)',
}
TITLE_OVERRIDE = {
    'Meriden Dental': ('Meriden Dental', 'Preferred pricing'),
    'New Haven Dental Painting': ('New Haven Dental', None),
}

# ----------------------------------------------------------------------------- style helpers
def font(size=11.5, bold=False, italic=False, color='INK', underline=None):
    return Font(name=FONT, size=size, bold=bold, italic=italic, color=C.get(color, color), underline=underline)

def fill(color):
    return PatternFill('solid', fgColor=C.get(color, color))

def side(color='RULE', style='thin'):
    return Side(style=style, color=C.get(color, color))

def align(h='left', v='center', wrap=False, indent=0):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap, indent=indent)

def cells(ws, rng):
    for row in ws[rng]:
        for c in (row if isinstance(row, tuple) else (row,)):
            yield c

def style(ws, rng, font_=None, fill_=None, align_=None, top=None, bottom=None, left=None, right=None, fmt=None):
    for c in cells(ws, rng):
        if font_: c.font = font_
        if fill_: c.fill = fill_
        if align_: c.alignment = align_
        if fmt: c.number_format = fmt
        if any([top, bottom, left, right]):
            b = c.border
            c.border = Border(top=top or b.top, bottom=bottom or b.bottom, left=left or b.left, right=right or b.right)

def set_widths(ws, widths):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

# ----------------------------------------------------------------------------- text helpers
def clean_desc(d):
    d = d.replace('​', '').strip()
    d = re.sub(r'^(Labor|Materials|Material)\s*-?\s*', '', d, flags=re.I)
    d = re.sub(r'\s{2,}', ' ', d)
    d = d.replace('Leveleler', 'Leveler')
    d = re.sub(r'(\S)-\s+', r'\1 – ', d)      # "Rip/Haul- Carpet" -> "Rip/Haul – Carpet"
    d = re.sub(r'\s*[-–]?\s*Customer to [Ss]elect [Cc]olor\b', ' – customer to select color', d)
    d = re.sub(r'\s+–\s*$', '', d)
    return d.strip()

def clean_title(s):
    t = s['title'].replace('​', '').strip()
    t = re.sub(r'^Completed-\s*', '', t)
    t = re.sub(r'\s*-\s*(Completed|Needs Revisit)\s*$', '', t, flags=re.I)
    t = t.replace('Fam Dental', 'Family Dental').strip()
    if s['orig_name'] in TITLE_OVERRIDE:
        t = TITLE_OVERRIDE[s['orig_name']][0]
    return t

def status_of(s):
    n = s['orig_name'].lower()
    if 'needs revisit' in (s['title'] or '').lower(): return 'Needs revisit'
    if n.startswith('completed'): return 'Completed'
    if n.startswith('inprocess') or n.startswith('in process'): return 'In process'
    return 'Proposal'

def scope_of(s):
    descs = ' | '.join(it['desc'].lower() for it in s['items'])
    parts = []
    if re.search(r'install\s+lv[tp]', descs) or 'install lvt' in descs: parts.append('LVT')
    if 'install carpet tile' in descs: parts.append('carpet tile')
    if 'broadloom' in descs: parts.append('broadloom carpet')
    if 'painting' in descs: parts.append('painting')
    if 'wallpaper' in descs: parts.append('wallpaper removal')
    if not parts:
        return 'Flooring'
    if parts[0] in ('painting', 'wallpaper removal'):
        return (' & '.join(parts)).capitalize()
    txt = ' & '.join(parts) + ' flooring'
    return txt[0].upper() + txt[1:]

def subtitle_of(s, title):
    if s['orig_name'] in TITLE_OVERRIDE and TITLE_OVERRIDE[s['orig_name']][1]:
        extra = TITLE_OVERRIDE[s['orig_name']][1]
    else:
        raw = (s.get('subtitle') or '').replace('​', '').strip()
        raw_title = (s['title'] or '').strip()
        extra = raw
        for t in (title, raw_title):
            m = re.match(r'^' + re.escape(t) + r'\s*[-—–]\s*(.*)$', raw)
            if m:
                extra = m.group(1).strip(); break
        if raw == title or raw == raw_title:
            extra = ''
    scope = scope_of(s)
    extra = re.sub(r'\s+-\s+', ' — ', extra).strip(' -—–')
    if extra:
        ew = set(re.findall(r'[a-z]+', extra.lower())) - {'and', 'the'}
        sw = set(re.findall(r'[a-z]+', scope.lower()))
        if ew and ew <= sw:
            extra = ''
    return scope + (f'  —  {extra}' if extra else '')

def tax_text(s):
    t = s['tax']
    if t is None:
        notes = ' '.join(n['text'] for n in s['notes'])
        return 'Included in price (PA)' if 'Pennsylvania' in notes else 'Not applicable'
    if t['rate'] == 0:
        return '0% — New Hampshire' if 'NH' in t['note'] else '0%'
    return f"{t['rate']*100:g}% on materials"

def qty_fmt(v):
    if isinstance(v, (int, float)) and abs(v - round(v)) < 1e-9: return '#,##0_)'
    if abs(v * 10 - round(v * 10)) < 1e-9: return '#,##0.0_)'
    return '#,##0.00_)'

def price_fmt(v):
    if isinstance(v, (int, float)) and abs(v * 1000 - round(v * 1000)) < 1e-9 and abs(v * 100 - round(v * 100)) > 1e-9:
        return '$#,##0.000_)'
    return '$#,##0.00_)'

# Wrapped-row heights are computed from real glyph metrics (EB Garamond, metrically close to Monotype Garamond),
# with a 12% width safety margin so Excel never clips a line that LibreOffice would have fitted.
from PIL import ImageFont
_FONT_FILE = os.path.expanduser('~/.fonts/EBGaramond-VF.ttf')
_font_cache = {}
def _pil_font(pt, bold=False):
    key = (pt, bold)
    if key not in _font_cache:
        f = ImageFont.truetype(_FONT_FILE, size=int(round(pt * 96 / 72)))
        try:
            f.set_variation_by_name('Bold' if bold else 'Regular')
        except Exception:
            pass
        _font_cache[key] = f
    return _font_cache[key]
def wrapped_lines(text, width_px, pt=10.5, bold=False, safety=1.06):
    f = _pil_font(pt, bold)
    avail = width_px / safety
    lines, cur = 1, ''
    for word in text.split(' '):
        trial = (cur + ' ' + word).strip()
        if f.getlength(trial) <= avail or not cur:
            cur = trial
        else:
            lines += 1; cur = word
    return lines
NOTES_WIDTH_PX = int((COLS['C'] + COLS['D'] + COLS['E'] + COLS['F']) * 7 + 3 * 5 - 14)   # merged C:F minus indent
def wrap_height(text, width_px=NOTES_WIDTH_PX, pt=10.5, bold=False, line=13.8, pad=4):
    return wrapped_lines(text, width_px, pt, bold) * line + pad

# ----------------------------------------------------------------------------- groups
def build_groups(s):
    """Return ordered list of (label, [items]) plus the set of item rows excluded from their subtotal."""
    by_row = {it['row']: it for it in s['items']}
    groups = {k: list(v) for k, v in s['groups'].items()}
    excluded = set()
    for r in s['unassigned_items']:
        it = by_row[r]
        if 'freight' in it['desc'].lower() or 'distribution' in it['desc'].lower():
            groups.setdefault('Freight', []).append(r)
        else:
            # keep it visible in the group its description implies, but out of the subtotal (fidelity to original)
            g = 'Labor' if it['desc'].lower().startswith('labor') else 'Materials'
            groups.setdefault(g, []).append(r); excluded.add(r)
    synthetic = []
    fr = next((x for x in s['summary'] if x['label'].lower().startswith('freight')), None)
    if fr and not groups.get('Freight') and not (isinstance(fr['formula'], str) and str(fr['formula']).startswith('=')) and fr['value']:
        synthetic.append({'row': -1, 'desc': 'Freight & distribution', 'qty': 1, 'unit_price': fr['value'], 'line_total': None,
                          'qty_v': 1, 'unit_price_v': fr['value'], 'line_total_v': fr['value'], 'comment': None})
        groups['Freight'] = [-1]; by_row[-1] = synthetic[0]
    order = ['Labor', 'Materials', 'Freight', 'Scope of work']
    out = []
    for g in order:
        rows = groups.get(g)
        if rows:
            out.append((g, [by_row[r] for r in sorted(rows)]))
    return out, excluded

GROUP_LABEL = {'Labor': 'LABOR', 'Materials': 'MATERIALS', 'Freight': 'FREIGHT & DISTRIBUTION', 'Scope of work': 'SCOPE OF WORK'}

# ----------------------------------------------------------------------------- proposal sheet
def build_proposal(wb, s, index):
    name = RENAME.get(s['orig_name'], s['orig_name']).strip()
    ws = wb.create_sheet(name)
    ws.sheet_view.showGridLines = False
    ws.sheet_view.showRowColHeaders = False
    ws.sheet_view.zoomScale = 100
    set_widths(ws, COLS)
    title = clean_title(s); status = status_of(s); subtitle = subtitle_of(s, title)
    ws.sheet_properties.tabColor = C[TAB_COLOR[status]]
    info = {'sheet': name, 'title': title, 'subtitle': subtitle, 'status': status, 'tax_text': tax_text(s), 'refs': {}, 'expected': {}}

    # -- header block
    ws.row_dimensions[1].height = 6
    style(ws, 'A1:G1', fill_=fill('BRAND'))
    ws.row_dimensions[2].height = 14
    ws.row_dimensions[3].height = 18
    ws.merge_cells('B3:D3'); c = ws['B3']; c.value = f'{CLIENT.upper()}   |   {DOC_KIND}'; c.font = font(9, bold=True, color='BRAND'); c.alignment = align('left', indent=0)
    c = ws['F3']; c.value = status.upper()
    sf, st = STATUS_STYLE[status]
    style(ws, 'F3:F3', font_=font(8.5, bold=True, color=st), fill_=fill(sf), align_=align('center'))
    ws.row_dimensions[4].height = 38
    ws.merge_cells('B4:F4'); c = ws['B4']; c.value = title; c.font = font(24, bold=True, color='NAVY'); c.alignment = align('left', 'bottom')
    ws.row_dimensions[5].height = 22
    ws.merge_cells('B5:F5'); c = ws['B5']; c.value = subtitle; c.font = font(13, italic=True, color='GRAY'); c.alignment = align('left', 'top')
    ws.row_dimensions[6].height = 6
    style(ws, 'B6:F6', bottom=side('BRAND', 'medium'))
    ws.row_dimensions[7].height = 15
    ws.row_dimensions[8].height = 20
    ws.merge_cells('D7:E7'); ws.merge_cells('D8:E8')
    for col, lab, val in (('C', 'PREPARED BY', ISSUER), ('D', 'TAX BASIS', info['tax_text']), ('F', 'PROPOSAL TOTAL', None)):
        ws[f'{col}7'] = lab; ws[f'{col}7'].font = font(8.5, bold=True, color='GRAY_LT'); ws[f'{col}7'].alignment = align('left' if col != 'F' else 'right', 'bottom')
        ws[f'{col}8'] = val; ws[f'{col}8'].font = font(11.5, color='NAVY'); ws[f'{col}8'].alignment = align('left' if col != 'F' else 'right', 'top')
    ws['F7'].number_format = FMT_TEXT_R
    ws['F8'].font = font(14, bold=True, color='NAVY'); ws['F8'].number_format = FMT_MONEY   # formula filled in once the TOTAL row exists
    ws.row_dimensions[9].height = 12

    # -- table header
    r = 10
    ws.row_dimensions[r].height = 24
    for col, lab, h in (('B', '#', 'center'), ('C', 'DESCRIPTION', 'left'), ('D', 'QTY', 'right'), ('E', 'UNIT PRICE', 'right'), ('F', 'LINE TOTAL', 'right')):
        c = ws[f'{col}{r}']; c.value = lab; c.font = font(10, bold=True, color='WHITE'); c.fill = fill('BRAND'); c.alignment = align(h, indent=1 if h == 'left' else 0)
        if h == 'right': c.number_format = FMT_TEXT_R
    r += 1

    groups, excluded = build_groups(s)
    group_ranges = {}
    n = 0
    for gi, (g, items) in enumerate(groups):
        ws.row_dimensions[r].height = 20
        style(ws, f'B{r}:F{r}', fill_=fill('TINT'), bottom=side('RULE'))
        c = ws[f'C{r}']; c.value = GROUP_LABEL[g]; c.font = font(10, bold=True, color='BRAND'); c.alignment = align('left', indent=1)
        r += 1
        first = r; rows_in_sum = []
        for it in items:
            n += 1
            ws.row_dimensions[r].height = 19
            ws[f'B{r}'] = n; ws[f'B{r}'].number_format = '00'; ws[f'B{r}'].font = font(9.5, color='GRAY_LT'); ws[f'B{r}'].alignment = align('center')
            desc = clean_desc(it['desc'])
            ws[f'C{r}'] = desc; ws[f'C{r}'].font = font(11.5); ws[f'C{r}'].alignment = align('left', indent=1)
            desc_lines = wrapped_lines(desc, int(COLS['C'] * 7 - 12), pt=11.5)
            if desc_lines > 1:
                ws.row_dimensions[r].height = 16 * desc_lines + 6
                ws[f'C{r}'].alignment = align('left', 'top', wrap=True, indent=1)
            qty = it['qty_v']; price = it['unit_price_v']; lt = it['line_total_v']
            ws[f'D{r}'] = qty; ws[f'D{r}'].number_format = qty_fmt(qty); ws[f'D{r}'].font = font(11.5); ws[f'D{r}'].alignment = align('right')
            lump = (isinstance(it['unit_price'], str) and str(it['unit_price']).startswith('=')) or \
                   (not (isinstance(it['line_total'], str) and str(it['line_total']).startswith('=')) and it['line_total'] is not None and abs(qty * price - lt) > 0.005)
            if lump:
                ws[f'F{r}'] = lt                      # agreed lump-sum amount (as in the original)
                ws[f'E{r}'] = 'lump sum'
                expected_lt = lt
            else:
                ws[f'E{r}'] = price
                ws[f'F{r}'] = f'=D{r}*E{r}'
                expected_lt = qty * price
            ws[f'E{r}'].number_format = price_fmt(price) if not lump else FMT_TEXT_R; ws[f'E{r}'].font = font(11.5) if not lump else font(10.5, italic=True, color='GRAY'); ws[f'E{r}'].alignment = align('right')
            ws[f'F{r}'].number_format = FMT_MONEY; ws[f'F{r}'].font = font(11.5); ws[f'F{r}'].alignment = align('right')
            style(ws, f'B{r}:F{r}', bottom=side('RULE', 'hair'))
            if desc_lines > 1:
                for col in 'BDEF':
                    a = ws[f'{col}{r}'].alignment; ws[f'{col}{r}'].alignment = Alignment(horizontal=a.horizontal, vertical='top', wrap_text=a.wrap_text, indent=a.indent)
            if it.get('comment'):
                ws[f'C{r}'].comment = Comment(it['comment'], 'Matt Levy')
            if it['row'] not in excluded:
                rows_in_sum.append(r)
            info['expected'].setdefault('lines', []).append((r, expected_lt, it['line_total_v']))
            r += 1
        group_ranges[g] = (first, r - 1, rows_in_sum)
        if gi < len(groups) - 1:
            ws.row_dimensions[r].height = 6; r += 1

    # -- summary block
    ws.row_dimensions[r].height = 10; r += 1
    summary_top = r
    def sum_formula(rows):
        # contiguous runs -> SUM(F1:F2,F5:F7)
        runs = []; 
        for x in rows:
            if runs and x == runs[-1][1] + 1: runs[-1][1] = x
            else: runs.append([x, x])
        return '=SUM(' + ','.join(f'F{a}:F{b}' if a != b else f'F{a}' for a, b in runs) + ')'
    def summary_row(label, formula, ref, rate=None, rate_fmt=FMT_PCT, height=20, lab_font=None, val_font=None, fill_color=None, top=None, bottom=None):
        nonlocal r
        ws.row_dimensions[r].height = height
        ws[f'C{r}'] = label; ws[f'C{r}'].font = lab_font or font(11, color='GRAY'); ws[f'C{r}'].alignment = align('left', indent=1)
        if rate is not None:
            ws[f'E{r}'] = rate; ws[f'E{r}'].number_format = rate_fmt; ws[f'E{r}'].font = (val_font or font(11, color='GRAY')); ws[f'E{r}'].alignment = align('right')
        ws[f'F{r}'] = formula; ws[f'F{r}'].number_format = FMT_MONEY; ws[f'F{r}'].font = val_font or font(11.5); ws[f'F{r}'].alignment = align('right')
        if fill_color: style(ws, f'B{r}:F{r}', fill_=fill(fill_color))
        if top: style(ws, f'B{r}:F{r}', top=top)
        if bottom: style(ws, f'B{r}:F{r}', bottom=bottom)
        info['refs'][ref] = f'F{r}'
        r += 1
    parts = []
    if 'Scope of work' in group_ranges:
        a, b, rows = group_ranges['Scope of work']
        total_formula = sum_formula(rows)
    else:
        first = True
        for g, lab in (('Labor', 'Labor subtotal'), ('Materials', 'Materials subtotal'), ('Freight', 'Freight & distribution')):
            if g in group_ranges:
                a, b, rows = group_ranges[g]
                summary_row(lab, sum_formula(rows), g.lower(), top=side('RULE_DK') if first else None); first = False
                parts.append(info['refs'][g.lower()])
        if s['tax'] is not None:
            lab = 'Tax on materials' + (' (NH)' if 'NH' in s['tax']['note'] else '')
            summary_row(lab, f"={info['refs']['materials']}*E{r}", 'tax', rate=s['tax']['rate'])
            parts.append(info['refs']['tax'])
        elif 'Pennsylvania' in ' '.join(n['text'] for n in s['notes']):
            ws.row_dimensions[r].height = 20
            ws[f'C{r}'] = 'Pennsylvania sales & use tax'; ws[f'C{r}'].font = font(11, color='GRAY'); ws[f'C{r}'].alignment = align('left', indent=1)
            ws[f'F{r}'] = 'Included'; ws[f'F{r}'].font = font(11, italic=True, color='GRAY'); ws[f'F{r}'].alignment = align('right'); ws[f'F{r}'].number_format = FMT_TEXT_R
            r += 1
        total_formula = '=' + '+'.join(parts)
    summary_row('TOTAL', total_formula, 'total', height=30, lab_font=font(13, bold=True, color='WHITE'), val_font=font(14, bold=True, color='WHITE'), fill_color='NAVY')
    ws['F8'] = f"={info['refs']['total']}"
    summary_row('Deposit due on approval', f"={info['refs']['total']}*E{r}", 'deposit', rate=0.5, rate_fmt='0%_)', height=24,
                lab_font=font(12, bold=True, color='NAVY'), val_font=font(12, bold=True, color='NAVY'), fill_color='TINT2')
    summary_row('Balance due on completion', f"={info['refs']['total']}-{info['refs']['deposit']}", 'balance', height=20, bottom=side('RULE_DK'))
    # expected values (from the original's cached numbers) for verification
    exp = {}
    for g, (a, b, rows) in group_ranges.items():
        vals = {rr: v for rr, _, v in info['expected'].get('lines', [])}
        exp[g.lower()] = sum(vals[x] for x in rows)
    tot_orig = next(x['value'] for x in s['summary'] if x['label'].lower().startswith('total'))
    dep_orig = next(x['value'] for x in s['summary'] if x['label'].lower().startswith('deposit'))
    info['expected']['orig_summary'] = {x['label']: x['value'] for x in s['summary']}
    info['expected']['total'] = tot_orig; info['expected']['deposit'] = dep_orig

    # -- notes block
    r += 1
    notes = s['notes']
    if notes:
        header_txt = notes[0]['text'] if notes[0]['text'].upper().startswith('PROJECT NOTES') else 'PROJECT NOTES & TERMS'
        body = notes[1:] if notes[0]['text'].upper().startswith('PROJECT NOTES') else notes
        ws.row_breaks.append(Break(id=r - 1))   # notes start on a fresh printed page
        ws.row_dimensions[r].height = 26
        ws.merge_cells(f'B{r}:F{r}')
        ws[f'B{r}'] = header_txt.upper(); ws[f'B{r}'].font = font(11, bold=True, color='BRAND'); ws[f'B{r}'].alignment = align('left', 'bottom', indent=0)
        style(ws, f'B{r}:F{r}', bottom=side('BRAND', 'medium'))
        r += 1
        ws.row_dimensions[r].height = 6; r += 1
        first_heading = True
        for nt in body:
            txt = nt['text'].replace('​', '').strip()
            if txt.upper().startswith('DISCLAIMER'):
                ws.row_dimensions[r].height = 6; r += 1
                ws.merge_cells(f'C{r}:F{r}')
                ws[f'C{r}'] = txt; 
                style(ws, f'C{r}:F{r}', font_=font(10.5, bold=True, color='RED'), fill_=fill('AMBER'), align_=align('left', 'center', wrap=True, indent=1),
                      top=side('AMBER_DK'), bottom=side('AMBER_DK'), left=side('AMBER_DK'), right=side('AMBER_DK'))
                ws.row_dimensions[r].height = wrap_height(txt, width_px=NOTES_WIDTH_PX - 10, bold=True, pad=12)
                r += 1
            elif txt.startswith('•'):
                body_txt = txt.lstrip('•').strip()
                ws[f'B{r}'] = '•'; ws[f'B{r}'].font = font(11, color='BRAND'); ws[f'B{r}'].alignment = align('right', 'top')
                ws.merge_cells(f'C{r}:F{r}')
                ws[f'C{r}'] = body_txt
                style(ws, f'C{r}:F{r}', font_=font(10.5), align_=align('left', 'top', wrap=True, indent=1))
                ws.row_dimensions[r].height = wrap_height(body_txt)
                if nt.get('comment'):
                    ws[f'C{r}'].comment = Comment(nt['comment'], 'Matt Levy')
                r += 1
            elif txt.lower().startswith('source:'):
                ws.merge_cells(f'C{r}:F{r}')
                ws[f'C{r}'] = txt; style(ws, f'C{r}:F{r}', font_=font(9.5, italic=True, color='GRAY_LT'), align_=align('left', 'center', indent=1))
                ws.row_dimensions[r].height = 16; r += 1
            else:  # sub-heading
                if not first_heading:
                    ws.row_dimensions[r].height = 6; r += 1
                first_heading = False
                ws.merge_cells(f'C{r}:F{r}')
                ws[f'C{r}'] = txt; style(ws, f'C{r}:F{r}', font_=font(11, bold=True, color='NAVY'), align_=align('left', 'bottom', indent=1))
                ws.row_dimensions[r].height = 20; r += 1

    # -- floor plan(s)
    for im in s['images']:
        r += 1
        ws.row_breaks.append(Break(id=r - 1))   # floor plan on its own printed page
        ws.row_dimensions[r].height = 26
        ws.merge_cells(f'B{r}:F{r}')
        ws[f'B{r}'] = 'FLOOR PLAN / SCOPE AREAS'; ws[f'B{r}'].font = font(11, bold=True, color='BRAND'); ws[f'B{r}'].alignment = align('left', 'bottom')
        style(ws, f'B{r}:F{r}', bottom=side('BRAND', 'medium'))
        r += 1; ws.row_dimensions[r].height = 10; r += 1
        path = os.path.join(MEDIA, im['image'])
        pw, ph = PILImage.open(path).size
        max_w, max_h = 735, 850
        k = min(max_w / pw, max_h / ph, 1.0)
        img = XLImage(path); img.width = int(pw * k); img.height = int(ph * k)
        ws.add_image(img, f'C{r}')
        rows_needed = math.ceil(img.height / 20) + 1
        r += rows_needed

    last = r - 1 if not s['images'] else r

    # -- print setup: fixed scale chosen from the real block heights (Letter portrait, 0.6in top/bottom margins -> ~700pt usable)
    ws.print_area = f'B1:F{last}'
    ws.page_setup.orientation = 'portrait'
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    def _h(row): return ws.row_dimensions[row].height or 15
    breaks = sorted(b.id for b in ws.row_breaks.brk)
    blocks = []; start = 1
    for b in breaks + [last]:
        blocks.append(sum(_h(x) for x in range(start, b + 1))); start = b + 1
    USABLE = 700.0
    scale = 88
    for i, hgt in enumerate(blocks):
        need = int(USABLE * 100 / hgt)
        if i == 0 or need >= 80:          # pricing block always on one page; notes on one page only if it stays legible (>= 80%)
            scale = min(scale, need)
    ws.page_setup.scale = max(72, scale)
    ws.page_setup.fitToWidth = None; ws.page_setup.fitToHeight = None
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=False)
    info['print_scale'] = ws.page_setup.scale
    ws.print_options.horizontalCentered = True
    ws.page_margins = PageMargins(left=0.5, right=0.5, top=0.6, bottom=0.6, header=0.3, footer=0.3)
    ws.oddFooter.left.text = ISSUER; ws.oddFooter.left.size = 8; ws.oddFooter.left.font = FONT
    ws.oddFooter.center.text = 'Page &P of &N'; ws.oddFooter.center.size = 8; ws.oddFooter.center.font = FONT
    ws.oddFooter.right.text = title; ws.oddFooter.right.size = 8; ws.oddFooter.right.font = FONT
    return info

# ----------------------------------------------------------------------------- overview sheet
def build_overview(wb, infos):
    ws = wb.create_sheet('Overview', 0)
    ws.sheet_view.showGridLines = False
    ws.sheet_view.showRowColHeaders = False
    ws.sheet_view.zoomScale = 100
    ws.sheet_properties.tabColor = C['NAVY']
    # column groups B:C, D:E, F:H, I:L each sum to 47 units so the four KPI tiles are equal width
    widths = {'A': 2.5, 'B': 5, 'C': 42, 'D': 14, 'E': 33, 'F': 11, 'G': 18, 'H': 18, 'I': 10, 'J': 10, 'K': 13, 'L': 14, 'M': 2.5}
    set_widths(ws, widths)
    ws.row_dimensions[1].height = 6; style(ws, 'A1:M1', fill_=fill('BRAND'))
    ws.row_dimensions[2].height = 15
    ws.row_dimensions[3].height = 18
    ws.merge_cells('B3:F3'); ws['B3'] = f'{ISSUER.upper()}   |   PORTFOLIO OVERVIEW'; ws['B3'].font = font(9, bold=True, color='BRAND')
    ws.merge_cells('J3:L3'); ws['J3'] = f'AS OF {TODAY.strftime("%B %d, %Y").upper()}'; ws['J3'].font = font(8.5, bold=True, color='GRAY_LT'); ws['J3'].alignment = align('right')
    ws.row_dimensions[4].height = 40
    ws.merge_cells('B4:L4'); ws['B4'] = f'{CLIENT} — Retail Flooring Proposals'; ws['B4'].font = font(26, bold=True, color='NAVY'); ws['B4'].alignment = align('left', 'bottom')
    ws.row_dimensions[5].height = 22
    ws.merge_cells('B5:L5'); ws['B5'] = f'{len(infos)} customer-facing proposals across {CLIENT} locations  —  live totals linked to each proposal tab'
    ws['B5'].font = font(13, italic=True, color='GRAY'); ws['B5'].alignment = align('left', 'top')
    ws.row_dimensions[6].height = 6; style(ws, 'B6:L6', bottom=side('BRAND', 'medium'))
    ws.row_dimensions[7].height = 12

    # KPI tiles (rows 8-10)
    first_data = 14; last_data = first_data + len(infos) - 1
    K = f'$K${first_data}:$K${last_data}'; D = f'$D${first_data}:$D${last_data}'
    tiles = [
        ('B', 'C', 'TOTAL PROPOSAL VALUE', f'=SUM({K})', f'{len(infos)} proposals'),
        ('D', 'E', 'COMPLETED', f'=SUMIF({D},"Completed",{K})', f'=COUNTIF({D},"Completed")&" proposals"'),
        ('F', 'H', 'IN PROCESS', f'=SUMIF({D},"In process",{K})', f'=COUNTIF({D},"In process")&" proposals"'),
        ('I', 'L', 'OPEN PROPOSALS', f'=SUMIF({D},"Proposal",{K})+SUMIF({D},"Needs revisit",{K})', f'=(COUNTIF({D},"Proposal")+COUNTIF({D},"Needs revisit"))&" proposals (incl. needs-revisit)"'),
    ]
    ws.row_dimensions[8].height = 16; ws.row_dimensions[9].height = 30; ws.row_dimensions[10].height = 16
    for a, b, lab, f, sub in tiles:
        rng = f'{a}8:{b}10'
        style(ws, f'{a}10:{b}10', bottom=side('RULE'))
        style(ws, f'{a}8:{a}10', left=side('BRAND', 'medium'))
        ws.merge_cells(f'{a}8:{b}8'); ws.merge_cells(f'{a}9:{b}9'); ws.merge_cells(f'{a}10:{b}10')
        ws[f'{a}8'] = lab; ws[f'{a}8'].font = font(8.5, bold=True, color='GRAY_LT'); ws[f'{a}8'].alignment = align('left', 'bottom', indent=1)
        ws[f'{a}9'] = f; ws[f'{a}9'].number_format = FMT_MONEY0; ws[f'{a}9'].font = font(22, bold=True, color='NAVY'); ws[f'{a}9'].alignment = align('left', 'center', indent=1)
        ws[f'{a}10'] = sub; ws[f'{a}10'].font = font(9, italic=True, color='GRAY'); ws[f'{a}10'].alignment = align('left', 'top', indent=1)
    ws.row_dimensions[11].height = 14
    ws.row_dimensions[12].height = 6

    # table header
    hr = 13
    ws.row_dimensions[hr].height = 24
    heads = [('B', '#', 'center'), ('C', 'PROPOSAL', 'left'), ('D', 'STATUS', 'left'), ('E', 'SCOPE', 'left'), ('F', 'TAX RATE', 'right'),
             ('G', 'LABOR', 'right'), ('H', 'MATERIALS', 'right'), ('I', 'FREIGHT', 'right'), ('J', 'TAX', 'right'), ('K', 'TOTAL', 'right'), ('L', 'DEPOSIT (50%)', 'right')]
    for col, lab, h in heads:
        c = ws[f'{col}{hr}']; c.value = lab; c.font = font(10, bold=True, color='WHITE'); c.fill = fill('BRAND'); c.alignment = align(h, indent=1 if h == 'left' else 0)
        if h == 'right': c.number_format = FMT_TEXT_R
    r = first_data
    for i, info in enumerate(infos, 1):
        ws.row_dimensions[r].height = 21
        q = "'" + info['sheet'].replace("'", "''") + "'!"
        ws[f'B{r}'] = i; ws[f'B{r}'].font = font(9.5, color='GRAY_LT'); ws[f'B{r}'].alignment = align('center')
        c = ws[f'C{r}']; c.value = OVERVIEW_LABEL.get(info['sheet'], info['title']); c.hyperlink = Hyperlink(ref=f'C{r}', location=f"{q}A1", display=c.value); c.font = font(11.5, bold=True, color='BRAND'); c.alignment = align('left', indent=1)
        c = ws[f'D{r}']; c.value = info['status']; c.font = font(10.5, color='INK'); c.alignment = align('left', indent=1)
        c = ws[f'E{r}']; c.value = info['subtitle'].split('  —  ')[0]; c.font = font(10.5, color='GRAY'); c.alignment = align('left', indent=1)
        c = ws[f'F{r}']; c.value = info['tax_text'].split(' ')[0] if info['tax_text'] != 'Not applicable' else '–'; c.font = font(10.5, color='GRAY'); c.alignment = align('right'); c.number_format = FMT_TEXT_R
        for col, key in (('G', 'labor'), ('H', 'materials'), ('I', 'freight'), ('J', 'tax'), ('K', 'total'), ('L', 'deposit')):
            ref = info['refs'].get(key)
            c = ws[f'{col}{r}']
            c.value = f'={q}{ref}' if ref else None
            c.number_format = FMT_MONEY; c.font = font(11.5, bold=(key == 'total')); c.alignment = align('right')
            if ref is None:
                c.value = '–'; c.font = font(11.5, color='GRAY_LT'); c.number_format = FMT_TEXT_R
        style(ws, f'B{r}:L{r}', bottom=side('RULE', 'hair'))
        r += 1
    # totals row
    ws.row_dimensions[r].height = 26
    ws[f'C{r}'] = 'TOTAL'; ws[f'C{r}'].font = font(12, bold=True, color='WHITE'); ws[f'C{r}'].alignment = align('left', indent=1)
    style(ws, f'B{r}:L{r}', fill_=fill('NAVY'))
    for col in 'GHIJKL':
        c = ws[f'{col}{r}']; c.value = f'=SUM({col}{first_data}:{col}{last_data})'; c.number_format = FMT_MONEY; c.font = font(12, bold=True, color='WHITE'); c.alignment = align('right')
    total_row = r
    r += 2
    ws.merge_cells(f'B{r}:L{r}')
    ws[f'B{r}'] = ('Status legend: Completed = installed and closed out  ·  In process = approved and scheduled  ·  Proposal = issued, awaiting approval  ·  '
                   'Needs revisit = draft pricing to be reconfirmed before issue.  Tax is charged on materials only at the state rate shown; freight and labor are untaxed. '
                   'Selinsgrove (PA) pricing is inclusive of Pennsylvania sales & use tax. Deposits are 50% of the proposal total, due on approval.')
    style(ws, f'B{r}:L{r}', font_=font(9.5, italic=True, color='GRAY'), align_=align('left', 'top', wrap=True))
    ws.row_dimensions[r].height = 44
    r += 2
    ws.merge_cells(f'B{r}:L{r}')
    ws[f'B{r}'] = f'{ISSUER}   ·   Prepared for {CLIENT}   ·   Proposal names link to their detailed tabs'
    style(ws, f'B{r}:L{r}', font_=font(9, italic=True, color='GRAY_LT'), align_=align('left'), top=side('RULE'))
    ws.row_dimensions[r].height = 18
    ws.print_area = f'B1:L{r}'
    ws.page_setup.orientation = 'landscape'; ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_options.horizontalCentered = True
    ws.page_margins = PageMargins(left=0.5, right=0.5, top=0.6, bottom=0.6, header=0.3, footer=0.3)
    ws.oddFooter.left.text = ISSUER; ws.oddFooter.center.text = 'Page &P of &N'; ws.oddFooter.right.text = f'{CLIENT} — Retail Flooring Proposals'
    for part in (ws.oddFooter.left, ws.oddFooter.center, ws.oddFooter.right): part.size = 8; part.font = FONT
    ws.freeze_panes = None
    return ws, first_data, last_data, total_row

# ----------------------------------------------------------------------------- hidden log
def build_log(wb, rows, note):
    ws = wb.create_sheet('Claude Log')
    ws.sheet_state = 'veryHidden'
    widths = {'A': 8, 'B': 12, 'C': 48, 'D': 48, 'E': 60, 'F': 48}
    set_widths(ws, widths)
    for i, row in enumerate(rows, 1):
        for j, v in enumerate(row, 1):
            c = ws.cell(i, j)
            if isinstance(v, str) and re.match(r'^\d{4}-\d{2}-\d{2}T', v):
                v = datetime.datetime.fromisoformat(v)
            c.value = v
            c.font = font(10, bold=(i == 1), color='WHITE' if i == 1 else 'INK')
            c.alignment = align('left', 'top', wrap=True)
            if i == 1: c.fill = fill('BRAND')
            if j == 2 and i > 1: c.number_format = 'mm-dd-yy'
    nr = len(rows) + 1
    turn = max(int(r[0]) for r in rows[1:] if isinstance(r[0], (int, float))) + 1
    for j, v in enumerate([turn, datetime.datetime(TODAY.year, TODAY.month, TODAY.day)] + note, 1):
        c = ws.cell(nr, j); c.value = v; c.font = font(10); c.alignment = align('left', 'top', wrap=True)
        if j == 2: c.number_format = 'mm-dd-yy'
    ws.freeze_panes = 'A2'
    return ws

# ----------------------------------------------------------------------------- main
def main():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    infos = []
    for i, s in enumerate(MODEL['sheets']):
        infos.append(build_proposal(wb, s, i))
    build_overview(wb, infos)
    note = [
        'User asked to re-engineer the whole workbook so it is far more presentable: modern, better than McKinsey / Goldman Sachs formatting, Garamond or Times New Roman font.',
        'Rebuilt every proposal tab on one design system (Garamond, brand navy #156082 / sky #44B3E1, hairline rules, grouped LABOR / MATERIALS / FREIGHT sections, summary block with TOTAL, 50% deposit and balance, restyled notes, floor plans retained) and added an Overview tab with live cross-sheet totals, KPI tiles and hyperlinks.',
        'All quantities, unit prices and line totals carried over unchanged; every total is a live formula (line = qty x price, subtotals = SUM of section, tax = materials x rate cell, deposit = total x 50%). Tab names normalised (e.g. "Completed - GD Braintree"); Claude Log kept veryHidden. Original numeric anomalies preserved and flagged to the user: Sunrise labor subtotal omits the Self-Level/Prep line; Natick $225 and New Haven $1,505 lump-sum lines shown as "lump sum" with their original quantities; Trenton vs Tremont St on the two Great Hill tabs.',
        'Every line total, subtotal, tax, total and deposit verified equal to the original workbook to the cent on all 20 tabs; recalculation returned zero formula errors.',
    ]
    build_log(wb, MODEL['log'], note)
    wb.active = 0
    for ws in wb.worksheets:
        ws.sheet_view.tabSelected = (ws.title == 'Overview')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    wb.save(OUT)
    json.dump(infos, open(os.path.join(HERE, 'out', 'infos.json'), 'w'), indent=1, default=str)
    print('saved', OUT, 'sheets:', len(wb.sheetnames))

if __name__ == '__main__':
    main()
