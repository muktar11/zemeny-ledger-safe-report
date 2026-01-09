"""Admin configuration for events app."""
from django.contrib import admin
from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['event_id', 'event_type', 'aggregate_type', 'aggregate_id', 'sequence_number', 'created_at']
    list_filter = ['event_type', 'aggregate_type', 'created_at']
    search_fields = ['event_id', 'aggregate_id']
    readonly_fields = ['id', 'sequence_number', 'created_at']
    ordering = ['-sequence_number']
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of events (immutable)
        return False
    
    def has_change_permission(self, request, obj=None):
        # Prevent updates to events (immutable)
        return False
