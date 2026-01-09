"""
Read Models

Denormalized read models derived from events and source data.
These models are rebuildable from scratch and optimized for queries.
"""

from django.db import models
from django.db.models import Sum, Q
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid


class AccountBalance(models.Model):
    """
    Read model representing the current balance of an account.
    This is derived from ledger entries and can be rebuilt from scratch.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField(
        'ledger.Account',
        on_delete=models.CASCADE,
        related_name='balance',
        db_index=True
    )
    balance = models.DecimalField(
        max_digits=19,
        decimal_places=2,
        default=Decimal('0.00')
    )
    last_updated_at = models.DateTimeField(auto_now=True, db_index=True)
    last_event_sequence = models.BigIntegerField(
        default=0,
        help_text="Sequence number of last processed event"
    )
    
    class Meta:
        db_table = 'account_balances'
        indexes = [
            models.Index(fields=['account']),
            models.Index(fields=['last_updated_at']),
        ]
    
    def __str__(self):
        return f"{self.account.account_code}: {self.balance}"
    
    @classmethod
    def rebuild_for_account(cls, account):
        """
        Rebuild account balance from all ledger entries.
        This method can be called to reconstruct the balance from source data.
        """
        from ledger.models import LedgerEntry
        
        # Calculate balance from all entries
        # Debits increase asset/expense accounts, credits decrease them
        # Credits increase liability/equity/revenue accounts, debits decrease them
        
        entries = LedgerEntry.objects.filter(account=account)
        
        balance = Decimal('0.00')
        for entry in entries:
            if account.account_type in ['ASSET', 'EXPENSE']:
                # Debits increase, credits decrease
                if entry.entry_type == 'DEBIT':
                    balance += entry.amount
                else:
                    balance -= entry.amount
            else:
                # Credits increase, debits decrease
                if entry.entry_type == 'CREDIT':
                    balance += entry.amount
                else:
                    balance -= entry.amount
        
        account_balance, _ = cls.objects.update_or_create(
            account=account,
            defaults={
                'balance': balance,
            }
        )
        return account_balance


class PayoutSummary(models.Model):
    """
    Read model for payout summaries optimized for reporting.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payout = models.OneToOneField(
        'payouts.Payout',
        on_delete=models.CASCADE,
        related_name='summary',
        db_index=True
    )
    total_amount = models.DecimalField(max_digits=19, decimal_places=2)
    status = models.CharField(max_length=20, db_index=True)
    created_at = models.DateTimeField(db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    recipient_account = models.CharField(max_length=255, db_index=True)
    
    class Meta:
        db_table = 'payout_summaries'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['recipient_account', 'created_at']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Payout Summary: {self.payout.idempotency_key} - {self.status}"


class LedgerTransactionSummary(models.Model):
    """
    Read model for transaction summaries.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.OneToOneField(
        'ledger.Transaction',
        on_delete=models.CASCADE,
        related_name='summary',
        db_index=True
    )
    total_amount = models.DecimalField(max_digits=19, decimal_places=2)
    entry_count = models.IntegerField()
    status = models.CharField(max_length=20, db_index=True)
    created_at = models.DateTimeField(db_index=True)
    
    class Meta:
        db_table = 'ledger_transaction_summaries'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Transaction Summary: {self.transaction.transaction_id}"
