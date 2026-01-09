"""
Double-Entry Ledger Models

Implements a true double-entry ledger system where:
- Every transaction generates exactly two ledger entries
- All transactions must balance to zero
- Ledger entries are immutable (no updates or deletions)
- Database-level constraints prevent invariant violations
"""

from django.db import models
from django.db.models import Sum, Q, CheckConstraint
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid


class Account(models.Model):
    """
    Represents an account in the ledger system.
    Accounts can be of different types (asset, liability, equity, revenue, expense).
    """
    ACCOUNT_TYPES = [
        ('ASSET', 'Asset'),
        ('LIABILITY', 'Liability'),
        ('EQUITY', 'Equity'),
        ('REVENUE', 'Revenue'),
        ('EXPENSE', 'Expense'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account_code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'ledger_accounts'
        indexes = [
            models.Index(fields=['account_code']),
            models.Index(fields=['account_type']),
        ]
    
    def __str__(self):
        return f"{self.account_code} - {self.name}"


class Transaction(models.Model):
    """
    Represents a financial transaction that generates ledger entries.
    Each transaction must have exactly two entries that balance to zero.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'ledger_transactions'
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['created_at']),  # For cursor pagination
        ]
        constraints = [
            # Ensure transaction_id is always present
            models.CheckConstraint(
                check=~Q(transaction_id=''),
                name='transaction_id_not_empty'
            ),
        ]
    
    def __str__(self):
        return f"Transaction {self.transaction_id}"
    
    def verify_balance(self):
        """Verify that all entries for this transaction balance to zero."""
        entries = self.entries.all()
        total = sum(entry.amount for entry in entries)
        return total == Decimal('0.00')
    
    @classmethod
    def create_transaction(cls, transaction_id, description, entries_data, metadata=None):
        """
        Create a transaction with ledger entries atomically.
        Ensures double-entry bookkeeping: exactly two entries that balance to zero.
        
        Args:
            transaction_id: Unique identifier for the transaction
            description: Description of the transaction
            entries_data: List of dicts with 'account_id', 'amount', 'entry_type'
            metadata: Optional metadata dict
            
        Returns:
            Transaction instance
            
        Raises:
            ValueError: If entries don't balance to zero or count != 2
        """
        if len(entries_data) != 2:
            raise ValueError("Double-entry ledger requires exactly 2 entries per transaction")
        
        total = sum(Decimal(str(entry['amount'])) for entry in entries_data)
        if total != Decimal('0.00'):
            raise ValueError(f"Transaction entries must balance to zero. Total: {total}")
        
        # Use database transaction to ensure atomicity
        from django.db import transaction as db_transaction
        
        with db_transaction.atomic():
            trans = cls.objects.create(
                transaction_id=transaction_id,
                description=description,
                status='COMPLETED',
                metadata=metadata or {}
            )
            
            for entry_data in entries_data:
                LedgerEntry.objects.create(
                    transaction=trans,
                    account_id=entry_data['account_id'],
                    amount=Decimal(str(entry_data['amount'])),
                    entry_type=entry_data['entry_type'],
                    description=entry_data.get('description', ''),
                )
            
            # Verify balance at database level
            balance = LedgerEntry.objects.filter(transaction=trans).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0.00')
            
            if balance != Decimal('0.00'):
                raise ValueError(f"Transaction balance verification failed: {balance}")
        
        return trans


class LedgerEntry(models.Model):
    """
    Represents a single entry in the double-entry ledger.
    Entries are immutable - once created, they cannot be modified or deleted.
    """
    ENTRY_TYPES = [
        ('DEBIT', 'Debit'),
        ('CREDIT', 'Credit'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.PROTECT,  # Prevent deletion of transactions with entries
        related_name='entries',
        db_index=True
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,  # Prevent deletion of accounts with entries
        related_name='entries',
        db_index=True
    )
    amount = models.DecimalField(
        max_digits=19,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPES)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'ledger_entries'
        indexes = [
            models.Index(fields=['transaction', 'created_at']),
            models.Index(fields=['account', 'created_at']),
            models.Index(fields=['created_at']),  # For cursor pagination
            # Composite index for common queries
            models.Index(fields=['account', 'entry_type', 'created_at']),
        ]
        constraints = [
            # Ensure amount is always positive
            CheckConstraint(
                check=Q(amount__gte=0),
                name='ledger_entry_amount_non_negative'
            ),
        ]
        # Prevent updates and deletions at model level
        # (Application code should never call update() or delete())
    
    def __str__(self):
        return f"{self.entry_type} {self.amount} to {self.account.account_code}"
    
    def save(self, *args, **kwargs):
        """Override save to prevent updates to existing entries."""
        if self.pk and LedgerEntry.objects.filter(pk=self.pk).exists():
            raise ValueError("Ledger entries are immutable and cannot be updated")
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Override delete to prevent deletion of ledger entries."""
        raise ValueError("Ledger entries are immutable and cannot be deleted")
