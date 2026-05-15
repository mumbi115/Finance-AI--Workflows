import pandas as pd
import os

def load_spending() -> pd.DataFrame:
    # 1. Load the historical data
    data_path = os.path.join('data', 'historical_spending.csv')
    df = pd.read_csv(data_path)
    df["Month"] = pd.to_datetime(df["Month"], format="%Y-%m")
    return df


def analyze_variance(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # 2. Calculate the Variance (Actual vs Budget)
    df['Variance'] = df['Actual_Amount'] - df['Budgeted_Amount']
    df['Variance_%'] = (df['Variance'] / df['Budgeted_Amount']) * 100
    df["Over_Budget"] = df["Variance"] > 0
    return df


def summarize_by_category(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("Category", as_index=False)
        .agg(
            Months=("Month", "count"),
            Total_Budgeted=("Budgeted_Amount", "sum"),
            Total_Actual=("Actual_Amount", "sum"),
            Over_Budget_Months=("Over_Budget", "sum"),
            Avg_Variance_Pct=("Variance_%", "mean"),
        )
        .assign(
            Total_Variance=lambda x: x["Total_Actual"] - x["Total_Budgeted"],
        )
    )


def flag_overspends(df: pd.DataFrame, categories: list[str] | None = None) -> pd.DataFrame:
    mask = df["Over_Budget"]
    if categories:
        mask &= df["Category"].isin(categories)
    return df.loc[mask, ["Month", "Category", "Budgeted_Amount", "Actual_Amount", "Variance", "Variance_%"]]


def forecast_next_month(df: pd.DataFrame) -> pd.DataFrame:
    # 3. Logic: Predict next month's spending based on the last 3 months
    # We group by Category and take the mean of the actual spend
    forecast = df.groupby('Category')['Actual_Amount'].tail(3).groupby(df['Category']).mean().reset_index()
    forecast.columns = ['Category', 'Predicted_Next_Month_Spend']
    return forecast


def main() -> None:
    print("📊 Analyzing Historical Spending Trends...")
    df = load_spending()
    df = analyze_variance(df)

    print("=== Category Summary ===")
    print(summarize_by_category(df).to_string(index=False))

    print("\n=== Marketing & Software Over-Spends ===")
    overspends = flag_overspends(df, categories=["Marketing", "Software"])
    print(overspends.to_string(index=False))

    forecast = forecast_next_month(df)

    # 4. Identify Risks (Categories consistently over budget)
    risky_categories = df[df['Variance'] > 0].groupby('Category')['Variance'].count()
    print("\n--- 🔮 NEXT MONTH BUDGET FORECAST ---")
    print(forecast.to_string(index=False))
    print("\n--- ⚠️ RISK ALERT ---")
    for cat, count in risky_categories.items():
        if count > 12:  # Over budget for more than half the time
            print(f"CRITICAL: {cat} has exceeded budget {count} times in 24 months. Action required.")

    # 5. Save the Forecast to a new CSV for the team
    output_path = os.path.join('data', 'budget_forecast_report.csv')
    forecast.to_csv(output_path, index=False)
    print(f"\n✅ Forecast exported to: {output_path}")


if __name__ == "__main__":
    main()
