from typing import Literal, TypedDict

Criticite = Literal["bloquant", "majeur", "mineur"]

ANOMALY_COLUMNS = ["module", "source", "axe", "description", "criticite"]


class AnomalyRecord(TypedDict):
    module: str
    source: str
    axe: str
    description: str
    criticite: Criticite
