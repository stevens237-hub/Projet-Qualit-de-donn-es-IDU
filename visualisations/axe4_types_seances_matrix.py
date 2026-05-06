"""
Axe 4 — Heatmap modules × types de séances.

Vert   — volume > 0h dans la maquette (attendu, contexte)
Gris   — volume 0h, absent partout (correct)
Orange — volume 0h, présent dans le graphe de dépendances (anomalie)
Rouge  — volume 0h, présent dans l'ADE (anomalie)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parents[1]))
from audit.core.config import DATA_DIR
from audit.core.loader import load_all_data

data      = load_all_data(DATA_DIR)
maquette  = data['maquette']
ade       = data['ade'].copy()
dep_graph = data['dep_graph']

# ── Extraction du type de séance ─────────────────────────────────────────
_TYPE_PARTS = {
    'CM': 'CM', 'TD': 'TD', 'TDG': 'TD', 'TDTP': 'TD',
    'TP': 'TP', 'TPG1': 'TP', 'TPG2': 'TP', 'TPPG': 'TP',
    'PROJ': 'PROJ', 'PROJET': 'PROJ',
    'EXAM': 'Exam', 'ET': 'Exam', 'EX': 'Exam', 'CMEX': 'Exam',
    'CT': 'Exam', 'CC': 'Exam', 'DS': 'Exam',
}

def _get_stype(row):
    if pd.notna(row.get('session_type_title')):
        t = _TYPE_PARTS.get(str(row['session_type_title']).upper())
        if t: return t
    if pd.notna(row.get('session_type_desc')):
        t = _TYPE_PARTS.get(str(row['session_type_desc']).upper())
        if t: return t
    for part in str(row.get('Title', '')).upper().split('_')[1:]:
        t = _TYPE_PARTS.get(part)
        if t: return t
    return None

ade['stype'] = ade.apply(_get_stype, axis=1)

ade_types = (
    ade.dropna(subset=['stype'])
    .groupby('canonical_code')['stype']
    .apply(set).to_dict()
)

dg_types: dict[str, set] = {}
for _, row in dep_graph.iterrows():
    for mod, typ in [
        (row['module_precedent'], row['type_precedent']),
        (row['module_suivant'],   row['type_suivant']),
    ]:
        dg_types.setdefault(mod, set()).add(typ)

# ── Construction de la matrice ────────────────────────────────────────────
TYPES        = ['CM', 'TD', 'TP']
MAQUETTE_COL = {'CM': 'cm', 'TD': 'td', 'TP': 'tp'}

STATUS_OK_ABSENT  = 0
STATUS_ANOM_DG    = 1
STATUS_ANOM_ADE   = 2
STATUS_OK_PRESENT = 3

COLORS = {
    STATUS_OK_ABSENT:  '#BDC3C7',
    STATUS_ANOM_DG:    '#E67E22',
    STATUS_ANOM_ADE:   '#E74C3C',
    STATUS_OK_PRESENT: '#2ECC71',
}
LABEL = {
    STATUS_OK_ABSENT:  'Volume 0h — Absent partout (correct)',
    STATUS_ANOM_DG:    'Volume 0h — Présent dans le graphe',
    STATUS_ANOM_ADE:   'Volume 0h — Présent dans ADE',
    STATUS_OK_PRESENT: 'Volume > 0h (attendu)',
}

matrix: dict[str, dict] = {}

for _, row in maquette.iterrows():
    module = row['code_module']
    statuses: dict[str, int] = {}
    has_anomaly = False

    for stype in TYPES:
        col = MAQUETTE_COL[stype]
        try:
            vol = float(row[col])
        except (ValueError, TypeError):
            vol = None

        if vol is None or vol > 0:
            statuses[stype] = STATUS_OK_PRESENT
        else:
            in_ade = stype in ade_types.get(module, set())
            in_dg  = stype in dg_types.get(module, set())
            if in_ade:
                statuses[stype] = STATUS_ANOM_ADE
                has_anomaly = True
            elif in_dg:
                statuses[stype] = STATUS_ANOM_DG
                has_anomaly = True
            else:
                statuses[stype] = STATUS_OK_ABSENT

    if has_anomaly:
        matrix[module] = statuses

def _n_anomalies(m):
    return sum(1 for s in matrix[m].values() if s in (STATUS_ANOM_ADE, STATUS_ANOM_DG))

modules       = sorted(matrix.keys(), key=_n_anomalies, reverse=True)
modules_label = [m.replace('_IDU', '') for m in modules]
n_mod, n_type = len(modules), len(TYPES)

# ── Tableaux numpy ────────────────────────────────────────────────────────
z           = np.zeros((n_mod, n_type))
hover_text  = [['' ] * n_type for _ in range(n_mod)]

for mi, mod in enumerate(modules):
    for ti, stype in enumerate(TYPES):
        status = matrix[mod][stype]
        z[mi, ti] = status

        if status == STATUS_ANOM_ADE:
            count  = ade[(ade['canonical_code'] == mod) & (ade['stype'] == stype)].shape[0]
            detail = f'{count} séance(s) planifiée(s) dans ADE'
        elif status == STATUS_ANOM_DG:
            detail = 'Référencé dans le graphe de dépendances'
        elif status == STATUS_OK_PRESENT:
            try:
                vol = float(maquette[maquette['code_module'] == mod].iloc[0][MAQUETTE_COL[stype]])
                detail = f'{int(vol)}h déclarées dans la maquette'
            except Exception:
                detail = 'Volume > 0h'
        else:
            detail = 'Aucune séance de ce type (cohérent)'

        hover_text[mi][ti] = (
            f'<b>{mod.replace("_IDU", "")}</b> — {stype}<br>'
            f'{LABEL[status]}<br><i>{detail}</i>'
        )

# ── Colorscale discrète 4 niveaux ─────────────────────────────────────────
colorscale = [
    [0.00, '#BDC3C7'], [0.24, '#BDC3C7'],
    [0.25, '#E67E22'], [0.49, '#E67E22'],
    [0.50, '#E74C3C'], [0.74, '#E74C3C'],
    [0.75, '#2ECC71'], [1.00, '#2ECC71'],
]

# ── Figure ────────────────────────────────────────────────────────────────
# Taille de cellule fixe → figure carrée par cellule
CELL_PX = 110
fig = go.Figure()

fig.add_trace(go.Heatmap(
    z=z,
    x=TYPES,
    y=modules_label,
    colorscale=colorscale,
    zmin=0, zmax=3,
    showscale=False,
    hovertemplate='%{customdata}<extra></extra>',
    customdata=hover_text,
    xgap=5,
    ygap=5,
))

# Légende manuelle
LEGEND_ITEMS = [
    (STATUS_OK_PRESENT, 'Volume > 0h (attendu)'),
    (STATUS_OK_ABSENT,  'Volume 0h Absent partout (correct)'),
    (STATUS_ANOM_DG,    'Volume 0h Présent dans le graphe '),
    (STATUS_ANOM_ADE,   'Volume 0h Présent dans ADE '),
]
for status, label in LEGEND_ITEMS:
    fig.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(size=13, color=COLORS[status], symbol='square'),
        name=label,
        showlegend=True,
    ))

# Dimensions : cellules carrées
plot_w = n_type * CELL_PX
plot_h = n_mod  * CELL_PX
margin = dict(l=130, r=20, t=120, b=20)
total_w = plot_w + margin['l'] + margin['r'] + 230   # 230 pour la légende
total_h = plot_h + margin['t'] + margin['b']

fig.update_layout(
    title=dict(
        text=(
            '<b>Axe 4 — Cohérence des types de séances : maquette vs ADE vs graphe</b><br>'
            '<sup>5 modules concernés · 6 anomalies détectées</sup>'
        ),
        font=dict(size=14), x=0.38,
    ),
    xaxis=dict(
        side='top',
        tickfont=dict(size=14, color='#2C3E50', family='Arial Black'),
        showgrid=False, zeroline=False,
        constrain='domain',
    ),
    yaxis=dict(
        tickfont=dict(size=12, color='#2C3E50'),
        showgrid=False, zeroline=False,
        autorange='reversed',
        scaleanchor='x',
        scaleratio=1,
        constrain='domain',
    ),
    plot_bgcolor='#F8F9FA',
    paper_bgcolor='white',
    width=total_w,
    height=total_h,
    margin=margin,
    legend=dict(
        x=1.02, y=0.5,
        xanchor='left', yanchor='middle',
        bgcolor='white',
        bordercolor='#BDC3C7',
        borderwidth=1,
        font=dict(size=11),
        traceorder='normal',
    ),
)

out = Path(__file__).parent / 'axe4_types_seances_matrix.html'
fig.write_html(str(out))
print(f'Heatmap sauvegardée : {out}')
