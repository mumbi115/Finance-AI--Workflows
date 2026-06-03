SELECT 
    Account_Code,
    Account_Name,
    Partner_Entity,
    SUM(Debit) AS Group_Total_Debits,
    SUM(Credit) AS Group_Total_Credits,
    (SUM(Debit) - SUM(Credit)) AS Group_Net_Position
FROM Central_Finance_Staging
GROUP BY Account_Code, Account_Name, Partner_Entity;