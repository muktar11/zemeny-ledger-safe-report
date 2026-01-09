"""
Management command to initialize required accounts for the ledger system.
"""
from django.core.management.base import BaseCommand
from ledger.models import Account


class Command(BaseCommand):
    help = 'Initialize required accounts for the ledger system'

    def handle(self, *args, **options):
        """Create required accounts if they don't exist."""
        accounts = [
            {
                'account_code': 'CASH_001',
                'name': 'Cash Account',
                'account_type': 'ASSET',
            },
            {
                'account_code': 'PAYOUT_LIABILITY_001',
                'name': 'Payout Liability Account',
                'account_type': 'LIABILITY',
            },
        ]
        
        created_count = 0
        for account_data in accounts:
            account, created = Account.objects.get_or_create(
                account_code=account_data['account_code'],
                defaults=account_data
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Created account: {account.account_code} - {account.name}'
                    )
                )
            else:
                self.stdout.write(
                    f'Account already exists: {account.account_code} - {account.name}'
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nInitialized {created_count} new account(s).'
            )
        )




