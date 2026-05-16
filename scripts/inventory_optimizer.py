import pandas as pd
import os

# Automatically find the absolute path of your project folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, 'data', 'inventory_data.csv')

try:
    # Load the data safely
    df = pd.read_csv(DATA_PATH)
except FileNotFoundError:
    print(f"\n❌ Error: Could not find the file at {DATA_PATH}")
    print("Please check that 'inventory_data.csv' is inside your 'data' folder!\n")
    exit()

def analyze_waste_risk(row):
    expected_sales = row['Days_to_Expiry'] * row['Avg_Daily_Demand']
    potential_waste_qty = max(0, row['Current_Stock'] - expected_sales)
    financial_loss = potential_waste_qty * row['Unit_Cost']
    return pd.Series([potential_waste_qty, financial_loss])

# Process risks
df[['Waste_Qty', 'Financial_Loss_Risk']] = df.apply(analyze_waste_risk, axis=1)
high_risk = df[df['Financial_Loss_Risk'] > 0].sort_values(by='Financial_Loss_Risk', ascending=False)

# Print operational alert report
print("\n--- INVENTORY WASTE & ESG RISK REPORT ---")
if high_risk.empty:
    print("Zero waste risk detected. Working capital is optimized!")
else:
    for _, row in high_risk.iterrows():
        print(f"ALERT: {row['SKU_Name']} has ${row['Financial_Loss_Risk']:.2f} at risk of spoilage.")
        print(f"Action: Allocate {int(row['Waste_Qty'])} units to Too Good To Go 'Surprise Bags'.\n")

print(f"TOTAL CAPITAL AT RISK: ${df['Financial_Loss_Risk'].sum():.2f}\n")