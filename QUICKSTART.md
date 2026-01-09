# Quick Start Guide

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ (for local development)

## Getting Started

### 1. Start Services

```bash
cd ledger_safe_backend
docker-compose up -d
```

This will start:
- PostgreSQL database
- Redis
- Django web server
- Celery worker
- Celery beat

### 2. Run Migrations

```bash
docker-compose exec web python manage.py migrate
```

### 3. Initialize Required Accounts

```bash
docker-compose exec web python manage.py init_accounts
```

This creates the required accounts:
- `CASH_001`: Cash Account (Asset)
- `PAYOUT_LIABILITY_001`: Payout Liability Account (Liability)

### 4. Create Superuser (Optional)

```bash
docker-compose exec web python manage.py createsuperuser
```

### 5. Access the System

- **API**: http://localhost:8000/api/payouts/
- **Admin**: http://localhost:8000/admin/
- **WebSocket**: ws://localhost:8000/ws/events/

## Testing the API

### Create a Payout

```bash
curl -X POST http://localhost:8000/api/payouts/ \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "test-key-001",
    "amount": "100.00",
    "recipient_account": "account-123",
    "recipient_name": "John Doe",
    "description": "Test payout"
  }'
```

### Get Payout Status

```bash
curl http://localhost:8000/api/payouts/{payout_id}/
```

### Test Idempotency

Send the same request multiple times with the same `idempotency_key`. You should get the same payout ID back.

## Running Tests

```bash
docker-compose exec web pytest
```

Or locally:

```bash
pytest
```

## Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web
docker-compose logs -f celery
```

## Stopping Services

```bash
docker-compose down
```

To remove volumes (database data):

```bash
docker-compose down -v
```

## Local Development (Without Docker)

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ledger_safe
export REDIS_URL=redis://localhost:6379/0
export CELERY_BROKER_URL=redis://localhost:6379/0
export CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

3. Run migrations:
```bash
python manage.py migrate
```

4. Initialize accounts:
```bash
python manage.py init_accounts
```

5. Start Celery worker (in separate terminal):
```bash
celery -A ledger_safe worker --loglevel=info
```

6. Start Django server:
```bash
python manage.py runserver
```




