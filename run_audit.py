"""Point d'entrée de l'audit — charge les données et exécute toutes les métriques."""

import json

from audit.core.config import DATA_DIR, OUTPUT_DIR
from audit.core.loader import load_all_data
from audit.metrics.coherence.metric import CoherenceMetric

# --- Ajoutez les métriques de vos collègues ici ---
# from audit.metrics.completude.metric import CompletudMetric
# from audit.metrics.exactitude.metric import ExactitudeMetric

METRICS = [
    CoherenceMetric(),
    # CompletudMetric(),
    # ExactitudeMetric(),
]


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    print(f"Chargement des données depuis {DATA_DIR} ...")
    data = load_all_data(DATA_DIR)

    report: dict = {}
    for metric in METRICS:
        print(f"  [{metric.name}] en cours...")
        anomalies = metric.run(data)
        csv_path = OUTPUT_DIR / f"{metric.name}_anomalies.csv"
        anomalies.to_csv(csv_path, index=False, encoding='utf-8-sig')
        report[metric.name] = metric.summary(anomalies)
        print(f"  [{metric.name}] {len(anomalies)} anomalies → {csv_path.name}")

    report_path = OUTPUT_DIR / "audit_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nAudit terminé — rapport : {report_path}")


if __name__ == '__main__':
    main()
