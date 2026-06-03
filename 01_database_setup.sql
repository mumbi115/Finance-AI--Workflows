DROP TABLE IF EXISTS Central_Finance_Staging;

CREATE TABLE Central_Finance_Staging (
    Transaction_ID VARCHAR(100),
    Posting_Date VARCHAR(50),
    Account_Code VARCHAR(50),
    Account_Name VARCHAR(150),
    Partner_Entity VARCHAR(150),
    Debit DECIMAL(18, 2),   
    Credit DECIMAL(18, 2),  
    Currency VARCHAR(50),
    Source_Subsidiary VARCHAR(50)
);