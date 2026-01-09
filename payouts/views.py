"""
Payout API Views

REST API endpoints for payout operations with idempotency support.
"""

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from decimal import Decimal, InvalidOperation
from payouts.models import Payout
from payouts.services import PayoutService
from payouts.tasks import process_payout_task


@api_view(['POST'])
def create_payout(request):
    """
    Create a payout request.
    
    POST /api/payouts/
    
    Body:
    {
        "idempotency_key": "unique-key-123",
        "amount": "100.00",
        "recipient_account": "account-123",
        "recipient_name": "John Doe",
        "description": "Payment for services",
        "metadata": {}
    }
    
    Returns:
        201 Created: Payout created
        200 OK: Payout already exists (idempotent)
        400 Bad Request: Invalid input
    """
    try:
        idempotency_key = request.data.get('idempotency_key')
        if not idempotency_key:
            raise ValidationError({'idempotency_key': 'This field is required'})
        
        amount = request.data.get('amount')
        if not amount:
            raise ValidationError({'amount': 'This field is required'})
        
        try:
            amount = Decimal(str(amount))
            if amount <= 0:
                raise ValidationError({'amount': 'Amount must be positive'})
        except (InvalidOperation, ValueError):
            raise ValidationError({'amount': 'Invalid amount format'})
        
        recipient_account = request.data.get('recipient_account')
        if not recipient_account:
            raise ValidationError({'recipient_account': 'This field is required'})
        
        recipient_name = request.data.get('recipient_name', '')
        description = request.data.get('description', '')
        metadata = request.data.get('metadata', {})
        
        # Create payout (idempotent)
        payout = PayoutService.initiate_payout(
            idempotency_key=idempotency_key,
            amount=amount,
            recipient_account=recipient_account,
            recipient_name=recipient_name,
            description=description,
            metadata=metadata
        )
        
        # Process payout asynchronously
        process_payout_task.delay(str(payout.id))
        
        response_data = {
            'id': str(payout.id),
            'idempotency_key': payout.idempotency_key,
            'amount': str(payout.amount),
            'currency': payout.currency,
            'recipient_account': payout.recipient_account,
            'status': payout.status,
            'created_at': payout.created_at.isoformat(),
        }
        
        # Return 201 if created, 200 if already existed
        if payout.status == 'PENDING':
            return Response(response_data, status=status.HTTP_201_CREATED)
        else:
            return Response(response_data, status=status.HTTP_200_OK)
            
    except ValidationError as e:
        return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_payout(request, payout_id):
    """
    Get payout details.
    
    GET /api/payouts/{payout_id}/
    """
    try:
        payout = Payout.objects.get(id=payout_id)
        response_data = {
            'id': str(payout.id),
            'idempotency_key': payout.idempotency_key,
            'amount': str(payout.amount),
            'currency': payout.currency,
            'recipient_account': payout.recipient_account,
            'recipient_name': payout.recipient_name,
            'description': payout.description,
            'status': payout.status,
            'ledger_transaction_id': payout.ledger_transaction_id,
            'external_payout_id': payout.external_payout_id,
            'error_message': payout.error_message,
            'created_at': payout.created_at.isoformat(),
            'updated_at': payout.updated_at.isoformat(),
            'processed_at': payout.processed_at.isoformat() if payout.processed_at else None,
        }
        return Response(response_data, status=status.HTTP_200_OK)
    except Payout.DoesNotExist:
        return Response(
            {'error': 'Payout not found'},
            status=status.HTTP_404_NOT_FOUND
        )
