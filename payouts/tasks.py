"""
Celery Tasks for Payout Processing

Tasks are designed with failure-first principles:
- Restartable
- Idempotent
- No partial state corruption
"""

from celery import shared_task
from django.db import transaction
from payouts.models import Payout, PayoutEvent
from payouts.services import PayoutService
from events.models import Event
import uuid


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_payout_task(self, payout_id):
    """
    Process a payout by creating ledger entries and initiating external payout.
    
    This task is:
    - Idempotent: Can be retried safely
    - Restartable: Can resume from any point
    - Failure-safe: Partial execution doesn't corrupt state
    
    Args:
        payout_id: UUID of the payout to process
    """
    try:
        payout = Payout.objects.get(id=payout_id)
        
        # If already completed or failed, don't process again
        if payout.status in ['COMPLETED', 'FAILED']:
            return {'status': payout.status, 'message': 'Already processed'}
        
        # Process payout (creates ledger entries)
        payout = PayoutService.process_payout(payout)
        
        return {
            'status': payout.status,
            'payout_id': str(payout.id),
            'idempotency_key': payout.idempotency_key,
        }
        
    except Payout.DoesNotExist:
        # Payout doesn't exist - don't retry
        return {'error': 'Payout not found'}
    except Exception as exc:
        # Retry on failure
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def initiate_external_payout(self, payout_id):
    """
    Initiate external payout (e.g., bank transfer, payment gateway).
    
    This task simulates an external payout API call.
    In production, this would call an actual payment provider.
    
    This task is designed to handle:
    - Network failures
    - Timeouts
    - Partial failures
    - Duplicate calls (idempotent)
    """
    try:
        payout = Payout.objects.get(id=payout_id)
        
        # If already completed, don't process again (idempotent)
        if payout.status == 'COMPLETED':
            return {'status': 'completed', 'message': 'Already completed'}
        
        # If not processing, something went wrong
        if payout.status != 'PROCESSING':
            return {'status': payout.status, 'message': 'Invalid state'}
        
        # Check if external payout already initiated (idempotency check)
        if payout.external_payout_id:
            # External payout already initiated - check status
            # In production, this would query the external system
            return {
                'status': 'already_initiated',
                'external_payout_id': payout.external_payout_id
            }
        
        # Simulate external payout API call
        # In production, this would be:
        # response = external_payout_api.create_payout(
        #     amount=payout.amount,
        #     recipient=payout.recipient_account,
        #     idempotency_key=payout.idempotency_key
        # )
        
        # For this assignment, we simulate a successful payout
        external_payout_id = f"ext_{payout.idempotency_key}_{uuid.uuid4()}"
        
        # Create event before updating payout
        PayoutEvent.objects.create(
            payout=payout,
            event_type='EXTERNAL_PAYOUT_INITIATED',
            event_data={'external_payout_id': external_payout_id}
        )
        
        # Update payout with external ID
        payout.external_payout_id = external_payout_id
        payout.save(update_fields=['external_payout_id', 'updated_at'])
        
        # Simulate async completion (in production, this would be a webhook)
        # For now, we'll mark it as completed immediately
        complete_external_payout.delay(str(payout.id), external_payout_id)
        
        return {
            'status': 'initiated',
            'external_payout_id': external_payout_id
        }
        
    except Payout.DoesNotExist:
        return {'error': 'Payout not found'}
    except Exception as exc:
        # Retry on failure
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def complete_external_payout(self, payout_id, external_payout_id):
    """
    Complete external payout and mark payout as completed.
    
    In production, this would be triggered by a webhook from the payment provider.
    """
    try:
        payout = Payout.objects.get(id=payout_id)
        
        # Verify external_payout_id matches
        if payout.external_payout_id != external_payout_id:
            return {'error': 'External payout ID mismatch'}
        
        # If already completed, don't process again (idempotent)
        if payout.status == 'COMPLETED':
            return {'status': 'completed', 'message': 'Already completed'}
        
        # Create event
        PayoutEvent.objects.create(
            payout=payout,
            event_type='EXTERNAL_PAYOUT_COMPLETED',
            event_data={'external_payout_id': external_payout_id}
        )
        
        # Mark payout as completed
        payout.mark_completed(
            external_payout_id=external_payout_id,
            external_reference=f"ref_{external_payout_id}"
        )
        
        # Emit completion event
        Event.create_event(
            event_id=f"payout_completed_{payout.idempotency_key}_{uuid.uuid4()}",
            event_type='PAYOUT_COMPLETED',
            aggregate_id=str(payout.id),
            aggregate_type='Payout',
            event_data={
                'idempotency_key': payout.idempotency_key,
                'external_payout_id': external_payout_id,
            }
        )
        
        # Update read model
        from read_models.models import PayoutSummary
        PayoutSummary.objects.filter(payout=payout).update(
            status='COMPLETED',
            processed_at=payout.processed_at
        )
        
        return {
            'status': 'completed',
            'payout_id': str(payout.id)
        }
        
    except Payout.DoesNotExist:
        return {'error': 'Payout not found'}
    except Exception as exc:
        raise self.retry(exc=exc)




