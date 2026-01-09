"""Admin configuration for ledger app."""
from django.contrib import admin
from .models import Account, Transaction, LedgerEntry


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['account_code', 'name', 'account_type', 'created_at']
    list_filter = ['account_type']
    search_fields = ['account_code', 'name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'description', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['transaction_id', 'description']
    readonly_fields = ['id', 'created_at']
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of transactions (immutable)
        return False


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'account', 'amount', 'entry_type', 'created_at']
    list_filter = ['entry_type', 'created_at']
    search_fields = ['transaction__transaction_id', 'account__account_code']
    readonly_fields = ['id', 'created_at']
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of ledger entries (immutable)
        return False
    
    def has_change_permission(self, request, obj=None):
        # Prevent updates to ledger entries (immutable)
        return False
