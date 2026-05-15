"""
Project 1: The Self-Healing Reconciler

Compares data/HQ_Ledger.csv (headquarters) vs data/Sub_Ledger.csv (subsidiary)
using Pandas, then classifies each discrepancy with an AI agent.

Run: python scripts/reconciler.py
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MONTH_END_SUMMARY_PATH = PROJECT_ROOT / "Month_End_Summary.txt"

COMPARE_FIELDS = ("post_date", "account_code", "description", "debit", "credit", "currency")
AI_CATEGORIES = ("Timing difference", "Currency Error", "missing entry")
RISK_LEVELS = ("High", "Medium", "Low")


def load_ledger(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    for col in df.columns:
        df[col] = df[col].str.strip()
    df["_row"] = df.groupby("txn_id").cumcount()
    return df


def _normalize_amount(val: str) -> float | None:
    val = (val or "").strip()
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _row_amount(row: dict | None) -> float:
    """Largest non-zero debit/credit on a ledger row."""
    if not row:
        return 0.0
    debit = _normalize_amount(str(row.get("debit", ""))) or 0.0
    credit = _normalize_amount(str(row.get("credit", ""))) or 0.0
    return max(debit, credit)


def compute_discrepancy_variance(d: dict) -> float:
    """Monetary variance attributable to a single discrepancy (USD)."""
    issue = d.get("issue", "")
    diffs = d.get("diffs") or []

    if issue in ("missing_in_sub", "extra_in_sub", "duplicate_in_sub"):
        return _row_amount(d.get("hq") or d.get("sub"))

    amount_fields = {"debit", "credit"}
    variance = 0.0
    for diff in diffs:
        if diff.get("field") not in amount_fields:
            continue
        hq_amt = _normalize_amount(diff.get("hq", ""))
        sub_amt = _normalize_amount(diff.get("sub", ""))
        if hq_amt is not None and sub_amt is not None:
            variance += abs(hq_amt - sub_amt)

    if variance > 0:
        return variance

    if any(x.get("field") == "post_date" for x in diffs):
        return 0.0

    return _row_amount(d.get("hq") or d.get("sub"))


def compare_ledgers(hq_path: Path, sub_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """
    Load HQ and Sub CSVs and return all discrepancies between them.

    Returns:
        hq_df, sub_df, list of mismatch records (txn_id, issue, diffs, etc.)
    """
    hq = load_ledger(hq_path)
    sub = load_ledger(sub_path)
    return hq, sub, find_mismatches(hq, sub)


def find_mismatches(hq: pd.DataFrame, sub: pd.DataFrame) -> list[dict]:
    """Detect all discrepancies between HQ and Sub ledgers using Pandas."""
    discrepancies: list[dict] = []

    hq_ids = set(hq["txn_id"])
    sub_ids = set(sub["txn_id"])

    for txn_id in sorted(hq_ids - sub_ids):
        row = hq.loc[hq["txn_id"] == txn_id].iloc[0]
        discrepancies.append(
            {
                "txn_id": txn_id,
                "issue": "missing_in_sub",
                "description": row["description"],
                "hq": row.to_dict(),
                "sub": None,
                "diffs": [],
            }
        )

    for txn_id in sorted(sub_ids - hq_ids):
        row = sub.loc[sub["txn_id"] == txn_id].iloc[0]
        discrepancies.append(
            {
                "txn_id": txn_id,
                "issue": "extra_in_sub",
                "description": row["description"],
                "hq": None,
                "sub": row.to_dict(),
                "diffs": [],
            }
        )

    for txn_id in sorted(hq_ids & sub_ids):
        hq_count = int((hq["txn_id"] == txn_id).sum())
        sub_count = int((sub["txn_id"] == txn_id).sum())
        if sub_count > hq_count:
            row = sub.loc[sub["txn_id"] == txn_id].iloc[0]
            discrepancies.append(
                {
                    "txn_id": txn_id,
                    "issue": "duplicate_in_sub",
                    "description": row["description"],
                    "hq": hq.loc[hq["txn_id"] == txn_id].iloc[0].to_dict(),
                    "sub": row.to_dict(),
                    "diffs": [{"field": "duplicate", "hq": str(hq_count), "sub": str(sub_count)}],
                }
            )

    merged = hq.merge(
        sub,
        on=["txn_id", "_row"],
        how="outer",
        suffixes=("_hq", "_sub"),
        indicator=True,
    )

    for _, row in merged.iterrows():
        if row["_merge"] != "both":
            continue
        txn_id = row["txn_id"]

        diffs = []
        desc_hq = row.get("description_hq", "")
        for field in COMPARE_FIELDS:
            hq_val = str(row.get(f"{field}_hq", "") or "").strip()
            sub_val = str(row.get(f"{field}_sub", "") or "").strip()
            if hq_val != sub_val:
                diffs.append({"field": field, "hq": hq_val, "sub": sub_val})

        if diffs:
            discrepancies.append(
                {
                    "txn_id": txn_id,
                    "issue": "field_mismatch",
                    "description": desc_hq or row.get("description_sub", ""),
                    "hq": {f: row.get(f"{f}_hq", "") for f in COMPARE_FIELDS},
                    "sub": {f: row.get(f"{f}_sub", "") for f in COMPARE_FIELDS},
                    "diffs": diffs,
                }
            )

    return discrepancies


def _build_agent_prompt(discrepancy: dict) -> str:
    return json.dumps(
        {
            "txn_id": discrepancy["txn_id"],
            "issue": discrepancy["issue"],
            "description": discrepancy["description"],
            "field_diffs": discrepancy["diffs"],
        },
        indent=2,
    )


def classify_with_ai_agent(discrepancies: list[dict], model: str = "gpt-4o-mini") -> list[dict]:
    """
    Classify each discrepancy using an LLM agent.
    Falls back to rule-based classification when OPENAI_API_KEY is not set.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    results = []

    if api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            system_prompt = (
                "You are a finance reconciliation AI agent. "
                "Classify each ledger discrepancy into exactly ONE category:\n"
                "- Timing difference: dates differ but transaction is otherwise recognizable\n"
                "- Currency Error: amounts, debit/credit sides, rounding, or currency mismatch\n"
                "- missing entry: transaction exists in only one ledger, duplicate, or phantom entry\n\n"
                "Respond with JSON only: "
                '{"category": "<one of the three>", "reason": "<one sentence citing the description>"}'
            )

            for d in discrepancies:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": f"Classify this discrepancy:\n{_build_agent_prompt(d)}",
                        },
                    ],
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or "{}"
                parsed = json.loads(content)
                category = parsed.get("category", "")
                if category not in AI_CATEGORIES:
                    category = _rule_based_category(d)
                results.append(
                    {
                        **d,
                        "ai_category": category,
                        "ai_reason": parsed.get("reason", ""),
                        "ai_source": "openai",
                    }
                )
            return results
        except Exception as exc:
            print(f"Warning: OpenAI agent failed ({exc}). Using rule-based fallback.\n")

    for d in discrepancies:
        category, reason = _rule_based_classify(d)
        results.append(
            {
                **d,
                "ai_category": category,
                "ai_reason": reason,
                "ai_source": "rule_based_agent",
            }
        )
    return results


def _rule_based_category(d: dict) -> str:
    category, _ = _rule_based_classify(d)
    return category


def _rule_based_classify(d: dict) -> tuple[str, str]:
    """Local agent fallback using description and diff patterns."""
    issue = d["issue"]
    desc = (d.get("description") or "").lower()
    diffs = d.get("diffs") or []

    if issue in ("missing_in_sub", "extra_in_sub", "duplicate_in_sub"):
        return (
            "missing entry",
            f"'{d.get('description', '')}' appears absent or duplicated across ledgers.",
        )

    diff_fields = {x["field"] for x in diffs}

    if "post_date" in diff_fields:
        return (
            "Timing difference",
            f"Description '{d.get('description', '')}' suggests a posting-date timing mismatch.",
        )

    if "currency" in diff_fields:
        return (
            "Currency Error",
            f"Description '{d.get('description', '')}' involves a currency field mismatch.",
        )

    amount_fields = diff_fields & {"debit", "credit"}
    if amount_fields:
        for field in amount_fields:
            hq_amt = _normalize_amount(next((x["hq"] for x in diffs if x["field"] == field), ""))
            sub_amt = _normalize_amount(next((x["sub"] for x in diffs if x["field"] == field), ""))
            if hq_amt is not None and sub_amt is not None:
                if abs(hq_amt - sub_amt) < 1.0 and ("utility" in desc or "rounding" in desc):
                    return (
                        "Currency Error",
                        f"Penny-level amount difference on '{d.get('description', '')}'.",
                    )
        if "debit" in diff_fields and "credit" in diff_fields:
            return (
                "Currency Error",
                f"Debit/credit sign flip detected for '{d.get('description', '')}'.",
            )
        return (
            "Currency Error",
            f"Amount mismatch on '{d.get('description', '')}' ({', '.join(amount_fields)}).",
        )

    if "account_code" in diff_fields:
        return (
            "missing entry",
            f"Account coding error on '{d.get('description', '')}' may indicate mis-posted entry.",
        )

    if "description" in diff_fields and len(diff_fields) == 1:
        return (
            "missing entry",
            f"Memo variance only on '{d.get('description', '')}'; verify entry identity.",
        )

    return (
        "Currency Error",
        f"Unclassified variance on '{d.get('description', '')}'; review amounts and accounts.",
    )


def _exposure_usd(d: dict, variance_usd: float) -> float:
    """Materiality basis for risk: variance amount or full line exposure."""
    if variance_usd > 0:
        return variance_usd
    return _row_amount(d.get("hq") or d.get("sub"))


def _risk_from_exposure(exposure_usd: float) -> str:
    if exposure_usd >= 5000:
        return "High"
    if exposure_usd >= 500:
        return "Medium"
    return "Low"


def _rule_based_risk_action(d: dict, variance_usd: float) -> tuple[str, str]:
    """Fallback risk rating and finance-team action when LLM is unavailable."""
    category = d.get("ai_category", "")
    issue = d.get("issue", "")
    desc = d.get("description", "")
    exposure = _exposure_usd(d, variance_usd)
    risk = _risk_from_exposure(exposure)

    if issue in ("missing_in_sub", "extra_in_sub", "duplicate_in_sub"):
        if issue == "missing_in_sub":
            action = (
                f"Request subsidiary posting support for '{desc}' and re-post the "
                f"${variance_usd:,.2f} entry before close."
            )
        else:
            action = (
                f"Investigate duplicate or phantom entry for '{desc}' and reverse "
                f"if not supported by source documents."
            )
        return risk, action

    if category == "Timing difference":
        return (
            risk,
            f"Confirm cut-off: reclassify '{desc}' (${exposure:,.2f} exposure) to the "
            f"correct period or document as an intercompany timing item for month-end.",
        )

    if category == "Currency Error":
        return (
            risk,
            f"Reconcile amount for '{desc}': verify exchange rates, rounding, and "
            f"correct the ${variance_usd:,.2f} variance between HQ and subsidiary.",
        )

    return (
        risk,
        f"Review supporting documentation for '{desc}' and clear the "
        f"${variance_usd:,.2f} open variance.",
    )


def analyze_discrepancies_with_agent(
    discrepancies: list[dict], model: str = "gpt-4o-mini"
) -> list[dict]:
    """
    AI agent pass: risk rating (High/Medium/Low) and suggested finance action per item.
    """
    enriched: list[dict] = []
    for d in discrepancies:
        variance = compute_discrepancy_variance(d)
        risk, action = _rule_based_risk_action(d, variance)
        enriched.append(
            {
                **d,
                "variance_usd": variance,
                "risk_rating": risk,
                "suggested_action": action,
                "analysis_source": "rule_based_agent",
            }
        )

    if not enriched:
        return enriched

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return enriched

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        payload = []
        for d in enriched:
            payload.append(
                {
                    "txn_id": d["txn_id"],
                    "description": d.get("description", ""),
                    "issue": d.get("issue", ""),
                    "ai_category": d.get("ai_category", ""),
                    "ai_reason": d.get("ai_reason", ""),
                    "variance_usd": d["variance_usd"],
                    "field_diffs": d.get("diffs", []),
                }
            )

        system_prompt = (
            "You are a month-end finance reconciliation AI agent. "
            "For each discrepancy, assign:\n"
            "- risk_rating: exactly one of High, Medium, Low (materiality + control risk)\n"
            "- suggested_action: one concrete sentence for the finance team "
            "(e.g. contact bank, verify FX rate, request missing sub-ledger posting)\n\n"
            "Respond with JSON only: "
            '{"items": [{"txn_id": "...", "risk_rating": "High|Medium|Low", '
            '"suggested_action": "..."}]}'
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, indent=2)},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        by_id = {item["txn_id"]: item for item in parsed.get("items", []) if item.get("txn_id")}

        for d in enriched:
            ai_item = by_id.get(d["txn_id"])
            if not ai_item:
                continue
            risk = ai_item.get("risk_rating", "")
            if risk in RISK_LEVELS:
                d["risk_rating"] = risk
            action = (ai_item.get("suggested_action") or "").strip()
            if action:
                d["suggested_action"] = action
            d["analysis_source"] = "openai"
    except Exception as exc:
        print(f"Warning: AI month-end analysis failed ({exc}). Using rule-based fallback.\n")

    return enriched


def write_month_end_summary(
    discrepancies: list[dict],
    output_path: Path = MONTH_END_SUMMARY_PATH,
    hq_rows: int = 0,
    sub_rows: int = 0,
) -> Path:
    """Write Month_End_Summary.txt for the finance team."""
    total_variance = sum(d.get("variance_usd", 0.0) for d in discrepancies)
    lines = [
        "MONTH-END RECONCILIATION SUMMARY",
        "Generated by Self-Healing Reconciler (AI Agent Analysis)",
        "=" * 70,
        "",
        f"HQ ledger rows: {hq_rows}",
        f"Subsidiary ledger rows: {sub_rows}",
        f"Discrepancies analyzed: {len(discrepancies)}",
        "",
        "TOTAL VARIANCE VALUE",
        "-" * 70,
        f"  ${total_variance:,.2f} USD  (sum of monetary exposure across all items)",
        "",
    ]

    if not discrepancies:
        lines.append("No discrepancies found. Ledgers are reconciled for month-end close.")
    else:
        lines.extend(["DISCREPANCY DETAIL", "-" * 70, ""])
        for d in discrepancies:
            variance = d.get("variance_usd", 0.0)
            lines.extend(
                [
                    f"Transaction: {d['txn_id']}",
                    f"  Description:     {d.get('description', '')}",
                    f"  AI category:     {d.get('ai_category', 'n/a')}",
                    f"  Variance (USD):  ${variance:,.2f}",
                    f"  Risk rating:     {d.get('risk_rating', 'n/a')}",
                    f"  Suggested action: {d.get('suggested_action', 'n/a')}",
                    f"  (Analysis via {d.get('analysis_source', 'n/a')})",
                    "",
                ]
            )

        by_risk = {r: sum(1 for d in discrepancies if d.get("risk_rating") == r) for r in RISK_LEVELS}
        lines.extend(
            [
                "RISK SUMMARY",
                "-" * 70,
                f"  High:   {by_risk.get('High', 0)}",
                f"  Medium: {by_risk.get('Medium', 0)}",
                f"  Low:    {by_risk.get('Low', 0)}",
                "",
                "RECOMMENDED NEXT STEPS",
                "-" * 70,
                "  1. Clear all High-risk items before filing.",
                "  2. Obtain subsidiary support for missing or timing items.",
                "  3. Post correcting journals for confirmed amount variances.",
                "",
            ]
        )

    lines.append("=" * 70)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def reconcile(hq_path: Path, sub_path: Path, model: str = "gpt-4o-mini") -> dict:
    hq = load_ledger(hq_path)
    sub = load_ledger(sub_path)
    discrepancies = find_mismatches(hq, sub)
    classified = classify_with_ai_agent(discrepancies, model=model)
    analyzed = analyze_discrepancies_with_agent(classified, model=model)
    return {"discrepancies": analyzed, "hq_rows": len(hq), "sub_rows": len(sub)}


def print_report(result: dict) -> None:
    items = result["discrepancies"]

    print("=" * 70)
    print("SELF-HEALING RECONCILER — PANDAS MISMATCH + AI CLASSIFICATION")
    print("=" * 70)
    print(f"\nLedger rows: HQ={result['hq_rows']}  Sub={result['sub_rows']}")
    print(f"Discrepancies found: {len(items)}")

    if not items:
        print("\nNo discrepancies found. Ledgers are reconciled.\n")
        return

    by_category: dict[str, int] = {c: 0 for c in AI_CATEGORIES}
    for item in items:
        cat = item.get("ai_category", "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1

    print("\nAI category summary:")
    for cat in AI_CATEGORIES:
        print(f"  {cat}: {by_category.get(cat, 0)}")

    print("\n" + "-" * 70)
    for item in items:
        print(f"\n{item['txn_id']}  [{item['issue']}]")
        print(f"  Description: {item.get('description', '')}")
        print(f"  AI category: {item.get('ai_category')}  (via {item.get('ai_source')})")
        print(f"  AI reason:   {item.get('ai_reason')}")
        if item.get("diffs"):
            print("  Field diffs:")
            for d in item["diffs"]:
                print(f"    {d['field']}: HQ={d['hq']!r}  Sub={d['sub']!r}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pandas ledger reconcile + AI discrepancy classification."
    )
    parser.add_argument("--hq", type=Path, default=DATA_DIR / "HQ_Ledger.csv")
    parser.add_argument("--sub", type=Path, default=DATA_DIR / "Sub_Ledger.csv")
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        help="OpenAI model when OPENAI_API_KEY is set",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=MONTH_END_SUMMARY_PATH,
        help="Path for Month_End_Summary.txt (default: project root)",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Skip writing Month_End_Summary.txt",
    )
    args = parser.parse_args()

    hq, sub, discrepancies = compare_ledgers(args.hq, args.sub)
    classified = classify_with_ai_agent(discrepancies, model=args.model)
    analyzed = analyze_discrepancies_with_agent(classified, model=args.model)
    result = {"discrepancies": analyzed, "hq_rows": len(hq), "sub_rows": len(sub)}
    print_report(result)

    if not args.no_summary:
        summary_path = write_month_end_summary(
            analyzed,
            output_path=args.summary,
            hq_rows=len(hq),
            sub_rows=len(sub),
        )
        total = sum(d.get("variance_usd", 0.0) for d in analyzed)
        print(f"Month-end summary written: {summary_path}")
        print(f"Total variance value: ${total:,.2f} USD\n")


if __name__ == "__main__":
    main()
