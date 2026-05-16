# Project 3: Supply Chain & ESG Inventory Analysis

 **Report Date:**May 2026 

**Data Source:** Active SKU Shelf-Life Matrix & Rolling Daily Demand **Optimization Target:** Working Capital Reclamation & Food Waste Reduction

 --- ## 📊 At-Risk Capital Optimization Matrix The inventory optimization script analyzed perishable stock metrics against daily transactional velocity to isolate capital exposure before product expiry. | SKU Name | Current Stock | Days to Expiry | Avg. Daily Demand | Potential Waste Qty | Financial Loss Risk | Action Metric | | :--- | :---: | :---: | :---: | :---: | :---: | :--- | | **Organic_Avocados** | 50 | 2 | 15 | 20 | $30.00 | Allocate to 20 TGTG Surprise Bags 

 | **Sourdough_Bread** | 30 | 1 | 20 | 10 | $30.00 | Allocate to 10 TGTG Surprise Bags | 

| **Fresh_Milk_1L**| 100 | 4 | 20 | 20 | $24.00 | Allocate to 20 TGTG Surprise Bags | 

| **Rotisserie_Chicken**| 15 | 1 | 12 | 3 | $24.00 | Allocate to 3 TGTG Surprise Bags | 

| **Greek_Yogurt_Large**| 40 | 7 | 5 | 5 | $22.50 | Allocate to 5 TGTG Surprise Bags | 

| **Premium_Ribeye_Steak**| 10 | 3 | 2 | 4 | $60.00 | Staged for Immediate Markdown |

 | **TOTALS** | **290** | **-** | **-** | **82** | **$190.50** | **62** **Surprise Bags Created** 

| *Figures exported directly from* `inventory_data.csv` *(generated via* `scripts/inventory_optimizer.py`*).* --- ## 📉 Financial & Operational Vulnerability 

### **1. Working Capital Velocity Blockage**

- **Total Exposure:** **$190.50** in active inventory cost components are currently paced to expire prior to matching baseline consumer demand curves. 
- **Primary Risk Driver:**

 *Premium Ribeye Steak* represents the highest individual financial exposure ($60.00 at risk) due to a steep unit cost mismatched with a slow local sales velocity (2 units/day). 

### **2. ESG Environmental & Waste Impact**

 *Leaving these* *82 units** of food products unmitigated would result in direct margin write-offs to the P&L and negative environmental waste scores.  *By routing excess supply dynamically into secondary market applications, we successfully preserve the initial capital layout while eliminating commercial food waste footprints.*

 *--- ## 🛠 Strategic Margin Reclamation Plan 1.* 

*Automated Secondary Allocations:** Offload excess produce and bakery inventory directly via the *Too Good To Go* platform as "Surprise Bags" 12 to 24 hours prior to expiry. 

1. **Dynamic Markdown Triggering:** Implement a systematic, automated price reduction rule for high-value protein categories (like Steak) when shelf-life counts fall below a 48-hour threshold.

