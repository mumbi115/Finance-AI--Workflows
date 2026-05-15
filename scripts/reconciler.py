"""
Project 1: The Self-Healing Reconciler

Uses Pandas to detect HQ vs Sub ledger mismatches, then an AI agent
classifies each discrepancy as Timing difference, Currency Error, or missing entry.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

COMPARE_FIELDS = ("post_date", "account_code", "description", "debit", "credit", "currency")
AI_CATEGORIES = ("Timing difference", "Currency Error", "missing entry")


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


def reconcile(hq_path: Path, sub_path: Path) -> dict:
    hq = load_ledger(hq_path)
    sub = load_ledger(sub_path)
    discrepancies = find_mismatches(hq, sub)
    classified = classify_with_ai_agent(discrepancies)
    return {"discrepancies": classified, "hq_rows": len(hq), "sub_rows": len(sub)}


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
    args = parser.parse_args()

    hq = load_ledger(args.hq)
    sub = load_ledger(args.sub)
    discrepancies = find_mismatches(hq, sub)
    classified = classify_with_ai_agent(discrepancies, model=args.model)
    print_report({"discrepancies": classified, "hq_rows": len(hq), "sub_rows": len(sub)})


if __name__ == "__main__":
    main()
