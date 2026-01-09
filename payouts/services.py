"""
Payout Services

Business logic for payout operations with exactly-once guarantees.
"""

from django.db import transaction
from decimal import Decimal
import uuid
from events.models import Event
from read_models.models import PayoutSummary
from ledger.services import LedgerService
from ledger.models import Account


class PayoutService:
    """Service for payout operations."""
    
    # Account IDs - in production, these would be configurable
    CASH_ACCOUNT_CODE = 'CASH_001'
    PAYOUT_LIABILITY_ACCOUNT_CODE = 'PAYOUT_LIABILITY_001'
    
    @staticmethod
    @transaction.atomic
    def initiate_payout(idempotency_key, amount, recipient_account, recipient_name=None, description=None, metadata=None):
        """
        Initiate a payout with exactly-once guarantees.
        
        This method:
        1. Creates or retrieves payout using idempotency_key
        2. Creates ledger entries atomically
        3. Emits events
        4. Updates read models
        
        Returns:
            Payout instance
        """
        from payouts.models import Payout, PayoutEvent
        
        # Get or create payout atomically
        payout, created = Payout.get_or_create_pending(
            idempotency_key=idempotency_key,
            defaults={
                'amount': Decimal(str(amount)),
                'recipient_account': recipient_account,
                'recipient_name': recipient_name or '',
                'description': description or '',
                'metadata': metadata or {},
            }
        )
        
        if not created:
            # Payout already exists - return it (idempotent)
            return payout
        
        # Create event
        PayoutEvent.objects.create(
            payout=payout,
            event_type='CREATED',
            event_data={
                'idempotency_key': idempotency_key,
                'amount': str(amount),
                'recipient_account': recipient_account,
            }
        )
        
        Event.create_event(
            event_id=f"payout_created_{idempotency_key}_{uuid.uuid4()}",
            event_type='PAYOUT_CREATED',
            aggregate_id=str(payout.id),
            aggregate_type='Payout',
            event_data={
                'idempotency_key': idempotency_key,
                'amount': str(amount),
                'recipient_account': recipient_account,
            }
        )
        
        # Create read model
        PayoutSummary.objects.create(
            payout=payout,
            total_amount=Decimal(str(amount)),
            status='PENDING',
            created_at=payout.created_at,
            recipient_account=recipient_account,
        )
        
        return payout
    
    @staticmethod
    @transaction.atomic
    def process_payout(payout):
        """
        Process a payout by creating ledger entries and initiating external payout.
        
        This method:
        1. Marks payout as processing (with locking)
        2. Creates ledger entries
        3. Initiates external payout (via Celery task)
        4. Emits events
        
        Returns:
            Payout instance
        """
        from payouts.models import PayoutEvent
        from payouts.tasks import initiate_external_payout
        
        # Atomically mark as processing
        payout = payout.mark_processing()
        
        # Create event
        PayoutEvent.objects.create(
            payout=payout,
            event_type='PROCESSING_STARTED',
            event_data={}
        )
        
        Event.create_event(
            event_id=f"payout_processing_{payout.idempotency_key}_{uuid.uuid4()}",
            event_type='PAYOUT_PROCESSING',
            aggregate_id=str(payout.id),
            aggregate_type='Payout',
            event_data={
                'idempotency_key': payout.idempotency_key,
                'amount': str(payout.amount),
            }
        )
        
        # Get accounts
        try:
            cash_account = Account.objects.get(account_code=PayoutService.CASH_ACCOUNT_CODE)
            liability_account = Account.objects.get(account_code=PayoutService.PAYOUT_LIABILITY_ACCOUNT_CODE)
        except Account.DoesNotExist:
            payout.mark_failed("Required accounts not found")
            return payout
        
        # Create ledger transaction
        transaction_id = f"payout_{payout.idempotency_key}"
        try:
            ledger_trans = LedgerService.create_transaction(
                transaction_id=transaction_id,
                description=f"Payout to {payout.recipient_account}",
                entries_data=[
                    {
                        'account_id': str(liability_account.id),
                        'amount': payout.amount,
                        'entry_type': 'DEBIT',
                        'description': f"Payout liability debit",
                    },
                    {
                        'account_id': str(cash_account.id),
                        'amount': payout.amount,
                        'entry_type': 'CREDIT',
                        'description': f"Cash payout credit",
                    },
                ],
                metadata={'payout_id': str(payout.id)}
            )
            
            payout.ledger_transaction_id = ledger_trans.transaction_id
            payout.save(update_fields=['ledger_transaction_id'])
            
            # Create event
            PayoutEvent.objects.create(
                payout=payout,
                event_type='LEDGER_ENTRY_CREATED',
                event_data={'transaction_id': transaction_id}
            )
            
        except Exception as e:
            payout.mark_failed(str(e))
            return payout
        
        # Initiate external payout asynchronously
        # This is done outside the transaction to avoid long-running transactions
        initiate_external_payout.delay(str(payout.id))
        
        return payout




