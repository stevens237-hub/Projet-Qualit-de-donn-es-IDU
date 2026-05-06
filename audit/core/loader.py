"""Chargement et normalisation des sources de données IDU.

CONVENTION DE NORMALISATION
============================
Tous les codes modules sont normalisés sous la forme <PREFIX>_IDU (ex: INFO731_IDU)
quelle que soit leur forme d'origine dans la source :

    Source          Forme brute             Après normalisation
    -------         ------------------      -------------------
    Maquette        INFO501_PACY            INFO501_IDU
    Maquette        INFO631_IDU             INFO631_IDU  (inchangé)
    ADE (titre)     INFO731_INGE_CM         canonical_code = INFO731_IDU
    Responsables    INFO501_PACY            INFO501_IDU
    Dep graph       ISOC631_IDU             ISOC631_IDU  (inchangé)
    Moodle HTML     INFO731_INGE / _IDU     INFO731_IDU

"""

import json
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

_TITLE_RE = re.compile(r'^([A-Z]{2,6}\d{3})_([A-Z]+)_(CM|TD|TP|Proj|DS)(\d+)?$')
_PREFIX_TYPE_RE = re.compile(r'^(CM|TD|TP)\s+([A-Z]{2,6}\d{3})$')
_DESC_TYPE_RE = re.compile(r'\((CM|TD|TP|Proj|DS)\)')


def _to_idu(code: str) -> str:
    """Normalise un code module vers la forme <PREFIX>_IDU.

    Exemples :
        'INFO731_IDU'  → 'INFO731_IDU'
        'INFO501_PACY' → 'INFO501_IDU'
        'INFO731'      → 'INFO731_IDU'
    """
    return code.split('_')[0] + '_IDU'


def _extract_from_title(title: str) -> tuple[str, str | None, str | None]:
    """Extrait (base_code, ade_group, session_type) depuis un titre ADE.

    Gère deux formats :
      - Standard  : 'INFO731_INGE_CM'  → base='INFO731', group='INGE', type='CM'
      - Préfixé   : 'CM INFO931'       → base='INFO931', group=None,   type='CM'

    base_code est normalisé vers 'BASE_IDU' dans load_all_data via _to_idu().
    """
    m = _TITLE_RE.match(title)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m2 = _PREFIX_TYPE_RE.match(title)
    if m2:
        return m2.group(2), None, m2.group(1)
    return title.split('_')[0], None, None


def _parse_description(desc: str) -> tuple[str | None, str | None, str | None]:
    """Extrait (session_type, groupe, intervenant) depuis le champ Description ADE.

    Format des lignes non vides dans une description ADE :
        0 : "NOM_MODULE (TYPE)"          ex: "INFO731 Sécurité et Cryptographie (CM)"
        1 : groupe                        ex: "IDU-4-Promo"
        2 : nom de l'intervenant          ex: "SALAMATIAN MOHAMMAD-REZA"
        3 : "(Exporté le: ...)"
    """
    if not isinstance(desc, str):
        return None, None, None

    lines = [l.strip() for l in desc.split('\n') if l.strip()]
    session_type = None
    groupe = None
    intervenant = None

    if lines:
        m = _DESC_TYPE_RE.search(lines[0])
        session_type = m.group(1) if m else None
    if len(lines) > 1:
        groupe = lines[1]
    if len(lines) > 2 and not lines[2].startswith('('):
        intervenant = lines[2]

    return session_type, groupe, intervenant


def _load_ade(path: Path) -> pd.DataFrame:
    """Charge un fichier ADE JSON et enrichit les colonnes dérivées du titre et de la description."""
    with open(path, encoding='utf-8') as f:
        events = json.load(f)

    df = pd.DataFrame(events)

    parsed_titles = df['Title'].apply(_extract_from_title)
    df['canonical_code'] = [p[0] for p in parsed_titles]   # base brute, normalisée plus tard
    df['ade_group'] = [p[1] for p in parsed_titles]
    df['session_type_title'] = [p[2] for p in parsed_titles]

    parsed_descs = df['Description'].apply(_parse_description)
    df['session_type_desc'] = [p[0] for p in parsed_descs]
    df['groupe'] = [p[1] for p in parsed_descs]
    df['intervenant'] = [p[2] for p in parsed_descs]

    df['Starts'] = pd.to_datetime(df['Starts'], utc=True)
    df['Ends'] = pd.to_datetime(df['Ends'], utc=True)
    return df


def _load_json_table(path: Path) -> pd.DataFrame:
    """Charge un export PHPMyAdmin JSON — extrait le premier bloc 'table'."""
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    for entry in raw:
        if isinstance(entry, dict) and entry.get('type') == 'table':
            return pd.DataFrame(entry['data'])
    return pd.DataFrame()


def _find_moodle_file(root: Path) -> Path | None:
    html_files = list(root.glob('*.html'))
    return html_files[0] if html_files else None


def _parse_moodle(path: Path) -> tuple[list[str], list[str]]:
    """Retourne (codes_bruts, codes_normalises) trouvés dans le HTML Moodle.

    codes_bruts      : formes originales dans le HTML (ex: 'INFO731_INGE', 'INFO631_IDU')
    codes_normalises : toutes converties en _IDU (ex: 'INFO731_IDU', 'INFO631_IDU')
    """
    with open(path, encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    text = soup.get_text()
    matches = re.findall(r'[A-Z]{2,6}\d{3}(?:_IDU|_PACY|_INGE)', text)
    raw = list(set(matches))
    normalized = list({_to_idu(c) for c in matches})
    return raw, normalized


def load_all_data(data_dir: str | Path) -> dict:
    """Charge et normalise toutes les sources de données IDU.

    Tous les codes modules sont normalisés vers la forme <PREFIX>_IDU
    (voir la convention en haut de ce fichier).

    Retourne un dict avec les clés :
        maquette       — DataFrame : code_module (_IDU), raw_code (brut), nom, ects, cm, td, tp
        responsables   — DataFrame : code_module (_IDU), raw_code (brut), nom, prenom
        dep_graph      — DataFrame : module_precedent (_IDU), type_precedent, numero_precedent,
                                     module_suivant (_IDU), type_suivant, numero_suivant
        ade            — DataFrame : canonical_code (_IDU), raw_canonical_code (brut),
                                     session_type_title, session_type_desc, groupe,
                                     intervenant, year, ade_group
        ade_idu3/4/5   — DataFrames ADE par année
        moodle_modules — list[str] : codes _IDU trouvés dans le résumé Moodle
        moodle_raw     — list[str] : codes bruts trouvés dans le résumé Moodle
    """
    root = Path(data_dir)

    # --- Chargement brut ---
    maquette = _load_json_table(root / 'MAQUETTE_IDU.json')
    responsables = _load_json_table(root / 'Responsables_modules_IDU.json')
    dep_graph = _load_json_table(root / 'dependance_sequence_IDU.json')

    ade3 = _load_ade(root / 'ADECal_IDU3.json')
    ade4 = _load_ade(root / 'ADECal_IDU4.json')
    ade5 = _load_ade(root / 'ADECal_IDU5.json')
    ade3['year'] = 'IDU3'
    ade4['year'] = 'IDU4'
    ade5['year'] = 'IDU5'
    ade_all = pd.concat([ade3, ade4, ade5], ignore_index=True)

    # --- Capture des codes bruts avant normalisation (utilisés par l'Axe 1) ---
    maquette['raw_code'] = maquette['code_module'].copy()
    responsables['raw_code'] = responsables['code_module'].copy()
    for df in [ade3, ade4, ade5, ade_all]:
        df['raw_canonical_code'] = df.apply(
            lambda r: f"{r['canonical_code']}_{r['ade_group']}"
                      if pd.notna(r['ade_group']) else r['canonical_code'],
            axis=1,
        )

    # --- Normalisation _IDU sur toutes les sources ---
    maquette['code_module'] = maquette['code_module'].map(_to_idu)
    responsables['code_module'] = responsables['code_module'].map(_to_idu)
    dep_graph['module_precedent'] = dep_graph['module_precedent'].map(_to_idu)
    dep_graph['module_suivant'] = dep_graph['module_suivant'].map(_to_idu)
    for df in [ade3, ade4, ade5, ade_all]:
        df['canonical_code'] = df['canonical_code'].map(_to_idu)

    moodle_path = _find_moodle_file(root)
    if moodle_path:
        moodle_raw, moodle_modules = _parse_moodle(moodle_path)
    else:
        moodle_raw, moodle_modules = [], []

    return {
        'maquette': maquette,
        'responsables': responsables,
        'dep_graph': dep_graph,
        'ade': ade_all,
        'ade_idu3': ade3,
        'ade_idu4': ade4,
        'ade_idu5': ade5,
        'moodle_modules': moodle_modules,
        'moodle_raw': moodle_raw,
    }
