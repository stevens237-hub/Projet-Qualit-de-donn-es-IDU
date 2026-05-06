from typing import Literal, TypedDict

Criticite = Literal["bloquant", "majeur", "mineur"]

ANOMALY_COLUMNS = ["source_1", "source_2", "axe", "description", "criticite"]


class AnomalyRecord(TypedDict):
    source_1: str
    source_2: str
    axe: str
    description: str
    criticite: Criticite
