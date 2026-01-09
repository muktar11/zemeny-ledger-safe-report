"""Admin configuration for read_models app."""
from django.contrib import admin
from .models import AccountBalance, PayoutSummary, LedgerTransactionSummary


@admin.register(AccountBalance)
class AccountBalanceAdmin(admin.ModelAdmin):
    list_display = ['account', 'balance', 'last_updated_at']
    list_filter = ['last_updated_at']
    search_fields = ['account__account_code', 'account__name']
    readonly_fields = ['id', 'last_updated_at']


@admin.register(PayoutSummary)
class PayoutSummaryAdmin(admin.ModelAdmin):
    list_display = ['payout', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['payout__idempotency_key', 'recipient_account']
    readonly_fields = ['id']


@admin.register(LedgerTransactionSummary)
class LedgerTransactionSummaryAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'total_amount', 'entry_count', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['transaction__transaction_id']
    readonly_fields = ['id']
