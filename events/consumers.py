"""
WebSocket Consumers for Real-Time Event Streaming

Events are streamed to clients via WebSocket for real-time updates.
Note: WebSocket delivery is NOT a source of truth - authoritative state
resides in the database.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from events.models import Event


class EventConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for streaming events to clients."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        await self.accept()
        
        # Send initial message
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to event stream. Events will be streamed as they occur.'
        }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        pass
    
    async def receive(self, text_data):
        """Handle messages from client."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'subscribe':
                # Client wants to subscribe to specific event types
                event_types = data.get('event_types', [])
                await self.send(text_data=json.dumps({
                    'type': 'subscribed',
                    'event_types': event_types
                }))
            elif message_type == 'get_latest':
                # Client wants to get latest events
                sequence_number = data.get('sequence_number', 0)
                events = await self.get_events_after(sequence_number)
                await self.send(text_data=json.dumps({
                    'type': 'events',
                    'events': events
                }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
    
    @database_sync_to_async
    def get_events_after(self, sequence_number):
        """Get events after a given sequence number."""
        events = Event.objects.filter(
            sequence_number__gt=sequence_number
        ).order_by('sequence_number')[:100]
        
        return [
            {
                'event_id': str(event.event_id),
                'event_type': event.event_type,
                'aggregate_id': event.aggregate_id,
                'aggregate_type': event.aggregate_type,
                'event_data': event.event_data,
                'sequence_number': event.sequence_number,
                'created_at': event.created_at.isoformat(),
            }
            for event in events
        ]
    
    async def send_event(self, event_data):
        """Send event to client (called by event handlers)."""
        await self.send(text_data=json.dumps({
            'type': 'event',
            'event': event_data
        }))




