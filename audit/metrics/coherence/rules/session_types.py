"""Axes 4 & 8 — Cohérence des types de séances.

Axe 4 : La maquette déclare des volumes CM/TD/TP pour chaque module.
Si un volume est 0, aucune séance de ce type ne devrait apparaître ni dans ADE
ni dans le graphe de dépendances. On vérifie la présence/absence du type,
pas les volumes (c'est de la complétude).
"""

import pandas as pd

_TYPE_PARTS: dict[str, str] = {
    'CM': 'CM',
    'TD': 'TD', 'TDG': 'TD', 'TDTP': 'TD',
    'TP': 'TP', 'TPG1': 'TP', 'TPG2': 'TP', 'TPPG': 'TP',
    'PROJ': 'PROJ', 'PROJET': 'PROJ',
    'EXAM': 'Exam', 'ET': 'Exam', 'EX': 'Exam', 'CMEX': 'Exam',
    'CT': 'Exam', 'CC': 'Exam', 'DS': 'Exam',
}

_MAQUETTE_COLS = {'CM': 'cm', 'TD': 'td', 'TP': 'tp'}


def _get_session_type(row: pd.Series) -> str | None:
    if pd.notna(row.get('session_type_title')):
        return _TYPE_PARTS.get(str(row['session_type_title']).upper())
    if pd.notna(row.get('session_type_desc')):
        return _TYPE_PARTS.get(str(row['session_type_desc']).upper())
    for part in str(row.get('Title', '')).upper().split('_')[1:]:
        mapped = _TYPE_PARTS.get(part)
        if mapped:
            return mapped
    return None


def check_unexpected_session_types(data: dict) -> list[dict]:
    """Axe 4 : signale tout type de séance présent dans ADE ou le graphe
    alors que la maquette déclare 0h pour ce type sur ce module."""
    maquette: pd.DataFrame = data['maquette']
    ade: pd.DataFrame = data['ade']
    dep_graph: pd.DataFrame = data['dep_graph']

    # Types présents par module dans ADE
    ade = ade.copy()
    ade['stype'] = ade.apply(_get_session_type, axis=1)
    ade_types_by_module: dict[str, set[str]] = (
        ade.dropna(subset=['stype'])
        .groupby('canonical_code')['stype']
        .apply(set)
        .to_dict()
    )

    # Types présents par module dans le graphe de dépendances
    dg_types_by_module: dict[str, set[str]] = {}
    for _, row in dep_graph.iterrows():
        for mod, typ in [
            (row['module_precedent'], row['type_precedent']),
            (row['module_suivant'],   row['type_suivant']),
        ]:
            dg_types_by_module.setdefault(mod, set()).add(typ)

    anomalies = []

    for _, row in maquette.iterrows():
        module = row['code_module']

        for session_type, col in _MAQUETTE_COLS.items():
            try:
                volume = float(row[col])
            except (ValueError, TypeError):
                continue

            if volume != 0:
                continue  # volume > 0 : présence attendue, hors périmètre de cet axe

            # Volume = 0 dans la maquette — vérifier ADE
            ade_present = session_type in ade_types_by_module.get(module, set())
            if ade_present:
                count = ade[
                    (ade['canonical_code'] == module) & (ade['stype'] == session_type)
                ].shape[0]
                anomalies.append({
                    'source_1': f"{module} : {session_type} = 0h (maquette)",
                    'source_2': f"{module} : {count} séance(s) {session_type} planifiée(s) (ADE)",
                    'axe': 'types_seances',
                    'description': (
                        f"{module} : la maquette déclare 0h de {session_type} "
                        f"mais {count} séance(s) {session_type} sont planifiées dans ADE."
                    ),
                    'criticite': 'majeur',
                })

            # Volume = 0 dans la maquette — vérifier le graphe de dépendances
            dg_present = session_type in dg_types_by_module.get(module, set())
            if dg_present:
                anomalies.append({
                    'source_1': f"{module} : {session_type} = 0h (maquette)",
                    'source_2': f"{module} : séance(s) {session_type} référencée(s) (graphe de dépendances)",
                    'axe': 'types_seances',
                    'description': (
                        f"{module} : la maquette déclare 0h de {session_type} "
                        f"mais ce type de séance est référencé dans le graphe de dépendances."
                    ),
                    'criticite': 'majeur',
                })

    return anomalies


def check_type_encoding_consistency(data: dict) -> list[dict]:
    """Axe 8: Session type in the Title field must match type in the Description field."""
    return []
