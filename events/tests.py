"""
Tests for Event Models

Tests cover:
- Event ordering
- Event idempotency
- Event replay correctness
"""

from django.test import TestCase
from events.models import Event


class EventModelTests(TestCase):
    """Test event models."""
    
    def test_event_sequence_numbers_are_monotonic(self):
        """Test that event sequence numbers are monotonically increasing."""
        event1 = Event.create_event(
            event_id='event_001',
            event_type='LEDGER_TRANSACTION_CREATED',
            aggregate_id='agg_001',
            aggregate_type='Transaction',
            event_data={}
        )
        
        event2 = Event.create_event(
            event_id='event_002',
            event_type='PAYOUT_CREATED',
            aggregate_id='agg_002',
            aggregate_type='Payout',
            event_data={}
        )
        
        event3 = Event.create_event(
            event_id='event_003',
            event_type='PAYOUT_COMPLETED',
            aggregate_id='agg_002',
            aggregate_type='Payout',
            event_data={}
        )
        
        self.assertLess(event1.sequence_number, event2.sequence_number)
        self.assertLess(event2.sequence_number, event3.sequence_number)
    
    def test_event_idempotency(self):
        """Test that duplicate event_ids return existing event."""
        event_id = 'idempotent_event_001'
        
        event1 = Event.create_event(
            event_id=event_id,
            event_type='LEDGER_TRANSACTION_CREATED',
            aggregate_id='agg_001',
            aggregate_type='Transaction',
            event_data={'test': 'data1'}
        )
        
        event2 = Event.create_event(
            event_id=event_id,
            event_type='LEDGER_TRANSACTION_CREATED',
            aggregate_id='agg_001',
            aggregate_type='Transaction',
            event_data={'test': 'data2'}  # Different data
        )
        
        # Should return same event
        self.assertEqual(event1.id, event2.id)
        self.assertEqual(event1.sequence_number, event2.sequence_number)
    
    def test_event_immutability(self):
        """Test that events cannot be updated or deleted."""
        event = Event.create_event(
            event_id='immutable_event_001',
            event_type='LEDGER_TRANSACTION_CREATED',
            aggregate_id='agg_001',
            aggregate_type='Transaction',
            event_data={}
        )
        
        # Try to update
        with self.assertRaises(ValueError):
            event.event_data = {'modified': True}
            event.save()
        
        # Try to delete
        with self.assertRaises(ValueError):
            event.delete()
    
    def test_event_replay(self):
        """Test that events can be replayed in order."""
        # Create multiple events
        events = []
        for i in range(5):
            event = Event.create_event(
                event_id=f'replay_event_{i}',
                event_type='LEDGER_TRANSACTION_CREATED',
                aggregate_id=f'agg_{i}',
                aggregate_type='Transaction',
                event_data={'index': i}
            )
            events.append(event)
        
        # Replay events in order
        replayed_events = Event.objects.filter(
            event_id__startswith='replay_event_'
        ).order_by('sequence_number')
        
        self.assertEqual(len(replayed_events), 5)
        for i, event in enumerate(replayed_events):
            self.assertEqual(event.event_data['index'], i)
