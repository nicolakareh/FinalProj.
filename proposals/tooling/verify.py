"""Compare the recalculated new workbook against the original's cached values."""
import json, sys, openpyxl, warnings
warnings.filterwarnings('ignore')
NEW = sys.argv[1] if len(sys.argv) > 1 else 'out/recalc_test.xlsx'
model = json.load(open('model.json'))
infos = json.load(open('out/infos.json'))
wb = openpyxl.load_workbook(NEW, data_only=True)
by_orig = {s['orig_name']: s for s in model['sheets']}
ok = True
def close(a, b, tol=0.005):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol
rows = []
for s, info in zip(model['sheets'], infos):
    ws = wb[info['sheet']]
    problems = []
    # line totals: every original item value must appear in column F of the new sheet (same multiset)
    new_lines = [ws[f'F{r}'].value for r, _, _ in info['expected']['lines']]
    orig_lines = [v for _, _, v in info['expected']['lines']]
    for (r, exp, orig), got in zip(info['expected']['lines'], new_lines):
        if not close(got, orig):
            problems.append(f'line F{r}: new={got} orig={orig}')
    # summary
    orig_sum = info['expected']['orig_summary']
    keymap = {'labor': 'labor subtotal', 'materials': 'materials subtotal', 'freight': 'freight', 'tax': 'tax', 'total': 'total', 'deposit': 'deposit'}
    got = {}
    for key, ref in info['refs'].items():
        got[key] = ws[ref].value
    for key, prefix in keymap.items():
        o = next((v for k, v in orig_sum.items() if k.lower().startswith(prefix)), None)
        if key in got:
            if o is None and key in ('freight',) and close(got[key], 0): continue
            if not close(got[key], o):
                problems.append(f'{key}: new={got[key]} orig={o}')
        elif o not in (None, 0):
            problems.append(f'{key}: missing in new, orig={o}')
    if 'balance' in got and not close(got['balance'], got['total'] - got['deposit']):
        problems.append('balance mismatch')
    rows.append((info['sheet'], len(orig_lines), got.get('total'), problems))
    if problems: ok = False
print(f"{'sheet':34} {'items':>5} {'new total':>14}  status")
for name, n, tot, probs in rows:
    print(f"{name:34} {n:5} {tot:14,.2f}  {'OK' if not probs else 'MISMATCH: ' + '; '.join(probs)}")
# overview
ov = wb['Overview']
print('\nOverview KPI:', [ov[f'{c}9'].value for c in 'CEGI'])
tot_row = next(r for r in range(14, 60) if ov[f'C{r}'].value == 'TOTAL')
ov_total = ov[f'K{tot_row}'].value
sum_sheets = sum(t for _, _, t, _ in rows)
print(f'Overview grand total {ov_total:,.2f} vs sum of sheet totals {sum_sheets:,.2f} ->', 'OK' if close(ov_total, sum_sheets) else 'MISMATCH')
for r in range(14, tot_row):
    vals = [ov[f'{c}{r}'].value for c in 'GHIJKL']
    if any(v is None for v in vals[4:]):
        print('Overview row', r, ov[f'C{r}'].value, 'has blank total/deposit', vals); ok = False
print('\nALL OK' if ok else '\nPROBLEMS FOUND')
