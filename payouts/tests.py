"""
Tests for Payout Models and Services

Tests cover:
- Idempotency guarantees
- Exactly-once execution
- Concurrency with identical idempotency keys
- Task interruption and restart behavior
"""

import pytest
from decimal import Decimal
from django.db import transaction
from django.test import TestCase
from payouts.models import Payout, PayoutEvent
from payouts.services import PayoutService
from ledger.models import Account


class PayoutIdempotencyTests(TestCase):
    """Test idempotency guarantees."""
    
    def setUp(self):
        """Set up test accounts."""
        self.cash_account = Account.objects.create(
            account_code='CASH_001',
            name='Cash Account',
            account_type='ASSET'
        )
        self.liability_account = Account.objects.create(
            account_code='PAYOUT_LIABILITY_001',
            name='Payout Liability',
            account_type='LIABILITY'
        )
    
    def test_duplicate_idempotency_key_returns_existing(self):
        """Test that duplicate idempotency keys return existing payout."""
        idempotency_key = 'test_key_001'
        
        # Create first payout
        payout1 = PayoutService.initiate_payout(
            idempotency_key=idempotency_key,
            amount=Decimal('100.00'),
            recipient_account='account_123'
        )
        
        # Try to create duplicate
        payout2 = PayoutService.initiate_payout(
            idempotency_key=idempotency_key,
            amount=Decimal('100.00'),
            recipient_account='account_123'
        )
        
        # Should return same payout
        self.assertEqual(payout1.id, payout2.id)
        self.assertEqual(payout1.idempotency_key, payout2.idempotency_key)
    
    def test_concurrent_identical_idempotency_keys(self):
        """Test concurrent requests with identical idempotency keys."""
        import threading
        
        idempotency_key = 'concurrent_key_001'
        results = []
        
        def create_payout():
            payout = PayoutService.initiate_payout(
                idempotency_key=idempotency_key,
                amount=Decimal('100.00'),
                recipient_account='account_123'
            )
            results.append(payout)
        
        # Create 5 concurrent requests
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=create_payout)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All should return the same payout
        self.assertEqual(len(results), 5)
        payout_ids = {p.id for p in results}
        self.assertEqual(len(payout_ids), 1)  # All same payout
        
        # Only one payout should exist in database
        payouts = Payout.objects.filter(idempotency_key=idempotency_key)
        self.assertEqual(payouts.count(), 1)
    
    def test_payout_processing_is_idempotent(self):
        """Test that processing a payout multiple times is safe."""
        payout = PayoutService.initiate_payout(
            idempotency_key='process_test_001',
            amount=Decimal('100.00'),
            recipient_account='account_123'
        )
        
        # Process first time
        payout1 = PayoutService.process_payout(payout)
        self.assertEqual(payout1.status, 'PROCESSING')
        
        # Try to process again (should be safe but not change state)
        payout2 = PayoutService.process_payout(payout1)
        # Status should remain PROCESSING or be COMPLETED, but not duplicate
        self.assertIn(payout2.status, ['PROCESSING', 'COMPLETED'])


class PayoutTaskTests(TestCase):
    """Test payout task behavior."""
    
    def setUp(self):
        """Set up test accounts."""
        self.cash_account = Account.objects.create(
            account_code='CASH_001',
            name='Cash Account',
            account_type='ASSET'
        )
        self.liability_account = Account.objects.create(
            account_code='PAYOUT_LIABILITY_001',
            name='Payout Liability',
            account_type='LIABILITY'
        )
    
    def test_task_retry_does_not_duplicate_ledger_entries(self):
        """Test that task retries don't create duplicate ledger entries."""
        payout = PayoutService.initiate_payout(
            idempotency_key='retry_test_001',
            amount=Decimal('100.00'),
            recipient_account='account_123'
        )
        
        # Process payout (creates ledger entries)
        payout = PayoutService.process_payout(payout)
        
        # Get ledger transaction count
        from ledger.models import Transaction
        initial_count = Transaction.objects.filter(
            transaction_id__startswith=f'payout_{payout.idempotency_key}'
        ).count()
        
        # Simulate task retry (should not create duplicate entries)
        from payouts.tasks import process_payout_task
        result = process_payout_task(str(payout.id))
        
        # Count should remain same
        final_count = Transaction.objects.filter(
            transaction_id__startswith=f'payout_{payout.idempotency_key}'
        ).count()
        
        self.assertEqual(initial_count, final_count)


class PayoutEventTests(TestCase):
    """Test payout event tracking."""
    
    def setUp(self):
        """Set up test accounts."""
        self.cash_account = Account.objects.create(
            account_code='CASH_001',
            name='Cash Account',
            account_type='ASSET'
        )
        self.liability_account = Account.objects.create(
            account_code='PAYOUT_LIABILITY_001',
            name='Payout Liability',
            account_type='LIABILITY'
        )
    
    def test_payout_events_are_created(self):
        """Test that payout events are tracked."""
        payout = PayoutService.initiate_payout(
            idempotency_key='event_test_001',
            amount=Decimal('100.00'),
            recipient_account='account_123'
        )
        
        # Check that CREATED event exists
        events = PayoutEvent.objects.filter(
            payout=payout,
            event_type='CREATED'
        )
        self.assertEqual(events.count(), 1)
        
        # Process payout
        payout = PayoutService.process_payout(payout)
        
        # Check that PROCESSING_STARTED event exists
        events = PayoutEvent.objects.filter(
            payout=payout,
            event_type='PROCESSING_STARTED'
        )
        self.assertEqual(events.count(), 1)
