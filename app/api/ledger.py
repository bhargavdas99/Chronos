from decimal import Decimal
import uuid
import asyncpg


async def process_transaction(
    pool: asyncpg.Pool,
    user_id: str,
    amount: Decimal,
    entry_type: str,
    idempotency_key: uuid.UUID | str = None,
    reference_id: uuid.UUID | str = None,
) -> dict:
    """
    - Executes a strict financial transaction using row-level locking (SELECT FOR UPDATE).
    - Guarantees no double-spending and zero balance drops below 0.0000.
    - Includes database-level idempotency fallback when caching fails.
    """
    entry_str = entry_type.value if hasattr(entry_type, "value") else str(entry_type)

    if entry_str == "RESERVATION_COMMIT" and not reference_id:
        raise ValueError(
            "RESERVATION_COMMIT requires a valid reference_id linking to a hold."
        )

    # Normalize UUIDs safely
    idem_uuid = uuid.UUID(str(idempotency_key)) if idempotency_key else None
    ref_uuid = uuid.UUID(str(reference_id)) if reference_id else None

    async with pool.acquire() as conn:
        async with conn.transaction():
            # 0. IDEMPOTENCY CHECK: Dedupes THIS exact execution request
            if idem_uuid is not None:
                existing_entry = await conn.fetchrow(
                    """
                    SELECT e.entry_id, e.account_id, e.amount, e.entry_type, a.balance
                    FROM ledger_entries e
                    JOIN accounts a ON e.account_id = a.account_id
                    WHERE e.idempotency_key = $1
                    """,
                    idem_uuid,
                )

                if existing_entry:
                    return {
                        "account_id": str(existing_entry["account_id"]),
                        "entry_id": str(existing_entry["entry_id"]),
                        "previous_balance": float(existing_entry["balance"]),
                        "new_balance": float(existing_entry["balance"]),
                        "amount_processed": float(abs(existing_entry["amount"])),
                        "entry_type": existing_entry["entry_type"],
                        "idempotency_replayed": True,
                    }

            # 1. Fetch account and acquire exclusive row lock
            account = await conn.fetchrow(
                """
                SELECT account_id, balance 
                FROM accounts 
                WHERE user_id = $1 
                FOR UPDATE
                """,
                user_id,
            )

            if not account:
                raise ValueError(f"Account for user '{user_id}' not found.")

            current_balance = account["balance"]
            account_id = account["account_id"]

            # 2. Balance rules and state transitions
            if entry_str in ("WITHDRAWAL", "RESERVATION_HOLD"):
                if current_balance < amount:
                    raise ValueError(
                        f"Insufficient funds. Current balance: {current_balance}, Requested: {amount}"
                    )
                new_balance = current_balance - amount
                ledger_amount = -amount

            elif entry_str == "DEPOSIT":
                new_balance = current_balance + amount
                ledger_amount = amount

            elif entry_str == "RESERVATION_COMMIT":
                # Verify that the linked hold actually exists in the ledger
                hold_entry = await conn.fetchrow(
                    """
                    SELECT entry_id FROM ledger_entries 
                    WHERE account_id = $1 AND reference_id = $2 AND entry_type = 'RESERVATION_HOLD'
                    """,
                    account_id,
                    ref_uuid,
                )
                if not hold_entry:
                    raise ValueError(
                        f"No matching RESERVATION_HOLD found for reference_id '{ref_uuid}'"
                    )

                # Funds were already subtracted during RESERVATION_HOLD
                new_balance = current_balance
                ledger_amount = -amount

            else:
                raise ValueError(f"Invalid entry type: {entry_str}")

            # 3. Update account balance only if balance shifted
            if new_balance != current_balance:
                await conn.execute(
                    """
                    UPDATE accounts 
                    SET balance = $1 
                    WHERE account_id = $2
                    """,
                    new_balance,
                    account_id,
                )

            # 4. Insert ledger entry (enforced by UNIQUE INDEX on idempotency_key)
            entry_id = await conn.fetchval(
                """
                INSERT INTO ledger_entries (account_id, amount, entry_type, reference_id, idempotency_key)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING entry_id
                """,
                account_id,
                ledger_amount,
                entry_str,
                ref_uuid,
                idem_uuid,
            )

            return {
                "account_id": str(account_id),
                "entry_id": str(entry_id),
                "previous_balance": float(current_balance),
                "new_balance": float(new_balance),
                "amount_processed": float(amount),
                "entry_type": entry_str,
                "idempotency_replayed": False,
            }
