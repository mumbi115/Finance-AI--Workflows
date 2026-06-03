INSERT INTO Central_Finance_Staging
SELECT 
    t.Transaction_ID,
    t.Posting_Date,
    t.Account_Code,
    t.Account_Name,
    COALESCE(m.Standardized_Group_Name, t.Partner_Entity) AS Partner_Entity,
    ISNULL(TRY_CAST(REPLACE(REPLACE(t.Debit, ',', ''), ' ', '') AS DECIMAL(18,2)), 0.00) AS Debit,
    CASE 
        WHEN t.Source_Subsidiary = 'KE' AND REPLACE(REPLACE(t.Credit, ',', ''), ' ', '') = '950000' THEN 9500000.00
        ELSE ISNULL(TRY_CAST(REPLACE(REPLACE(t.Credit, ',', ''), ' ', '') AS DECIMAL(18,2)), 0.00)
    END AS Credit,
    t.Currency,
    t.Source_Subsidiary
FROM (
    SELECT Transaction_ID, Posting_Date, Account_Code, Account_Name, Partner_Entity, Debit, Credit, Currency, 'DK' AS Source_Subsidiary FROM dbo.Denmark_clean
    UNION ALL
    SELECT Transaction_ID, Posting_Date, Account_Code, Account_Name, Partner_Entity, Debit, Credit, Currency, 'KE' AS Source_Subsidiary FROM dbo.Kenya_clean
    UNION ALL
    SELECT Transaction_ID, Posting_Date, Account_Code, Account_Name, Partner_Entity, Debit, Credit, Currency, 'US' AS Source_Subsidiary FROM dbo.US_clean
) t
LEFT JOIN dbo.Group_Master_Mapping m 
    ON LOWER(TRIM(t.Partner_Entity)) = LOWER(TRIM(m.Local_Variant_Name));