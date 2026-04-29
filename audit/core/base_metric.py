from abc import ABC, abstractmethod

import pandas as pd

from audit.core.models import ANOMALY_COLUMNS


class BaseMetric(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, data: dict) -> pd.DataFrame:
        """Run the audit and return a DataFrame of anomalies.

        The returned DataFrame must have columns: module, source, axe, description, criticite.
        criticite values: "bloquant" | "majeur" | "mineur"
        """
        ...

    def summary(self, anomalies: pd.DataFrame) -> dict:
        return {
            "metric": self.name,
            "total_anomalies": len(anomalies),
            "by_criticite": anomalies["criticite"].value_counts().to_dict() if not anomalies.empty else {},
            "by_axe": anomalies["axe"].value_counts().to_dict() if not anomalies.empty else {},
        }

    def _empty_df(self) -> pd.DataFrame:
        return pd.DataFrame(columns=ANOMALY_COLUMNS)
