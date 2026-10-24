DROP TABLE IF EXISTS ledger_entries CASCADE;
DROP TABLE IF EXISTS accounts CASCADE;

CREATE TABLE accounts (
    account_id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) UNIQUE NOT NULL,
    balance NUMERIC(15, 4) NOT NULL DEFAULT 0.0000 CHECK (balance >= 0.0000),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ledger_entries (
    entry_id SERIAL PRIMARY KEY,
    account_id INT NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
    amount NUMERIC(15, 4) NOT NULL,
    entry_type VARCHAR(50) NOT NULL,
    
    -- Idempotency key for THIS exact request (Dedupes retries)
    idempotency_key UUID,
    
    -- Relational link pointing to an earlier hold, order, or checkout
    reference_id UUID,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ledger_entries_account_id 
ON ledger_entries(account_id);

CREATE INDEX idx_ledger_entries_reference_id 
ON ledger_entries(reference_id);

-- Enforce idempotency ONLY on the request key
CREATE UNIQUE INDEX idx_ledger_entries_idempotency_key_unique 
ON ledger_entries(idempotency_key) 
WHERE idempotency_key IS NOT NULL;