"""Point d'entrée de l'audit — charge les données et exécute toutes les métriques."""

import json
from datetime import datetime, timezone

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
    generated_at = datetime.now(timezone.utc).isoformat()

    print(f"Chargement des données depuis {DATA_DIR} ...")
    data = load_all_data(DATA_DIR)

    full_report: dict = {
        "generated_at": generated_at,
        "metrics": {},
    }

    for metric in METRICS:
        print(f"  [{metric.name}] en cours...")
        anomalies = metric.run(data)

        # Export CSV global de la métrique (pour Power BI)
        csv_path = OUTPUT_DIR / f"{metric.name}_anomalies.csv"
        anomalies.to_csv(csv_path, index=False, encoding='utf-8-sig')

        # Export par axe : un CSV + un JSON par axe
        axes_data = {}
        if not anomalies.empty:
            for axe, group in anomalies.groupby("axe"):
                axe_records = group.to_dict(orient="records")
                axes_data[axe] = axe_records

                axe_csv = OUTPUT_DIR / f"{axe}_anomalies.csv"
                group.to_csv(axe_csv, index=False, encoding='utf-8-sig')

                axe_json = OUTPUT_DIR / f"{axe}_anomalies.json"
                with open(axe_json, 'w', encoding='utf-8') as f:
                    json.dump({
                        "generated_at": generated_at,
                        "metric": metric.name,
                        "axe": axe,
                        "total": len(group),
                        "anomalies": axe_records,
                    }, f, ensure_ascii=False, indent=2)

                print(f"    [{axe}] {len(group)} anomalies -> {axe_json.name}")

        # Construction du bloc JSON pour cette métrique
        full_report["metrics"][metric.name] = {
            "description": metric.description,
            "summary": metric.summary(anomalies),
            "anomalies": anomalies.to_dict(orient="records"),
        }

        print(f"  [{metric.name}] {len(anomalies)} anomalies -> {csv_path.name}")

    # Export JSON structuré complet
    json_path = OUTPUT_DIR / "audit_report.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(full_report, f, ensure_ascii=False, indent=2)

    print(f"\nAudit terminé — rapport JSON : {json_path}")


if __name__ == '__main__':
    main()
