"""
Axe 6 — Visualisation interactive : séquence pédagogique attendue vs chronologie ADE.

Pour chaque module, affiche deux colonnes côte à côte :
  - Colonne gauche  : ordre attendu par le graphe de dépendances (CM1, TD1, CM2, TD2...)
  - Colonne droite  : ordre chronologique réel dans ADE (trié par date)

Les lignes reliant les mêmes séances entre les deux colonnes montrent les inversions :
  - Ligne verte  → la séance est au bon endroit dans ADE
  - Ligne rouge  → inversion : la séance est planifiée trop tôt ou trop tard par rapport au graphe
"""

import sys
from collections import defaultdict, deque
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parents[1]))
from audit.core.config import DATA_DIR
from audit.core.loader import load_all_data

# ── Chargement des données ────────────────────────────────────────────────
data = load_all_data(DATA_DIR)
ade  = data['ade'].copy()
dg   = data['dep_graph']

# ── Extraction du type de séance ─────────────────────────────────────────
_TYPE_PARTS = {
    'CM':'CM', 'TD':'TD', 'TDG':'TD', 'TDTP':'TD',
    'TP':'TP', 'TPG1':'TP', 'TPG2':'TP', 'TPPG':'TP',
    'PROJ':'PROJ', 'PROJET':'PROJ',
    'EXAM':'Exam', 'ET':'Exam', 'EX':'Exam', 'CMEX':'Exam',
    'CT':'Exam', 'CC':'Exam', 'DS':'Exam',
}

def get_type(row):
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

ade['stype'] = ade.apply(get_type, axis=1)

# ── Slots de séances par (module, type) via semaine ISO ──────────────────
def build_slots(ade_mod):
    df = ade_mod.copy()
    iso = df['Starts'].dt.isocalendar()
    df['_y'] = iso['year']; df['_w'] = iso['week']
    slots = {}
    for stype, grp in df.dropna(subset=['stype']).groupby('stype'):
        s = grp.groupby(['_y', '_w'])['Starts'].min().sort_values()
        slots[str(stype)] = s.tolist()
    return slots

# ── Tri topologique (algorithme de Kahn) ─────────────────────────────────
def topological_sort(edges):
    """Retourne une liste ordonnée de nœuds (type, num) respectant les arcs."""
    in_degree = defaultdict(int)
    adj = defaultdict(list)
    all_nodes = set()
    for u, v in edges:
        adj[u].append(v)
        in_degree[v] += 1
        all_nodes.update([u, v])
    # Initialiser les nœuds sans prédécesseur
    queue = deque(
        sorted(n for n in all_nodes if in_degree[n] == 0)
    )
    result = []
    while queue:
        node = queue.popleft()
        result.append(node)
        for neighbor in sorted(adj[node]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    # Ajouter les nœuds non atteints (cycles éventuels)
    for n in sorted(all_nodes):
        if n not in result:
            result.append(n)
    return result

# ── Construction des données par module ──────────────────────────────────
TYPE_COLORS = {
    'CM': '#3498DB', 'TD': '#E67E22',
    'TP': '#2ECC71', 'PROJ': '#9B59B6', 'Exam': '#E74C3C',
}

def build_module_data(mod):
    """
    Retourne :
      expected_order : liste de (type, num) dans l'ordre du graphe
      ade_order      : liste de (type, num) dans l'ordre chronologique ADE
      slot_dates     : dict (type, num) -> date ADE
      inverted_pairs : set de paires (prec, suiv) qui sont des inversions
    """
    dg_mod = dg[dg['module_precedent'] == mod]
    slots  = build_slots(ade[ade['canonical_code'] == mod])

    edges = []
    verifiable = {}  # (type, num) -> date ADE
    inverted_pairs = set()

    for _, row in dg_mod.iterrows():
        tp = row['type_precedent']; np_ = int(row['numero_precedent'])
        ts = row['type_suivant'];   ns  = int(row['numero_suivant'])
        dp_list = slots.get(tp, [])
        ds_list = slots.get(ts, [])
        if len(dp_list) < np_ or len(ds_list) < ns:
            continue
        prec = (tp, np_); suiv = (ts, ns)
        edges.append((prec, suiv))
        verifiable[prec] = dp_list[np_ - 1]
        verifiable[suiv] = ds_list[ns - 1]
        if dp_list[np_ - 1] >= ds_list[ns - 1]:
            inverted_pairs.add((prec, suiv))

    if not verifiable:
        return None, None, None, None

    expected_order = [n for n in topological_sort(edges) if n in verifiable]
    ade_order = sorted(verifiable.keys(), key=lambda k: verifiable[k])

    return expected_order, ade_order, verifiable, inverted_pairs


# ── Construction de la figure Plotly ─────────────────────────────────────
def make_traces_for_module(mod):
    """Retourne la liste de traces Plotly pour un module."""
    expected_order, ade_order, slot_dates, inverted_pairs = build_module_data(mod)
    if expected_order is None:
        return []

    n = len(expected_order)
    # Position Y : 0 en haut → n-1 en bas
    exp_pos  = {node: i for i, node in enumerate(expected_order)}
    ade_pos  = {node: i for i, node in enumerate(ade_order)}

    # Nœuds inverted (impliqués dans au moins une inversion)
    inv_nodes = set()
    for prec, suiv in inverted_pairs:
        inv_nodes.add(prec); inv_nodes.add(suiv)

    traces = []
    X_LEFT, X_RIGHT = 0.1, 0.9

    # ── Lignes de connexion ──────────────────────────────────────────────
    for node in expected_order:
        y_left  = exp_pos[node]
        y_right = ade_pos[node]
        is_inv  = node in inv_nodes
        color   = 'rgba(231,76,60,0.7)' if is_inv else 'rgba(46,204,113,0.5)'
        width   = 2.5 if is_inv else 1.5
        dash    = 'solid' if is_inv else 'dot'
        typ, num = node
        date_str = slot_dates[node].strftime('%d/%m/%Y')
        hover = (
            f'<b>{typ} n°{num}</b><br>'
            f'ADE : {date_str}<br>'
            f'{"❌ Impliqué dans une inversion" if is_inv else "✅ Ordre respecté"}'
        )
        traces.append(go.Scatter(
            x=[X_LEFT, X_RIGHT], y=[-y_left, -y_right],
            mode='lines',
            line=dict(color=color, width=width, dash=dash),
            hoverinfo='text',
            text=hover,
            showlegend=False,
        ))

    # ── Nœuds colonne gauche (ordre graphe) ──────────────────────────────
    for node in expected_order:
        typ, num = node
        y = -exp_pos[node]
        is_inv = node in inv_nodes
        border = '#E74C3C' if is_inv else '#2C3E50'
        date_str = slot_dates[node].strftime('%d/%m/%Y')
        traces.append(go.Scatter(
            x=[X_LEFT], y=[y],
            mode='markers+text',
            marker=dict(
                size=22,
                color=TYPE_COLORS.get(typ, '#95A5A6'),
                line=dict(color=border, width=3 if is_inv else 1),
                symbol='circle',
            ),
            text=[f'{typ}{num}'],
            textposition='middle center',
            textfont=dict(size=10, color='white', family='Arial Black'),
            hovertemplate=f'<b>{typ} n°{num}</b><br>Rang graphe : {exp_pos[node]+1}<br>ADE : {date_str}<extra></extra>',
            showlegend=False,
        ))

    # ── Nœuds colonne droite (ordre ADE) ────────────────────────────────
    for node in ade_order:
        typ, num = node
        y = -ade_pos[node]
        is_inv = node in inv_nodes
        border = '#E74C3C' if is_inv else '#2C3E50'
        date_str = slot_dates[node].strftime('%d/%m/%Y')
        traces.append(go.Scatter(
            x=[X_RIGHT], y=[y],
            mode='markers+text',
            marker=dict(
                size=22,
                color=TYPE_COLORS.get(typ, '#95A5A6'),
                line=dict(color=border, width=3 if is_inv else 1),
                symbol='circle',
            ),
            text=[f'{typ}{num}'],
            textposition='middle center',
            textfont=dict(size=10, color='white', family='Arial Black'),
            hovertemplate=f'<b>{typ} n°{num}</b><br>ADE : {date_str}<br>Rang ADE : {ade_pos[node]+1}<extra></extra>',
            showlegend=False,
        ))

    # ── Annotations de date sur la droite ────────────────────────────────
    for node in ade_order:
        typ, num = node
        y = -ade_pos[node]
        date_str = slot_dates[node].strftime('%d/%m/%y')
        is_inv = node in inv_nodes
        traces.append(go.Scatter(
            x=[X_RIGHT + 0.08], y=[y],
            mode='text',
            text=[f'<span style="color:{"#E74C3C" if is_inv else "#7F8C8D"}">{date_str}</span>'],
            textposition='middle right',
            textfont=dict(size=9),
            hoverinfo='skip',
            showlegend=False,
        ))

    return traces


# ── Collecte des modules avec inversions ─────────────────────────────────
modules_with_inv = {}
for mod in dg['module_precedent'].unique():
    if ade[ade['canonical_code'] == mod].empty:
        continue
    _, _, _, inverted_pairs = build_module_data(mod)
    if inverted_pairs:
        modules_with_inv[mod] = len(inverted_pairs)

sorted_mods = sorted(modules_with_inv.items(), key=lambda x: -x[1])
mods_list   = [m for m, _ in sorted_mods]

# ── Figure principale ─────────────────────────────────────────────────────
fig = go.Figure()

all_traces_by_mod = {}
visibility_map = []

for idx, mod in enumerate(mods_list):
    traces = make_traces_for_module(mod)
    all_traces_by_mod[mod] = (len(fig.data), len(traces))
    for t in traces:
        t.visible = (idx == 0)
        fig.add_trace(t)
        visibility_map.append(idx)

n_total = len(fig.data)

# ── Boutons dropdown ──────────────────────────────────────────────────────
buttons = []
for idx, mod in enumerate(mods_list):
    inv_count = modules_with_inv[mod]
    label = f'{mod.replace("_IDU","")}  —  {inv_count} inversion{"s" if inv_count>1 else ""}'
    vis = [visibility_map[t] == idx for t in range(n_total)]
    expected_order, ade_order, _, _ = build_module_data(mod)
    n_sess = len(expected_order) if expected_order else 0
    buttons.append(dict(
        label=label,
        method='update',
        args=[
            {'visible': vis},
            {'title': {
                'text': (
                    f'<b>{mod.replace("_IDU","")}</b> — Séquence pédagogique vs chronologie ADE<br>'
                    f'<sup>{inv_count} inversion(s) détectée(s) sur {n_sess} séances vérifiées'
                    f'  |  <span style="color:#3498DB">●CM</span>'
                    f'  <span style="color:#E67E22">●TD</span>'
                    f'  <span style="color:#2ECC71">●TP</span>'
                    f'  |  <span style="color:#E74C3C">— Inversion</span>'
                    f'  <span style="color:#2ECC71">··· Ordre correct</span></sup>'
                ),
                'font': {'size': 14},
                'x': 0.5,
            }}
        ],
    ))

# Titre initial
first_mod = mods_list[0]
first_inv = modules_with_inv[first_mod]
first_exp, _, _, _ = build_module_data(first_mod)
n_first = len(first_exp) if first_exp else 0

fig.update_layout(
    updatemenus=[dict(
        buttons=buttons,
        direction='down',
        showactive=True,
        x=0.0, xanchor='left',
        y=1.18, yanchor='top',
        bgcolor='#ECF0F1',
        bordercolor='#BDC3C7',
        font=dict(size=12),
    )],
    title=dict(
        text=(
            f'<b>{first_mod.replace("_IDU","")}</b> — Séquence pédagogique vs chronologie ADE<br>'
            f'<sup>{first_inv} inversion(s) sur {n_first} séances vérifiées'
            f'  |  <span style="color:#3498DB">●CM</span>'
            f'  <span style="color:#E67E22">●TD</span>'
            f'  <span style="color:#2ECC71">●TP</span>'
            f'  |  <span style="color:#E74C3C">— Inversion</span>'
            f'  <span style="color:#2ECC71">··· Ordre correct</span></sup>'
        ),
        font=dict(size=14), x=0.5,
    ),
    xaxis=dict(
        range=[-0.05, 1.25],
        showgrid=False, zeroline=False,
        showticklabels=False,
    ),
    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    plot_bgcolor='#F8F9FA',
    paper_bgcolor='white',
    height=700,
    margin=dict(l=20, r=20, t=130, b=60),
    annotations=[
        dict(
            text='<b>Ordre attendu (graphe)</b>',
            x=0.1, y=1.04, xref='paper', yref='paper',
            showarrow=False, font=dict(size=13, color='#2C3E50'),
            xanchor='center',
        ),
        dict(
            text='<b>Chronologie ADE</b>',
            x=0.9, y=1.04, xref='paper', yref='paper',
            showarrow=False, font=dict(size=13, color='#2C3E50'),
            xanchor='center',
        ),
        dict(
            text='Survolez une séance ou une ligne pour les détails',
            x=0.5, y=-0.06, xref='paper', yref='paper',
            showarrow=False, font=dict(size=10, color='#95A5A6'),
            xanchor='center',
        ),
    ],
)

out = Path(__file__).parent / 'axe6_sequence_vs_ade.html'
fig.write_html(str(out))
print(f'Graphique interactif sauvegardé : {out}')
