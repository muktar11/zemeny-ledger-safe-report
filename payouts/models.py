"""
Payout Models with Exactly-Once Execution Guarantees

Implements idempotent payout processing with database-level guarantees
to prevent duplicate execution even under failure conditions.
"""

from django.db import models
from django.db.models import Q, CheckConstraint
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid


class Payout(models.Model):
    """
    Represents a payout request with exactly-once execution guarantees.
    
    Uses idempotency keys to ensure that duplicate API calls or task retries
    do not result in duplicate payouts.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique key to ensure exactly-once execution"
    )
    amount = models.DecimalField(
        max_digits=19,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    currency = models.CharField(max_length=3, default='USD')
    recipient_account = models.CharField(max_length=255)
    recipient_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    
    # Transaction tracking
    ledger_transaction_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    
    # External payout tracking
    external_payout_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    external_reference = models.CharField(max_length=255, null=True, blank=True)
    
    # Error tracking
    error_message = models.TextField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'payouts'
        indexes = [
            models.Index(fields=['idempotency_key']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['ledger_transaction_id']),
            models.Index(fields=['external_payout_id']),
            models.Index(fields=['created_at']),  # For cursor pagination
        ]
        constraints = [
            # Ensure idempotency_key is always present
            CheckConstraint(
                check=~Q(idempotency_key=''),
                name='idempotency_key_not_empty'
            ),
            # Ensure amount is positive
            CheckConstraint(
                check=Q(amount__gt=0),
                name='payout_amount_positive'
            ),
        ]
    
    def __str__(self):
        return f"Payout {self.idempotency_key} - {self.status}"
    
    @classmethod
    def get_or_create_pending(cls, idempotency_key, defaults):
        """
        Atomically get existing payout or create a new pending one.
        
        This method uses database-level locking to ensure that concurrent
        requests with the same idempotency_key result in only one payout.
        
        Returns:
            (payout, created) tuple
        """
        from django.db import transaction
        
        with transaction.atomic():
            # Use select_for_update to lock the row if it exists
            try:
                payout = cls.objects.select_for_update().get(
                    idempotency_key=idempotency_key
                )
                return payout, False
            except cls.DoesNotExist:
                # Create new payout atomically
                payout = cls.objects.create(
                    idempotency_key=idempotency_key,
                    status='PENDING',
                    **defaults
                )
                return payout, True
    
    def mark_processing(self):
        """Atomically mark payout as processing."""
        from django.db import transaction
        
        with transaction.atomic():
            # Use select_for_update to prevent concurrent processing
            payout = Payout.objects.select_for_update().get(pk=self.pk)
            if payout.status != 'PENDING':
                raise ValueError(f"Cannot process payout in status: {payout.status}")
            payout.status = 'PROCESSING'
            payout.save(update_fields=['status', 'updated_at'])
            return payout
    
    def mark_completed(self, external_payout_id=None, external_reference=None):
        """Mark payout as completed."""
        self.status = 'COMPLETED'
        if external_payout_id:
            self.external_payout_id = external_payout_id
        if external_reference:
            self.external_reference = external_reference
        from django.utils import timezone
        self.processed_at = timezone.now()
        self.save(update_fields=['status', 'external_payout_id', 'external_reference', 'processed_at', 'updated_at'])
    
    def mark_failed(self, error_message):
        """Mark payout as failed."""
        self.status = 'FAILED'
        self.error_message = error_message
        self.retry_count += 1
        self.save(update_fields=['status', 'error_message', 'retry_count', 'updated_at'])


class PayoutEvent(models.Model):
    """
    Tracks events related to payout processing for audit and replay purposes.
    """
    EVENT_TYPES = [
        ('CREATED', 'Created'),
        ('PROCESSING_STARTED', 'Processing Started'),
        ('LEDGER_ENTRY_CREATED', 'Ledger Entry Created'),
        ('EXTERNAL_PAYOUT_INITIATED', 'External Payout Initiated'),
        ('EXTERNAL_PAYOUT_COMPLETED', 'External Payout Completed'),
        ('EXTERNAL_PAYOUT_FAILED', 'External Payout Failed'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('RETRY', 'Retry'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payout = models.ForeignKey(
        Payout,
        on_delete=models.CASCADE,
        related_name='events',
        db_index=True
    )
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES, db_index=True)
    event_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'payout_events'
        indexes = [
            models.Index(fields=['payout', 'created_at']),
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.payout.idempotency_key} - {self.event_type}"
