"""Axe 6 — Cohérence séquence pédagogique ↔ chronologie ADE.

Le graphe de dépendances définit un ordre entre les séances :
    (module, type, n°) doit précéder (module, type, n°)
    ex: ISOC631 CM n°1 → ISOC631 TD n°1 → ISOC631 CM n°2 …

Cette règle attribue des numéros implicites aux séances ADE (en triant
chronologiquement par type), puis vérifie que l'ordre obtenu respecte
chaque arc du graphe.

Les séances de groupes parallèles (TPG1/TPG2, TDG, …) qui tombent dans
la même semaine ISO sont fusionnées en un seul slot pédagogique.

Signalement dans les logs (pas dans les anomalies) :
  [AXE6][COMPLETUDE] modules absents de l'ADE
  [AXE6][COMPLETUDE] séances référencées dans le graphe mais manquantes en ADE
"""

import pandas as pd

# Mapping : segment de titre (en majuscules) → type canonique du graphe
_TYPE_PARTS: dict[str, str] = {
    'CM': 'CM',
    'TD': 'TD', 'TDG': 'TD', 'TDTP': 'TD',
    'TP': 'TP', 'TPG1': 'TP', 'TPG2': 'TP', 'TPPG': 'TP',
    'PROJ': 'PROJ', 'PROJET': 'PROJ',
    'EXAM': 'Exam', 'ET': 'Exam', 'EX': 'Exam', 'CMEX': 'Exam',
    'CT': 'Exam', 'CC': 'Exam', 'DS': 'Exam',
}


def _get_session_type(row: pd.Series) -> str | None:
    """Extrait le type canonique d'une séance ADE.

    Priorité :
      1. session_type_title  (regex sur le titre, via loader)
      2. session_type_desc   (regex sur la description ADE, via loader)
      3. scan des segments du titre en fallback
    """
    if pd.notna(row.get('session_type_title')):
        return _TYPE_PARTS.get(str(row['session_type_title']).upper())

    if pd.notna(row.get('session_type_desc')):
        return _TYPE_PARTS.get(str(row['session_type_desc']).upper())

    title = str(row.get('Title', ''))
    for part in title.upper().split('_')[1:]:
        mapped = _TYPE_PARTS.get(part)
        if mapped:
            return mapped

    return None


def _build_session_slots(ade_module: pd.DataFrame) -> dict[str, list[pd.Timestamp]]:
    """Retourne {type: [date_slot_1, date_slot_2, …]} triés chronologiquement.

    Les séances de groupes parallèles (TPG1 / TPG2) tombant dans la même
    semaine ISO sont fusionnées en un slot unique (date minimale de la semaine).
    """
    df = ade_module.copy()
    df['stype'] = df.apply(_get_session_type, axis=1)
    iso = df['Starts'].dt.isocalendar()
    df['_year'] = iso['year']
    df['_week'] = iso['week']

    result: dict[str, list[pd.Timestamp]] = {}
    for stype, group in df.dropna(subset=['stype']).groupby('stype'):
        slots = group.groupby(['_year', '_week'])['Starts'].min().sort_values()
        result[str(stype)] = slots.tolist()

    return result


def check_sequence_vs_chronologie(data: dict) -> list[dict]:
    """Axe 6 : l'ordre chronologique des séances ADE doit respecter le graphe."""
    ade: pd.DataFrame = data['ade']
    dep_graph: pd.DataFrame = data['dep_graph']

    # Construire les slots de séances par module
    session_slots: dict[str, dict[str, list[pd.Timestamp]]] = {}
    for module in dep_graph['module_precedent'].unique():
        ade_mod = ade[ade['canonical_code'] == module]
        if ade_mod.empty:
            print(
                f"[AXE6][COMPLETUDE] Module '{module}' absent de l'ADE "
                f"— à signaler à l'équipe complétude"
            )
            continue
        session_slots[module] = _build_session_slots(ade_mod)

    anomalies = []
    logged_missing: set[tuple] = set()

    for _, row in dep_graph.iterrows():
        module = row['module_precedent']
        type_prec = row['type_precedent']
        type_suiv = row['type_suivant']
        num_prec = int(row['numero_precedent'])
        num_suiv = int(row['numero_suivant'])

        if module not in session_slots:
            continue

        slots = session_slots[module]
        dates_prec = slots.get(type_prec, [])
        dates_suiv = slots.get(type_suiv, [])

        # Sessions manquantes → log pour l'équipe complétude, pas d'anomalie cohérence
        if len(dates_prec) < num_prec:
            key = (module, type_prec, num_prec)
            if key not in logged_missing:
                logged_missing.add(key)
                print(
                    f"[AXE6][COMPLETUDE] {module} : {len(dates_prec)} séance(s) "
                    f"{type_prec} dans ADE, graphe attend {type_prec} n°{num_prec}"
                )
            continue

        if len(dates_suiv) < num_suiv:
            key = (module, type_suiv, num_suiv)
            if key not in logged_missing:
                logged_missing.add(key)
                print(
                    f"[AXE6][COMPLETUDE] {module} : {len(dates_suiv)} séance(s) "
                    f"{type_suiv} dans ADE, graphe attend {type_suiv} n°{num_suiv}"
                )
            continue

        date_prec = dates_prec[num_prec - 1]
        date_suiv = dates_suiv[num_suiv - 1]

        if date_prec >= date_suiv:
            order = "le même jour que" if date_prec.date() == date_suiv.date() else "après"
            anomalies.append({
                'source_1': f"{module} : {type_prec} n°{num_prec} -> {type_suiv} n°{num_suiv} (graphe de dépendances)",
                'source_2': f"{module} : {type_prec} n°{num_prec} ({date_prec.date()}) {order} {type_suiv} n°{num_suiv} ({date_suiv.date()}) (ADE)",
                'axe': 'sequence_chronologie',
                'description': (
                    f"{module} : le graphe exige que {type_prec} n°{num_prec} précède "
                    f"{type_suiv} n°{num_suiv}, mais dans ADE {type_prec} n°{num_prec} "
                    f"se déroule {order} {type_suiv} n°{num_suiv} "
                    f"({date_prec.date()} vs {date_suiv.date()})."
                ),
                'criticite': 'majeur',
            })

    return anomalies
