"""
Tests for Ledger Models and Services

Tests cover:
- Double-entry bookkeeping invariants
- Immutability guarantees
- Balance verification
- Concurrency safety
"""

import pytest
from decimal import Decimal
from django.db import transaction, IntegrityError
from django.test import TestCase
from ledger.models import Account, Transaction, LedgerEntry
from ledger.services import LedgerService
from read_models.models import AccountBalance


class LedgerModelTests(TestCase):
    """Test ledger models."""
    
    def setUp(self):
        """Set up test accounts."""
        self.asset_account = Account.objects.create(
            account_code='ASSET_001',
            name='Cash Account',
            account_type='ASSET'
        )
        self.liability_account = Account.objects.create(
            account_code='LIABILITY_001',
            name='Accounts Payable',
            account_type='LIABILITY'
        )
    
    def test_create_transaction_balances_to_zero(self):
        """Test that transactions must balance to zero."""
        trans = Transaction.create_transaction(
            transaction_id='test_txn_001',
            description='Test transaction',
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
        
        self.assertEqual(trans.status, 'COMPLETED')
        self.assertEqual(trans.entries.count(), 2)
        self.assertTrue(trans.verify_balance())
    
    def test_create_transaction_requires_exactly_two_entries(self):
        """Test that transactions require exactly 2 entries."""
        with self.assertRaises(ValueError):
            Transaction.create_transaction(
                transaction_id='test_txn_002',
                description='Invalid transaction',
                entries_data=[
                    {
                        'account_id': str(self.asset_account.id),
                        'amount': Decimal('100.00'),
                        'entry_type': 'DEBIT',
                    },
                ]
            )
    
    def test_create_transaction_rejects_unbalanced_entries(self):
        """Test that unbalanced transactions are rejected."""
        with self.assertRaises(ValueError):
            Transaction.create_transaction(
                transaction_id='test_txn_003',
                description='Unbalanced transaction',
                entries_data=[
                    {
                        'account_id': str(self.asset_account.id),
                        'amount': Decimal('100.00'),
                        'entry_type': 'DEBIT',
                    },
                    {
                        'account_id': str(self.liability_account.id),
                        'amount': Decimal('-50.00'),  # Doesn't balance
                        'entry_type': 'CREDIT',
                    },
                ]
            )
    
    def test_ledger_entry_immutability(self):
        """Test that ledger entries cannot be updated."""
        trans = Transaction.create_transaction(
            transaction_id='test_txn_004',
            description='Test transaction',
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
        
        entry = trans.entries.first()
        
        # Try to update
        with self.assertRaises(ValueError):
            entry.amount = Decimal('200.00')
            entry.save()
        
        # Try to delete
        with self.assertRaises(ValueError):
            entry.delete()
    
    def test_account_balance_calculation(self):
        """Test account balance calculation."""
        # Create transactions
        Transaction.create_transaction(
            transaction_id='test_txn_005',
            description='Test transaction 1',
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
            transaction_id='test_txn_006',
            description='Test transaction 2',
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
        
        # Rebuild balance
        balance = AccountBalance.rebuild_for_account(self.asset_account)
        
        # Asset account: debits increase balance
        self.assertEqual(balance.balance, Decimal('150.00'))


class LedgerConcurrencyTests(TestCase):
    """Test concurrency scenarios."""
    
    def setUp(self):
        """Set up test accounts."""
        self.asset_account = Account.objects.create(
            account_code='ASSET_002',
            name='Cash Account',
            account_type='ASSET'
        )
        self.liability_account = Account.objects.create(
            account_code='LIABILITY_002',
            name='Accounts Payable',
            account_type='LIABILITY'
        )
    
    def test_concurrent_transaction_creation(self):
        """Test that concurrent transactions don't corrupt data."""
        import threading
        
        results = []
        errors = []
        
        def create_transaction(txn_id):
            try:
                trans = Transaction.create_transaction(
                    transaction_id=f'concurrent_txn_{txn_id}',
                    description=f'Concurrent transaction {txn_id}',
                    entries_data=[
                        {
                            'account_id': str(self.asset_account.id),
                            'amount': Decimal('10.00'),
                            'entry_type': 'DEBIT',
                        },
                        {
                            'account_id': str(self.liability_account.id),
                            'amount': Decimal('-10.00'),
                            'entry_type': 'CREDIT',
                        },
                    ]
                )
                results.append(trans)
            except Exception as e:
                errors.append(str(e))
        
        # Create 10 concurrent transactions
        threads = []
        for i in range(10):
            thread = threading.Thread(target=create_transaction, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All transactions should succeed
        self.assertEqual(len(results), 10)
        self.assertEqual(len(errors), 0)
        
        # All transactions should balance
        for trans in results:
            self.assertTrue(trans.verify_balance())


class LedgerServiceTests(TestCase):
    """Test ledger services."""
    
    def setUp(self):
        """Set up test accounts."""
        self.asset_account = Account.objects.create(
            account_code='ASSET_003',
            name='Cash Account',
            account_type='ASSET'
        )
        self.liability_account = Account.objects.create(
            account_code='LIABILITY_003',
            name='Accounts Payable',
            account_type='LIABILITY'
        )
    
    def test_ledger_service_creates_transaction(self):
        """Test that ledger service creates transactions correctly."""
        trans = LedgerService.create_transaction(
            transaction_id='service_txn_001',
            description='Service test transaction',
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
        
        self.assertIsNotNone(trans)
        self.assertTrue(trans.verify_balance())
        
        # Check that event was created
        from events.models import Event
        events = Event.objects.filter(
            aggregate_id=str(trans.id),
            event_type='LEDGER_TRANSACTION_CREATED'
        )
        self.assertEqual(events.count(), 1)
        
        # Check that account balance was updated
        balance = AccountBalance.objects.get(account=self.asset_account)
        self.assertEqual(balance.balance, Decimal('100.00'))
