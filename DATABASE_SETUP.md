# Oracle Database Replication Guide

This document provides a step-by-step guide to replicate the database schema and data from the provided SQL scripts.

## Prerequisites

*   Access to an Oracle Database instance.
*   A SQL client (like SQL*Plus, SQL Developer, or DBeaver) connected to your Oracle instance.
*   The following SQL script files from this project:
    *   `script.sql`
    *   `inserts_products_books.sql`
    *   `invoice_data_insert.sql`
    *   `similarity_search.sql`

---

## Step 1: Create Tables and Indexes

This step creates the main tables (`products`, `INVOICE`, `ITEM_INVOICE`) and the necessary indexes.

Execute the contents of `database_sql_scripts/script.sql`:

```sql
CREATE TABLE products (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    CODE VARCHAR2(50),
    description VARCHAR2(4000)
);

CREATE INDEX idx_text_description ON products(description)
INDEXTYPE IS CTXSYS.CONTEXT;

-- Table main: INVOICE
CREATE TABLE INVOICE (
    NO_INVOICE         VARCHAR2(20) PRIMARY KEY,
    CODE_CUSTOMER    VARCHAR2(20) NOT NULL,
    NAME_CUSTOMER      VARCHAR2(100),
    VALUE_TOTAL       NUMBER(15, 2),
    DATE_PRINT        DATE,
    CITY            VARCHAR2(100),
    STATE            VARCHAR2(2)   -- Ex: SP, RJ, MG
);

-- Table of itens: ITEM_INVOICE
CREATE TABLE ITEM_INVOICE (
    NO_INVOICE         VARCHAR2(20) NOT NULL,
    NO_ITEM       NUMBER(5) NOT NULL,
    CODE_EAN        VARCHAR2(20),
    DESCRIPTION_PRODUCT VARCHAR2(200),
    VALUE_UNITARY    NUMBER(12, 4),
    QUANTITY        NUMBER(10, 2),
    VALUE_TOTAL       NUMBER(15, 2),
    VALUE_TAXES    NUMBER(15, 2),
    
    -- Primary key
    CONSTRAINT PK_ITEM_INVOICE PRIMARY KEY (NO_INVOICE, NO_ITEM),

    -- Foreign key for INVOICE
    CONSTRAINT FK_ITEM_INVOICE FOREIGN KEY (NO_INVOICE)
        REFERENCES INVOICE (NO_INVOICE)
        ON DELETE CASCADE
);

-- Index to accelerate searches for invoice item
CREATE INDEX IDX_ITEM_INVOICE_EAN ON ITEM_INVOICE (CODE_EAN);
```

---

## Step 2: Populate the `products` Table

This step inserts the book product data into the `products` table.

Execute the contents of `database_sql_scripts/inserts_products_books.sql`:

```sql
INSERT INTO products (code, description) VALUES ('LIV1001', '1984 - Annotated Edition - George Orwell');
INSERT INTO products (code, description) VALUES ('LIV1002', 'The Lord of the Rings - J.R.R. Tolkien');
INSERT INTO products (code, description) VALUES ('LIV1003', 'The Old Man and the Sea - Ernest Hemingway');
INSERT INTO products (code, description) VALUES ('LIV1004', 'To Kill a Mockingbird - Harper Lee');
... and so on for all entries in the file.
```
*(Note: The full list of INSERT statements is in the `inserts_products_books.sql` file.)*

---

## Step 3: Populate Invoice Data

This step inserts the invoice headers and their corresponding line items.

Execute the contents of `database_sql_scripts/invoice_data_insert.sql`:

```sql
INSERT INTO INVOICE (NO_INVOICE, CODE_CUSTOMER, NAME_CUSTOMER, VALUE_TOTAL, DATE_PRINT, CITY, STATE) VALUES ('NF000001', 'CL00001', 'Customer 1', 0, TO_DATE('2025-01-26', 'YYYY-MM-DD'), 'SÃ£o Paulo', 'SP');
INSERT INTO ITEM_INVOICE (NO_INVOICE, NO_ITEM, CODE_EAN, DESCRIPTION_PRODUCT, VALUE_UNITARY, QUANTITY, VALUE_TOTAL, VALUE_TAXES) VALUES ('NF000001', 1, 'LIV1089', 'Mockingjay - Suzanne Collins', 138.21, 4, 552.84, 82.93);
INSERT INTO ITEM_INVOICE (NO_INVOICE, NO_ITEM, CODE_EAN, DESCRIPTION_PRODUCT, VALUE_UNITARY, QUANTITY, VALUE_TOTAL, VALUE_TAXES) VALUES ('NF000001', 2, 'LIV1073', 'The Way of Kings - Brandon Sanderson', 77.45, 3, 232.35, 34.85);
INSERT INTO ITEM_INVOICE (NO_INVOICE, NO_ITEM, CODE_EAN, DESCRIPTION_PRODUCT, VALUE_UNITARY, QUANTITY, VALUE_TOTAL, VALUE_TAXES) VALUES ('NF000001', 3, 'LIV1078', 'Ready Player One - Ernest Cline', 142.33, 2, 284.66, 42.7);
INSERT INTO ITEM_INVOICE (NO_INVOICE, NO_ITEM, CODE_EAN, DESCRIPTION_PRODUCT, VALUE_UNITARY, QUANTITY, VALUE_TOTAL, VALUE_TAXES) VALUES ('NF000001', 4, 'LIV1005', 'Pride and Prejudice - Jane Austen', 117.79, 1, 117.79, 17.67);
INSERT INTO ITEM_INVOICE (NO_INVOICE, NO_ITEM, CODE_EAN, DESCRIPTION_PRODUCT, VALUE_UNITARY, QUANTITY, VALUE_TOTAL, VALUE_TAXES) VALUES ('NF000001', 5, 'LIV1062', 'Malibu Rising - Taylor Jenkins Reid', 131.24, 1, 131.24, 19.69);
UPDATE INVOICE SET VALUE_TOTAL = 1318.88 WHERE NO_INVOICE = 'NF000001';

... and so on for all entries in the file.
```
*(Note: The full list of INSERT and UPDATE statements is in the `invoice_data_insert.sql` file.)*

---

## Step 4: Create Advanced Search Functionality

This final step creates the custom PL/SQL types and the function used for performing advanced, phonetic-based searches on the `products` table.

Execute the contents of `database_sql_scripts/similarity_search.sql`:

```sql
-- ============================================================
-- Oracle Advanced Search Function with Phonetic Matching
-- ============================================================

-- DROP TYPES (if they exist) - with error handling
BEGIN
    EXECUTE IMMEDIATE 'DROP TYPE product_result_tab FORCE';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -4043 THEN  -- ORA-04043: object does not exist
            RAISE;
        END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP TYPE product_result FORCE';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -4043 THEN
            RAISE;
        END IF;
END;
/

-- Create a result type for the function
CREATE TYPE product_result AS OBJECT (
    code VARCHAR2(50),
    description VARCHAR2(4000),
    similarity NUMBER
);
/

CREATE TYPE product_result_tab AS TABLE OF product_result;
/

-- Advanced search function with phonetic and keyword matching
CREATE OR REPLACE FUNCTION fn_advanced_search(p_termos IN VARCHAR2)
    RETURN product_result_tab PIPELINED
AS
    v_termos SYS.ODCIVARCHAR2LIST := SYS.ODCIVARCHAR2LIST();
    v_token VARCHAR2(1000);
    v_description VARCHAR2(4000);
    v_score NUMBER;
    v_dummy NUMBER;
BEGIN
    -- Split search terms
    FOR i IN 1..REGEXP_COUNT(p_termos, '\S+') LOOP
        v_termos.EXTEND;
        v_termos(i) := LOWER(REGEXP_SUBSTR(p_termos, '\S+', 1, i));
    END LOOP;

    -- Loop through products
    FOR prod IN (SELECT code, description FROM products) LOOP
        v_description := LOWER(prod.description);
        v_score := 0;

        -- Evaluate each search term
        FOR i IN 1..v_termos.COUNT LOOP
            v_token := v_termos(i);

            -- 3 points if exact match found
            IF v_description LIKE '%' || v_token || '%' THEN
                v_score := v_score + 3;
            ELSE
                -- 2 points if phonetically similar
                BEGIN
                    SELECT 1 INTO v_dummy FROM dual
                    WHERE SOUNDEX(v_token) IN (
                        SELECT SOUNDEX(REGEXP_SUBSTR(v_description, '\w+', 1, LEVEL))
                        FROM dual
                        CONNECT BY LEVEL <= REGEXP_COUNT(v_description, '\w+')
                    );
                    v_score := v_score + 2;
                EXCEPTION
                    WHEN NO_DATA_FOUND THEN NULL;
                END;

                -- 1 point if similar by edit distance
                BEGIN
                    SELECT 1 INTO v_dummy FROM dual
                    WHERE EXISTS (
                        SELECT 1
                        FROM (
                            SELECT REGEXP_SUBSTR(v_description, '\w+', 1, LEVEL) AS palavra
                            FROM dual
                            CONNECT BY LEVEL <= REGEXP_COUNT(v_description, '\w+')
                        )
                        WHERE UTL_MATCH.EDIT_DISTANCE(palavra, v_token) <= 2
                    );
                    v_score := v_score + 1;
                EXCEPTION
                    WHEN NO_DATA_FOUND THEN NULL;
                END;
            END IF;
        END LOOP;

        -- Only return if there's at least some match
        IF v_score > 0 THEN
            PIPE ROW(product_result(prod.code, prod.description, v_score));
        END IF;
    END LOOP;

    RETURN;
END fn_advanced_search;
/

-- Grant execution to PUBLIC if needed
BEGIN
    EXECUTE IMMEDIATE 'GRANT EXECUTE ON fn_advanced_search TO PUBLIC';
EXCEPTION
    WHEN OTHERS THEN
        NULL;  -- Ignore if grant fails
END;
/
```

---

After completing these steps, the database will be fully replicated.