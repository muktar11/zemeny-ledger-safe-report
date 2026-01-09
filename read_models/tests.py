"""
Tests for Read Models

Tests cover:
- Read model rebuilds
- State derivation from source data
"""

from decimal import Decimal
from django.test import TestCase
from ledger.models import Account, Transaction
from read_models.models import AccountBalance


class ReadModelTests(TestCase):
    """Test read models."""
    
    def setUp(self):
        """Set up test accounts."""
        self.asset_account = Account.objects.create(
            account_code='ASSET_004',
            name='Cash Account',
            account_type='ASSET'
        )
        self.liability_account = Account.objects.create(
            account_code='LIABILITY_004',
            name='Accounts Payable',
            account_type='LIABILITY'
        )
    
    def test_account_balance_rebuild(self):
        """Test that account balance can be rebuilt from scratch."""
        # Create transactions
        Transaction.create_transaction(
            transaction_id='rebuild_txn_001',
            description='Transaction 1',
            entries_data=[
                {
                    'account_id': str(self.asset_account.id),
                    'amount': Decimal('100.00'),
                    'entry_type': 'DEBIT',
                },
                {
                    'account_id': str(self.liability_account.id),
                    'amount': Decimal('-100.00'),
                    'entry_type': 'CREDIT',
                },
            ]
        )
        
        Transaction.create_transaction(
            transaction_id='rebuild_txn_002',
            description='Transaction 2',
            entries_data=[
                {
                    'account_id': str(self.asset_account.id),
                    'amount': Decimal('50.00'),
                    'entry_type': 'DEBIT',
                },
                {
                    'account_id': str(self.liability_account.id),
                    'amount': Decimal('-50.00'),
                    'entry_type': 'CREDIT',
                },
            ]
        )
        
        # Delete read model
        AccountBalance.objects.filter(account=self.asset_account).delete()
        
        # Rebuild from scratch
        balance = AccountBalance.rebuild_for_account(self.asset_account)
        
        # Should match expected balance
        self.assertEqual(balance.balance, Decimal('150.00'))
    
    def test_account_balance_is_derived_from_ledger(self):
        """Test that account balance is correctly derived from ledger entries."""
        # Create transaction
        Transaction.create_transaction(
            transaction_id='derive_txn_001',
            description='Derive test',
            entries_data=[
                {
                    'account_id': str(self.asset_account.id),
                    'amount': Decimal('200.00'),
                    'entry_type': 'DEBIT',
                },
                {
                    'account_id': str(self.liability_account.id),
                    'amount': Decimal('-200.00'),
                    'entry_type': 'CREDIT',
                },
            ]
        )
        
        # Rebuild balance
        balance = AccountBalance.rebuild_for_account(self.asset_account)
        
        # Calculate expected balance manually
        from ledger.models import LedgerEntry
        entries = LedgerEntry.objects.filter(account=self.asset_account)
        expected_balance = sum(
            entry.amount if entry.entry_type == 'DEBIT' else -entry.amount
            for entry in entries
        )
        
        self.assertEqual(balance.balance, expected_balance)
