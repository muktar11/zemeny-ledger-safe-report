"""Admin configuration for payouts app."""
from django.contrib import admin
from .models import Payout, PayoutEvent


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ['idempotency_key', 'amount', 'recipient_account', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['idempotency_key', 'recipient_account', 'external_payout_id']
    readonly_fields = ['id', 'created_at', 'updated_at', 'processed_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('idempotency_key', 'amount', 'currency', 'status')
        }),
        ('Recipient', {
            'fields': ('recipient_account', 'recipient_name', 'description')
        }),
        ('Tracking', {
            'fields': ('ledger_transaction_id', 'external_payout_id', 'external_reference')
        }),
        ('Error Handling', {
            'fields': ('error_message', 'retry_count')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'processed_at')
        }),
        ('Metadata', {
            'fields': ('metadata',)
        }),
    )


@admin.register(PayoutEvent)
class PayoutEventAdmin(admin.ModelAdmin):
    list_display = ['payout', 'event_type', 'created_at']
    list_filter = ['event_type', 'created_at']
    search_fields = ['payout__idempotency_key']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']
