import openpyxl, json, re, zipfile
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.utils.cell import range_boundaries

SRC='original.xlsx'
wbf = openpyxl.load_workbook(SRC)               # formulas
wbv = openpyxl.load_workbook(SRC, data_only=True)  # cached values

# --- image mapping: sheet name -> list of {image, anchor_row, anchor_col}
import xml.etree.ElementTree as ET
z = zipfile.ZipFile(SRC)
ns = {'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'm':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'p':'http://schemas.openxmlformats.org/package/2006/relationships',
      'xdr':'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'}
wbxml = ET.fromstring(z.read('xl/workbook.xml'))
wbrels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
rid2target = {rel.get('Id'): rel.get('Target') for rel in wbrels}
sheet_images = {}
for sh in wbxml.find('m:sheets', ns):
    name = sh.get('name'); rid = sh.get('{%s}id' % ns['r'])
    target = rid2target[rid]  # worksheets/sheetN.xml
    fname = target.split('/')[-1]
    relp = f'xl/worksheets/_rels/{fname}.rels'
    if relp not in z.namelist(): continue
    srels = ET.fromstring(z.read(relp))
    for rel in srels:
        if rel.get('Type').endswith('/drawing'):
            dpath = 'xl/drawings/' + rel.get('Target').split('/')[-1]
            drels = ET.fromstring(z.read(dpath.replace('drawings/','drawings/_rels/') + '.rels'))
            img = {r.get('Id'): 'xl/media/' + r.get('Target').split('/')[-1] for r in drels}
            d = ET.fromstring(z.read(dpath))
            for anc in d.findall('xdr:twoCellAnchor', ns):
                frm = anc.find('xdr:from', ns)
                blip = anc.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
                ext = anc.find('xdr:pic/xdr:spPr/{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm/{http://schemas.openxmlformats.org/drawingml/2006/main}ext', ns)
                sheet_images.setdefault(name, []).append({
                    'image': img[blip.get('{%s}embed' % ns['r'])],
                    'from_row': int(frm.find('xdr:row', ns).text)+1,
                    'from_col': int(frm.find('xdr:col', ns).text)+1,
                    'cx_emu': int(ext.get('cx')), 'cy_emu': int(ext.get('cy')),
                })
print('images:', json.dumps(sheet_images, indent=1))

def refs_in_formula(f):
    """return set of row numbers referenced in column D for a formula like =SUM(D5:D9,D12) or =D23 or =D19+D20"""
    rows=set()
    for a,b in re.findall(r'\$?D\$?(\d+):\$?D\$?(\d+)', f):
        rows.update(range(int(a), int(b)+1))
    f2 = re.sub(r'\$?D\$?\d+:\$?D\$?\d+','',f)
    for a in re.findall(r'\$?D\$?(\d+)', f2):
        rows.add(int(a))
    return rows

model = {'sheets': [], 'log': []}
for ws in wbf.worksheets:
    wv = wbv[ws.title]
    if ws.title == 'Claude Log':
        rows=[]
        for r in ws.iter_rows(min_row=1, values_only=True):
            rows.append([ (v.isoformat() if hasattr(v,'isoformat') else v) for v in r])
        model['log'] = rows
        continue
    s = {'orig_name': ws.title, 'state': ws.sheet_state, 'title': ws['A1'].value}
    # header row
    hdr = None
    for r in range(1, 8):
        if ws.cell(r,1).value == 'Description': hdr = r; break
    assert hdr, ws.title
    sub = [ws.cell(r,1).value for r in range(2, hdr) if ws.cell(r,1).value]
    s['subtitle'] = sub[0] if sub else None
    # line items + summary
    items=[]; summary=[]; r = hdr+1
    while True:
        a = ws.cell(r,1).value
        if a is None: break
        b = ws.cell(r,2).value; c = ws.cell(r,3).value; d = ws.cell(r,4).value
        if b is not None:
            items.append({'row': r, 'desc': str(a).strip(), 'qty': b, 'unit_price': c, 'line_total': d,
                          'qty_v': wv.cell(r,2).value, 'unit_price_v': wv.cell(r,3).value, 'line_total_v': wv.cell(r,4).value,
                          'comment': ws.cell(r,1).comment.text if ws.cell(r,1).comment else None,
                          'qty_fmt': ws.cell(r,2).number_format})
        else:
            summary.append({'row': r, 'label': str(a).strip(), 'formula': d, 'value': wv.cell(r,4).value})
        r += 1
    s['items']=items; s['summary']=summary
    # groups from subtotal formulas
    groups={}
    for sm in summary:
        lab = sm['label'].lower()
        if isinstance(sm['formula'], str) and sm['formula'].startswith('='):
            rr = refs_in_formula(sm['formula'])
        else:
            rr = set()
        if lab.startswith('labor'): groups['Labor'] = rr
        elif lab.startswith('materials'): groups['Materials'] = rr
        elif lab.startswith('freight'): groups['Freight'] = rr
        elif lab.startswith('total') and 'Labor' not in groups and len(summary)<=2: groups['Scope of work'] = rr
    item_rows = {it['row'] for it in items}
    assigned=set()
    for g, rr in groups.items():
        rr &= item_rows; groups[g] = sorted(rr); assigned |= rr
    s['groups'] = groups
    s['unassigned_items'] = sorted(item_rows - assigned)
    # tax
    tax = next((sm for sm in summary if sm['label'].lower().startswith('tax')), None)
    if tax:
        m = re.search(r'\(([^)]*)\)', tax['label'])
        m2 = re.search(r'([\d.]+)\s*%', tax['label'])
        s['tax'] = {'label': tax['label'], 'rate': float(m2.group(1))/100 if m2 else 0.0, 'formula': tax['formula'], 'value': tax['value'], 'note': m.group(1) if m else ''}
    else:
        s['tax'] = None
    # notes: everything after summary
    notes=[]
    r2 = r+1
    while r2 <= ws.max_row:
        v = ws.cell(r2,1).value
        if v is not None:
            cell = ws.cell(r2,1)
            fc = cell.font.color.rgb if (cell.font.color is not None and cell.font.color.type=='rgb') else None
            fill = cell.fill.fgColor.rgb if cell.fill and cell.fill.fill_type else None
            notes.append({'row': r2, 'text': str(v), 'bold': bool(cell.font.b), 'italic': bool(cell.font.i), 'size': cell.font.sz, 'color': fc, 'fill': fill,
                          'height': ws.row_dimensions[r2].height, 'comment': cell.comment.text if cell.comment else None})
        r2 += 1
    s['notes'] = notes
    s['images'] = sheet_images.get(ws.title, [])
    s['col_widths'] = {k: v.width for k,v in ws.column_dimensions.items() if v.width}
    # any other comments on the sheet
    s['comments'] = [{'cell': c.coordinate, 'text': c.comment.text, 'author': c.comment.author} for row in ws.iter_rows() for c in row if c.comment]
    model['sheets'].append(s)

json.dump(model, open('model.json','w'), indent=1, default=str)
# summary print
for s in model['sheets']:
    tot = next((x['value'] for x in s['summary'] if x['label'].lower().startswith('total')), None)
    print(f"{s['orig_name']!r:36} items={len(s['items']):2} groups={ {k:len(v) for k,v in s['groups'].items()} } unassigned={s['unassigned_items']} tax={s['tax']['rate'] if s['tax'] else None} total={tot} notes={len(s['notes'])} imgs={len(s['images'])} comments={s['comments']}")
