SELECT 
    Source_Subsidiary,
    SUM(Debit) AS Total_Debits,
    SUM(Credit) AS Total_Credits,
    (SUM(Debit) - SUM(Credit)) AS Net_Imbalance
FROM Central_Finance_Staging
GROUP BY Source_Subsidiary;