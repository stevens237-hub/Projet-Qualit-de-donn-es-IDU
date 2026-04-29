import json
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

_TITLE_RE = re.compile(r'^([A-Z]{2,6}\d{3})_([A-Z]+)_(CM|TD|TP|Proj|DS)(\d+)?$')
_DESC_TYPE_RE = re.compile(r'\((CM|TD|TP|Proj|DS)\)')


def _extract_from_title(title: str) -> tuple[str, str | None, str | None]:
    """Return (canonical_code, ade_group, session_type) from an ADE Title."""
    m = _TITLE_RE.match(title)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return title.split('_')[0], None, None


def _parse_description(desc: str) -> tuple[str | None, str | None, str | None]:
    """Return (session_type, groupe, intervenant) from an ADE Description field.

    ADE description format (non-empty lines):
        0: "MODULE_NAME (TYPE)"
        1: group (e.g. "IDU-4-Promo")
        2: intervenant full name
        3: "(Exporté le:...)"
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
    with open(path, encoding='utf-8') as f:
        events = json.load(f)

    df = pd.DataFrame(events)

    parsed_titles = df['Title'].apply(_extract_from_title)
    df['canonical_code'] = [p[0] for p in parsed_titles]
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
    """Load a PHPMyAdmin JSON export — extracts the first 'table' entry's data."""
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    for entry in raw:
        if isinstance(entry, dict) and entry.get('type') == 'table':
            return pd.DataFrame(entry['data'])
    return pd.DataFrame()


def _find_moodle_file(root: Path) -> Path | None:
    html_files = list(root.glob('*.html'))
    return html_files[0] if html_files else None


def _parse_moodle(path: Path) -> list[str]:
    """Return list of unique module base codes found in the Moodle HTML."""
    with open(path, encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    text = soup.get_text()
    matches = re.findall(r'[A-Z]{2,6}\d{3}(?:_IDU|_PACY|_INGE)', text)
    return list({c.split('_')[0] for c in matches})


def load_all_data(data_dir: str | Path) -> dict:
    """Load and normalize all IDU data sources.

    Returns a dict with keys:
        maquette       — DataFrame: code_module, nom, ects, cm, td, tp
        responsables   — DataFrame: code_module, nom, prenom
        dep_graph      — DataFrame: module_precedent, type_precedent, numero_precedent,
                                    module_suivant,   type_suivant,   numero_suivant
        ade            — DataFrame: all years combined, enriched with canonical_code,
                                    session_type_title, session_type_desc, groupe,
                                    intervenant, year
        ade_idu3/4/5   — per-year ADE DataFrames
        moodle_modules — list[str] of base codes found in Moodle HTML
    """
    root = Path(data_dir)

    ade3 = _load_ade(root / 'ADECal_IDU3.json')
    ade4 = _load_ade(root / 'ADECal_IDU4.json')
    ade5 = _load_ade(root / 'ADECal_IDU5.json')

    ade3['year'] = 'IDU3'
    ade4['year'] = 'IDU4'
    ade5['year'] = 'IDU5'
    ade_all = pd.concat([ade3, ade4, ade5], ignore_index=True)

    moodle_path = _find_moodle_file(root)
    moodle_modules = _parse_moodle(moodle_path) if moodle_path else []

    return {
        'maquette': _load_json_table(root / 'MAQUETTE_IDU.json'),
        'responsables': _load_json_table(root / 'Responsables_modules_IDU.json'),
        'dep_graph': _load_json_table(root / 'dependance_sequence_IDU.json'),
        'ade': ade_all,
        'ade_idu3': ade3,
        'ade_idu4': ade4,
        'ade_idu5': ade5,
        'moodle_modules': moodle_modules,
    }
