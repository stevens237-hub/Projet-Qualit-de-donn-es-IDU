"""Axe 1 — Cohérence des nommages : la forme BASE_IDU doit apparaître dans chaque titre ADE.

La maquette référence tous les modules sous la forme BASE_IDU (ex: INFO634_IDU).
Cette règle vérifie que, pour chaque titre ADE qui mentionne la base d'un module de la
maquette, la forme complète BASE_IDU est bien présente dans ce titre (en n'importe quelle
position).

    Titre ADE                   Base détectée  Réf maquette  Résultat
    -------------------------   -------------  ------------  --------
    INFO634_INGE_CM             INFO634        INFO634_IDU   ❌ anomalie
    CM INFO931                  INFO931        INFO931_IDU   ❌ anomalie
    DATA931_CM                  DATA931        DATA931_IDU   ❌ anomalie
    ISOC831_Sopra_AdminLinux    ISOC831        ISOC831_IDU   ❌ anomalie
    INFO633_A01_G1              INFO633        INFO633_IDU   ❌ anomalie
    PROJ631_IDU_01_4H1          PROJ631        PROJ631_IDU   ✓ cohérent
"""

import json
import re
from pathlib import Path

from audit.core.config import DATA_DIR

_BASE_RE = re.compile(r'[A-Z]{2,6}\d{3}')
_ADE_FILES = ['ADECal_IDU3.json', 'ADECal_IDU4.json', 'ADECal_IDU5.json']


def _load_maquette_refs(data_dir: Path) -> dict[str, str]:
    """Retourne {base: ref_IDU}  ex: {'INFO634': 'INFO634_IDU'}"""
    with open(data_dir / 'MAQUETTE_IDU.json', encoding='utf-8') as f:
        raw = json.load(f)
    for entry in raw:
        if isinstance(entry, dict) and entry.get('type') == 'table':
            return {
                row['code_module'].split('_')[0]: row['code_module'].split('_')[0] + '_IDU'
                for row in entry['data']
            }
    return {}


def _load_ade_titles(data_dir: Path) -> set[str]:
    """Retourne l'ensemble des titres uniques depuis les 3 fichiers ADE."""
    titles: set[str] = set()
    for fname in _ADE_FILES:
        with open(data_dir / fname, encoding='utf-8') as f:
            events = json.load(f)
        for event in events:
            titles.add(event['Title'])
    return titles


def check_code_normalisation(data: dict) -> list[dict]:
    """Axe 1 : signale tout titre ADE dont la forme BASE_IDU est absente.

    Pour chaque titre ADE, détecte toutes les bases de modules (ex: INFO634) présentes
    n'importe où dans le titre via regex, puis vérifie que la forme canonique (INFO634_IDU)
    y figure aussi. Couvre les formats : BASE_INGE_CM, CM BASE, BASE_A01_G1, BASE_Sopra_xxx…
    """
    maquette = _load_maquette_refs(DATA_DIR)
    titles = _load_ade_titles(DATA_DIR)

    anomalies = []
    for title in titles:
        for base in _BASE_RE.findall(title):
            ref = maquette.get(base)
            if ref is None:
                continue  # base absente de la maquette IDU, hors périmètre
            if ref not in title:
                coherent_form = title.replace(base, ref, 1)
                anomalies.append({
                    'source_1': title,
                    'source_2': ref,
                    'axe': 'normalisation_codes',
                    'description': (
                        f"Le module '{base}' est nommé '{title}' dans ADE "
                        f"au lieu de '{coherent_form}' (forme cohérente avec la maquette)"
                    ),
                    'criticite': 'majeur',
                })

    return anomalies
