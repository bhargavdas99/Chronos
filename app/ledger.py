from decimal import Decimal
import uuid
import asyncpg

async def process_transaction(
    pool: asyncpg.Pool, 
    user_id: str, 
    amount: Decimal, 
    entry_type: str, 
    reference_id: str = None
) -> dict:
    """
    Executes a strict financial transaction using row-level locking (SELECT FOR UPDATE).
    Guarantees no double-spending and zero balance drops below 0.0000.
    """
    async with pool.acquire() as conn:
        # Acquire an explicit transaction block
        async with conn.transaction():
            
            # 1. Fetch account and LOCK THE ROW exclusively.
            # NOTE: this is the Two Phase Locking to solve the double booking problem
            # Concurrent transactions targeting this user_id will BLOCK HERE
            # until this transaction commits or rolls back.
            account = await conn.fetchrow(
                """
                SELECT account_id, balance 
                FROM accounts 
                WHERE user_id = $1 
                FOR UPDATE
                """,
                user_id
            )
            
            if not account:
                raise ValueError(f"Account for user '{user_id}' not found.")
            
            current_balance = account["balance"]
            account_id = account["account_id"]
            
            # 2. Calculate new balance
            if entry_type in ('WITHDRAWAL', 'RESERVATION_HOLD'):
                if current_balance < amount:
                    raise ValueError(f"Insufficient funds. Current balance: {current_balance}, Requested: {amount}")
                new_balance = current_balance - amount
                ledger_amount = -amount
            elif entry_type in ('DEPOSIT', 'RESERVATION_COMMIT'):
                new_balance = current_balance + amount
                ledger_amount = amount
            else:
                raise ValueError(f"Invalid entry type: {entry_type}")
            
            # 3. Update account balance
            await conn.execute(
                """
                UPDATE accounts 
                SET balance = $1 
                WHERE account_id = $2
                """,
                new_balance, account_id
            )
            
            # 4. Insert immutable audit trail entry
            if isinstance(reference_id, str):
                ref_uuid = uuid.UUID(reference_id)
            elif isinstance(reference_id, uuid.UUID):
                ref_uuid = reference_id
            else:
                ref_uuid = None

            entry_id = await conn.fetchval(
                """
                INSERT INTO ledger_entries (account_id, amount, entry_type, reference_id)
                VALUES ($1, $2, $3, $4)
                RETURNING entry_id
                """,
                account_id, ledger_amount, entry_type, ref_uuid
            )
            
            return {
                "account_id": str(account_id),
                "entry_id": str(entry_id),
                "previous_balance": float(current_balance),
                "new_balance": float(new_balance),
                "amount_processed": float(amount),
                "entry_type": entry_type
            }