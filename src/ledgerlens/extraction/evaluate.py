"""Field-level extraction accuracy vs ground truth, plus validation quality
(did injected errors get caught?). Logged to MLflow.

Usage:
    python -m ledgerlens.extraction.evaluate
"""

from __future__ import annotations

import json
import logging

import mlflow

from ledgerlens.extraction.extract import extract_pdf
from ledgerlens.settings import get_config, get_settings, resolve_path
from ledgerlens.validation.rules import validate_invoice

logger = logging.getLogger(__name__)

FIELDS = ["invoice_no", "vendor", "invoice_date", "due_date", "subtotal", "tax", "total"]


def _match(field: str, extracted, truth) -> bool:
    if extracted is None:
        return False
    if field in ("subtotal", "tax", "total"):
        try:
            return abs(float(extracted) - float(truth)) < 0.01
        except (TypeError, ValueError):
            return False
    return str(extracted).strip() == str(truth).strip()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = get_config()
    pdf_dir = resolve_path(cfg["corpus"]["pdf_dir"])
    truth_dir = resolve_path(cfg["corpus"]["truth_dir"])
    pairs = [
        (pdf, truth_dir / f"{pdf.stem}.json")
        for pdf in sorted(pdf_dir.glob("*.pdf"))
        if (truth_dir / f"{pdf.stem}.json").exists()
    ]
    if not pairs:
        raise SystemExit("No corpus; run `python -m ledgerlens.corpus.generate` first")

    mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
    mlflow.set_experiment(cfg["eval"]["experiment_name"])

    hits = dict.fromkeys(FIELDS, 0)
    error_caught = error_total = clean_flagged = clean_total = 0
    seen: dict[str, str] = {}
    for pdf, truth_path in pairs:
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        inv = extract_pdf(pdf)
        for field in FIELDS:
            if _match(field, inv.get(field), truth[field]):
                hits[field] += 1
        findings = validate_invoice(inv, seen)
        has_error_finding = any(f.severity == "error" for f in findings)
        if truth["errors"]:
            error_total += 1
            if has_error_finding:
                error_caught += 1
        else:
            clean_total += 1
            if has_error_finding:
                clean_flagged += 1

    n = len(pairs)
    with mlflow.start_run(run_name="extraction-eval"):
        metrics = {f"acc_{field}": hits[field] / n for field in FIELDS}
        metrics["acc_mean"] = sum(metrics.values()) / len(FIELDS)
        metrics["validation_recall"] = error_caught / max(error_total, 1)
        metrics["validation_false_alarm_rate"] = clean_flagged / max(clean_total, 1)
        mlflow.log_params({"n_invoices": n})
        mlflow.log_metrics(metrics)
        for field in FIELDS:
            logger.info("%s: %.1f%%", field, 100 * hits[field] / n)
        logger.info(
            "mean field accuracy %.1f%% | validation recall %.1f%% | false alarms %.1f%%",
            100 * metrics["acc_mean"],
            100 * metrics["validation_recall"],
            100 * metrics["validation_false_alarm_rate"],
        )


if __name__ == "__main__":
    main()
