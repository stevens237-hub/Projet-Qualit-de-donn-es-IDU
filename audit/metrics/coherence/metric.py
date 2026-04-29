import pandas as pd

from audit.core.base_metric import BaseMetric
from audit.core.models import ANOMALY_COLUMNS
from audit.metrics.coherence.rules.code_normalisation import check_code_normalisation
from audit.metrics.coherence.rules.dep_graph import (
    check_dep_graph_vs_maquette,
    check_maquette_dep_graph_coverage,
)
from audit.metrics.coherence.rules.moodle import check_moodle_fantomes, check_moodle_vs_maquette
from audit.metrics.coherence.rules.responsables import (
    check_intervenants_non_references,
    check_responsable_presence,
)
from audit.metrics.coherence.rules.sequence_chronologie import check_sequence_vs_chronologie
from audit.metrics.coherence.rules.session_types import (
    check_type_encoding_consistency,
    check_unexpected_session_types,
)
from audit.metrics.coherence.rules.timezone import check_timezone_anomalies


class CoherenceMetric(BaseMetric):
    name = "coherence"
    description = "Cohérence inter-sources des données IDU — 8 axes"

    def run(self, data: dict) -> pd.DataFrame:
        rows: list[dict] = []
        rows += check_code_normalisation(data)          # Axe 1
        rows += check_responsable_presence(data)         # Axe 2a
        rows += check_intervenants_non_references(data)  # Axe 2b
        rows += check_dep_graph_vs_maquette(data)        # Axe 3a
        rows += check_maquette_dep_graph_coverage(data)  # Axe 3b
        rows += check_unexpected_session_types(data)     # Axe 4
        rows += check_timezone_anomalies(data)           # Axe 5
        rows += check_sequence_vs_chronologie(data)      # Axe 6
        rows += check_moodle_vs_maquette(data)           # Axe 7a
        rows += check_moodle_fantomes(data)              # Axe 7b
        rows += check_type_encoding_consistency(data)    # Axe 8

        if not rows:
            return self._empty_df()
        return pd.DataFrame(rows)[ANOMALY_COLUMNS]
