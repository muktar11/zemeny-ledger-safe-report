"""
Ledger Services

Business logic for ledger operations with transactional guarantees.
"""

from django.db import transaction
from decimal import Decimal
import uuid
from events.models import Event
from read_models.models import AccountBalance


class LedgerService:
    """Service for ledger operations."""
    
    @staticmethod
    @transaction.atomic
    def create_transaction(transaction_id, description, entries_data, metadata=None):
        """
        Create a double-entry transaction atomically.
        
        This method ensures:
        1. Transaction is created with exactly 2 entries
        2. Entries balance to zero
        3. Event is emitted
        4. Read models are updated
        
        Returns:
            Transaction instance
        """
        from ledger.models import Transaction
        
        # Create transaction with entries
        trans = Transaction.create_transaction(
            transaction_id=transaction_id,
            description=description,
            entries_data=entries_data,
            metadata=metadata
        )
        
        # Emit event (within same transaction)
        event_id = f"ledger_txn_{transaction_id}_{uuid.uuid4()}"
        Event.create_event(
            event_id=event_id,
            event_type='LEDGER_TRANSACTION_CREATED',
            aggregate_id=str(trans.id),
            aggregate_type='Transaction',
            event_data={
                'transaction_id': transaction_id,
                'description': description,
                'entries': [
                    {
                        'account_id': str(entry.account_id),
                        'amount': str(entry.amount),
                        'entry_type': entry.entry_type,
                    }
                    for entry in trans.entries.all()
                ],
                'metadata': metadata or {},
            }
        )
        
        # Update read models (within same transaction)
        for entry in trans.entries.all():
            AccountBalance.rebuild_for_account(entry.account)
        
        return trans
    
    @staticmethod
    def get_account_balance(account):
        """Get current balance for an account."""
        balance, _ = AccountBalance.objects.get_or_create(
            account=account,
            defaults={'balance': Decimal('0.00')}
        )
        return balance.balance




