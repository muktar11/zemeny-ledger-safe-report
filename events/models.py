"""
Event Stream Models

Implements an ordered, idempotent event stream for state changes.
Events are the source of truth for state derivation and replay.
"""

from django.db import models
from django.db.models import Q, CheckConstraint
import uuid


class Event(models.Model):
    """
    Represents an immutable event in the system.
    Events are append-only and serve as the source of truth for state derivation.
    """
    EVENT_TYPES = [
        ('LEDGER_TRANSACTION_CREATED', 'Ledger Transaction Created'),
        ('PAYOUT_CREATED', 'Payout Created'),
        ('PAYOUT_PROCESSING', 'Payout Processing'),
        ('PAYOUT_COMPLETED', 'Payout Completed'),
        ('PAYOUT_FAILED', 'Payout Failed'),
        ('ACCOUNT_BALANCE_UPDATED', 'Account Balance Updated'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique identifier for idempotency"
    )
    event_type = models.CharField(max_length=100, choices=EVENT_TYPES, db_index=True)
    aggregate_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="ID of the aggregate root (e.g., transaction_id, payout_id)"
    )
    aggregate_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Type of aggregate (e.g., Transaction, Payout)"
    )
    event_data = models.JSONField()
    metadata = models.JSONField(default=dict, blank=True)
    sequence_number = models.BigIntegerField(
        unique=True,
        db_index=True,
        help_text="Monotonically increasing sequence number for ordering"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'events'
        indexes = [
            models.Index(fields=['event_id']),
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['aggregate_type', 'aggregate_id', 'created_at']),
            models.Index(fields=['sequence_number']),
            models.Index(fields=['created_at']),  # For cursor pagination
        ]
        constraints = [
            # Ensure event_id is always present
            CheckConstraint(
                check=~Q(event_id=''),
                name='event_id_not_empty'
            ),
            # Ensure sequence_number is positive
            CheckConstraint(
                check=Q(sequence_number__gt=0),
                name='sequence_number_positive'
            ),
        ]
        ordering = ['sequence_number']
    
    def __str__(self):
        return f"{self.event_type} - {self.aggregate_id} (#{self.sequence_number})"
    
    def save(self, *args, **kwargs):
        """Override save to prevent updates to existing events."""
        if self.pk and Event.objects.filter(pk=self.pk).exists():
            raise ValueError("Events are immutable and cannot be updated")
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Override delete to prevent deletion of events."""
        raise ValueError("Events are immutable and cannot be deleted")
    
    @classmethod
    def get_next_sequence_number(cls):
        """Get the next sequence number atomically."""
        from django.db import transaction
        from django.db.models import Max
        
        with transaction.atomic():
            max_seq = cls.objects.aggregate(Max('sequence_number'))['sequence_number__max']
            return (max_seq or 0) + 1
    
    @classmethod
    def create_event(cls, event_id, event_type, aggregate_id, aggregate_type, event_data, metadata=None):
        """
        Atomically create an event with the next sequence number.
        
        This ensures events are ordered and idempotent.
        """
        from django.db import transaction
        
        with transaction.atomic():
            # Check for idempotency
            if cls.objects.filter(event_id=event_id).exists():
                return cls.objects.get(event_id=event_id)
            
            sequence_number = cls.get_next_sequence_number()
            event = cls.objects.create(
                event_id=event_id,
                event_type=event_type,
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                event_data=event_data,
                metadata=metadata or {},
                sequence_number=sequence_number
            )
            return event
