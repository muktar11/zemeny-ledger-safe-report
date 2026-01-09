# Ledger-Safe Report and Payout Engine

A correctness-critical financial backend system implementing a double-entry ledger and exactly-once payout engine. This system is designed to handle money-critical operations with absolute guarantees around data integrity, fault tolerance, and auditability.

## Table of Contents

1. [System Overview](#system-overview)
2. [System Invariants](#system-invariants)
3. [Architecture](#architecture)
4. [Core Components](#core-components)
5. [Failure Model and Assumptions](#failure-model-and-assumptions)
6. [Failure Scenarios and Handling](#failure-scenarios-and-handling)
7. [Database Design](#database-design)
8. [API Endpoints](#api-endpoints)
9. [Testing](#testing)
10. [Deployment](#deployment)
11. [Architectural Trade-offs](#architectural-trade-offs)
12. [Known Scalability Limits](#known-scalability-limits)
13. [Planned Refactors and Improvements](#planned-refactors-and-improvements)

## System Overview

The Ledger-Safe Report and Payout Engine is a Django-based backend system that provides:

- **Double-Entry Ledger**: True double-entry bookkeeping with database-enforced invariants
- **Exactly-Once Payouts**: Idempotent payout processing with guaranteed exactly-once execution
- **Event Stream**: Ordered, idempotent event stream for state changes
- **Read Models**: Denormalized read models derived from source-of-truth data
- **Real-Time Updates**: WebSocket-based event streaming for real-time state visibility

### Technology Stack

- **Django 4.2.7**: Web framework
- **Django REST Framework**: API layer
- **PostgreSQL 15**: Primary database
- **Redis 7**: Message broker and cache
- **Celery 5.3.4**: Async task processing
- **Django Channels**: WebSocket support
- **Docker & Docker Compose**: Containerization

## System Invariants

The following invariants must **never** be violated:

1. **Financial Data Immutability**: Ledger entries and transactions are immutable once created. No updates or deletions are permitted.

2. **Double-Entry Balance**: Every transaction must generate exactly two ledger entries that balance to zero. This is enforced at the database level.

3. **Idempotency**: All operations must be idempotent. Duplicate requests with the same idempotency key must produce identical results.

4. **Event Ordering**: Events are assigned monotonically increasing sequence numbers. Event replay must preserve order.

5. **State Derivation**: All read models must be derivable from source-of-truth data (ledger entries and events). Read models can be rebuilt from scratch.

6. **Exactly-Once Payouts**: Payouts must execute exactly once, even under failure conditions (API retries, task retries, worker crashes, network failures).

7. **Transactional Integrity**: Financial operations must be atomic. Partial state is never acceptable.

8. **No Eventually Consistent Financial Logic**: Financial operations must be immediately consistent. Eventual consistency is not acceptable for money-critical operations.

## Architecture

### High-Level Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       │ HTTP/WebSocket
       │
┌──────▼─────────────────────────────────────┐
│         Django Application                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │   API    │  │ Services │  │  Tasks   │  │
│  │  Views   │  │          │  │ (Celery) │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │             │             │        │
│  ┌────▼─────────────▼─────────────▼─────┐ │
│  │         Business Logic Layer          │ │
│  └────┬─────────────────────────────────┘ │
└───────┼───────────────────────────────────┘
        │
        │
┌───────▼───────────────────────────────────┐
│         PostgreSQL (Source of Truth)       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ Ledger   │  │ Payouts  │  │ Events   │ │
│  │ Models   │  │ Models   │  │ Models   │ │
│  └──────────┘  └──────────┘  └──────────┘ │
│  ┌──────────┐                             │
│  │ Read     │                             │
│  │ Models   │                             │
│  └──────────┘                             │
└───────────────────────────────────────────┘
        │
        │
┌───────▼───────────────────────────────────┐
│         Redis (Message Broker)            │
│  ┌──────────┐  ┌──────────┐             │
│  │ Celery   │  │ Channels │             │
│  │ Broker   │  │ Layer    │             │
│  └──────────┘  └──────────┘             │
└───────────────────────────────────────────┘
```

### Component Responsibilities

1. **Ledger App**: Manages double-entry ledger entries and transactions
2. **Payouts App**: Handles payout requests with exactly-once guarantees
3. **Events App**: Manages event stream and WebSocket delivery
4. **Read Models App**: Maintains denormalized read models for queries

## Core Components

### 1. Double-Entry Ledger

The ledger system enforces double-entry bookkeeping at the database level:

- **Transaction Model**: Represents a financial transaction that must have exactly 2 entries
- **LedgerEntry Model**: Immutable entries that cannot be updated or deleted
- **Account Model**: Represents accounts in the ledger (Asset, Liability, Equity, Revenue, Expense)

**Key Features**:
- Database constraints ensure entries balance to zero
- Immutability enforced at model level (save/delete overridden)
- Atomic transaction creation using database transactions

### 2. Exactly-Once Payout Engine

The payout system guarantees exactly-once execution using:

- **Idempotency Keys**: Unique keys provided by clients
- **Database-Level Locking**: `select_for_update()` prevents concurrent processing
- **State Machine**: Payouts transition through states (PENDING → PROCESSING → COMPLETED/FAILED)

**Key Features**:
- `get_or_create_pending()` atomically creates or retrieves payouts
- `mark_processing()` uses row-level locking to prevent duplicate processing
- Celery tasks are idempotent and can be safely retried

### 3. Event Stream

Events provide an audit trail and enable state derivation:

- **Event Model**: Immutable events with sequence numbers
- **Ordering**: Sequence numbers ensure events are ordered
- **Idempotency**: Events with same `event_id` are deduplicated

**Key Features**:
- Sequence numbers are assigned atomically
- Events are immutable (save/delete overridden)
- Events can be replayed to reconstruct state

### 4. Read Models

Read models are denormalized views optimized for queries:

- **AccountBalance**: Current balance for each account
- **PayoutSummary**: Summary of payout information
- **LedgerTransactionSummary**: Summary of transaction information

**Key Features**:
- Rebuildable from source data
- Updated asynchronously via Celery tasks
- Optimized indexes for common queries

### 5. WebSocket Event Streaming

Real-time event delivery via WebSocket:

- **EventConsumer**: WebSocket consumer for event streaming
- **Non-Authoritative**: WebSocket delivery is NOT a source of truth
- **Replay Support**: Clients can request events after a sequence number

**Important**: WebSocket delivery is for real-time visibility only. Authoritative state resides in PostgreSQL.

## Failure Model and Assumptions

### Failure Assumptions

1. **Network Failures**: Network can fail at any time, causing:
   - API requests to be lost or duplicated
   - Task messages to be lost or duplicated
   - WebSocket connections to drop

2. **Process Failures**: Processes can crash at any point:
   - After database commit but before event emission
   - During task execution
   - During external API calls

3. **Database Failures**: Database can:
   - Become temporarily unavailable
   - Experience connection timeouts
   - Roll back transactions

4. **Redis Failures**: Redis can:
   - Restart, losing in-memory state
   - Become temporarily unavailable
   - Drop messages

5. **External Service Failures**: External payout services can:
   - Timeout
   - Return errors
   - Process requests multiple times (idempotency required)

### Design Principles

1. **Fail-Safe Defaults**: System defaults to safe states (no money lost)
2. **Idempotency Everywhere**: All operations are idempotent
3. **Atomic Operations**: Critical operations are atomic
4. **Audit Trail**: All state changes are logged as events
5. **Replay Capability**: State can be reconstructed from events

## Failure Scenarios and Handling

### Scenario 1: Worker Failure After Database Commit But Before Event Emission

**Problem**: A worker crashes after committing a transaction to the database but before emitting the event.

**System Behavior**:
- The transaction exists in the database (source of truth)
- The event may be missing
- Read models may be inconsistent

**Safety Guarantees**:
- No financial data is lost (transaction is committed)
- The system can detect missing events by comparing database state with event stream
- Read models can be rebuilt from database state

**Recovery Strategy**:
1. Run a reconciliation job that compares database state with events
2. Generate missing events from database state
3. Rebuild read models from database state
4. Event sequence numbers are assigned based on creation time

**Implementation**: Events are created within the same database transaction as the source data. If the transaction commits, the event is guaranteed to exist. If the worker crashes, the transaction rolls back and no partial state exists.

### Scenario 2: Event Emission Followed by Transaction Rollback

**Problem**: An event is emitted but the database transaction rolls back.

**System Behavior**:
- Event exists in event stream
- Source data does not exist in database
- Read models may be inconsistent

**Safety Guarantees**:
- Financial data is not corrupted (transaction rolled back)
- Event can be ignored during replay (event references non-existent aggregate)

**Recovery Strategy**:
1. Events are created within the same database transaction as source data
2. If transaction rolls back, event creation also rolls back
3. No orphaned events can exist
4. During event replay, verify aggregate exists before processing

**Implementation**: Events are created using `transaction.atomic()` context manager. If the transaction fails, both source data and event are rolled back atomically.

### Scenario 3: Redis Restart During Message Broadcast

**Problem**: Redis restarts while broadcasting WebSocket messages.

**System Behavior**:
- WebSocket messages may be lost
- Clients may miss events
- Event stream in database is unaffected

**Safety Guarantees**:
- No financial data is lost (events are in database)
- Clients can replay events from database
- WebSocket is not a source of truth

**Recovery Strategy**:
1. Clients detect connection loss and reconnect
2. Clients request events after their last known sequence number
3. Events are replayed from database (authoritative source)
4. WebSocket delivery is best-effort only

**Implementation**: WebSocket consumers handle disconnections gracefully. Clients can request events using `get_latest` message with a sequence number. Events are always read from PostgreSQL, not Redis.

### Scenario 4: Out-of-Order WebSocket Delivery

**Problem**: WebSocket messages arrive out of order due to network conditions.

**System Behavior**:
- Events may be delivered out of sequence
- Client state may be temporarily inconsistent

**Safety Guarantees**:
- Database state is always correct (source of truth)
- Events have sequence numbers for ordering
- Clients can reorder events using sequence numbers

**Recovery Strategy**:
1. Clients buffer events and sort by sequence number
2. Clients process events in order
3. If gaps are detected, clients request missing events
4. WebSocket delivery is not authoritative

**Implementation**: Events include `sequence_number` field. Clients should buffer and sort events before processing. WebSocket consumer provides `get_latest` endpoint for gap filling.

### Scenario 5: Duplicate Task Execution

**Problem**: Celery task is executed multiple times (retry, duplicate message, etc.).

**System Behavior**:
- Task may attempt to process same payout multiple times
- Without idempotency, this could create duplicate ledger entries

**Safety Guarantees**:
- Tasks are idempotent
- Database constraints prevent duplicate processing
- Idempotency keys prevent duplicate payouts

**Recovery Strategy**:
1. Tasks check payout status before processing
2. `mark_processing()` uses row-level locking to prevent concurrent processing
3. Ledger transactions use unique transaction IDs
4. External payout APIs are called with idempotency keys

**Implementation**: 
- `process_payout_task` checks payout status before processing
- `mark_processing()` uses `select_for_update()` for atomic state transition
- External payout APIs receive idempotency keys for deduplication

### Scenario 6: Partial External Payout Failure

**Problem**: External payout API fails after ledger entries are created.

**System Behavior**:
- Ledger entries exist (money deducted)
- External payout may not have been initiated
- Payout status may be inconsistent

**Safety Guarantees**:
- Ledger entries are immutable (cannot be deleted)
- Payout status tracks failure
- System can retry external payout
- Audit trail exists for reconciliation

**Recovery Strategy**:
1. Payout status is set to FAILED
2. Error message is recorded
3. Retry count is incremented
4. Manual review process for failed payouts
5. Reconciliation job identifies discrepancies

**Implementation**:
- External payout is initiated in separate task (`initiate_external_payout`)
- If external payout fails, payout is marked as FAILED
- Ledger entries remain (they represent the financial reality)
- Manual reconciliation process handles edge cases

## Database Design

### Indexing Strategy

The system uses strategic indexes for performance at scale:

1. **Ledger Entries**:
   - `(transaction_id, created_at)`: Fast transaction lookups
   - `(account_id, created_at)`: Fast account history
   - `(account_id, entry_type, created_at)`: Optimized balance queries

2. **Payouts**:
   - `(idempotency_key)`: Unique constraint for idempotency
   - `(status, created_at)`: Fast status-based queries
   - `(ledger_transaction_id)`: Link to ledger

3. **Events**:
   - `(sequence_number)`: Ordered event retrieval
   - `(aggregate_type, aggregate_id, created_at)`: Aggregate history
   - `(event_type, created_at)`: Event type filtering

### Pagination

The system uses **cursor-based pagination** (not OFFSET) for scalability:

- Cursor pagination uses `created_at` timestamps and IDs
- Avoids performance degradation with large datasets
- Implemented via Django REST Framework's `CursorPagination`

### Raw SQL Usage

For large-scale balance calculations, raw SQL is used:

```python
# Example: Calculate account balance using raw SQL
balance = LedgerEntry.objects.raw("""
    SELECT 
        account_id,
        SUM(CASE 
            WHEN entry_type = 'DEBIT' THEN amount 
            ELSE -amount 
        END) as balance
    FROM ledger_entries
    WHERE account_id = %s
    GROUP BY account_id
""", [account_id])
```

This avoids loading millions of rows into memory and leverages database aggregation.

### Constraints

Database-level constraints enforce invariants:

1. **Ledger Entry Amount**: `CHECK (amount >= 0)`
2. **Transaction Balance**: Verified in application code (could be database function)
3. **Idempotency Key**: `UNIQUE` constraint
4. **Event Sequence**: `UNIQUE` constraint on sequence_number

## API Endpoints

### POST /api/payouts/

Create a payout request.

**Request Body**:
```json
{
    "idempotency_key": "unique-key-123",
    "amount": "100.00",
    "recipient_account": "account-123",
    "recipient_name": "John Doe",
    "description": "Payment for services",
    "metadata": {}
}
```

**Response** (201 Created):
```json
{
    "id": "uuid",
    "idempotency_key": "unique-key-123",
    "amount": "100.00",
    "currency": "USD",
    "recipient_account": "account-123",
    "status": "PENDING",
    "created_at": "2024-01-01T00:00:00Z"
}
```

**Idempotency**: If the same `idempotency_key` is used, returns existing payout (200 OK).

### GET /api/payouts/{payout_id}/

Get payout details.

**Response** (200 OK):
```json
{
    "id": "uuid",
    "idempotency_key": "unique-key-123",
    "amount": "100.00",
    "currency": "USD",
    "recipient_account": "account-123",
    "status": "COMPLETED",
    "ledger_transaction_id": "payout_unique-key-123",
    "external_payout_id": "ext_unique-key-123",
    "created_at": "2024-01-01T00:00:00Z",
    "processed_at": "2024-01-01T00:01:00Z"
}
```

## Testing

### Test Coverage

The test suite covers:

1. **Concurrency Tests**: Multiple threads with identical idempotency keys
2. **Task Interruption**: Simulated worker crashes and restarts
3. **Event Replay**: Events can be replayed correctly
4. **Ledger Balance Invariants**: Transactions always balance
5. **Read Model Rebuilds**: Read models can be rebuilt from scratch

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ledger --cov=payouts --cov=events --cov=read_models

# Run specific test file
pytest ledger/tests.py
```

### Test Files

- `ledger/tests.py`: Ledger model and service tests
- `payouts/tests.py`: Payout idempotency and task tests
- `events/tests.py`: Event ordering and idempotency tests
- `read_models/tests.py`: Read model rebuild tests

## Deployment

### Docker Compose

The system is containerized using Docker Compose:

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Run migrations
# Run migrations
docker-compose exec web python manage.py makemigrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser
```

### Services

- **web**: Django application server
- **db**: PostgreSQL database
- **redis**: Redis for Celery and Channels
- **celery**: Celery worker for async tasks
- **celery-beat**: Celery beat for scheduled tasks

### Environment Variables

Set the following environment variables:

- `SECRET_KEY`: Django secret key
- `DEBUG`: Debug mode (False in production)
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `CELERY_BROKER_URL`: Celery broker URL
- `CELERY_RESULT_BACKEND`: Celery result backend URL

## Architectural Trade-offs

### Trade-off 1: Event Emission Within Transaction

**Decision**: Events are created within the same database transaction as source data.

**Rationale**:
- Ensures events and source data are consistent
- Prevents orphaned events
- Simplifies failure handling

**Trade-offs**:
- Slightly longer transaction duration
- Events cannot be emitted if database is unavailable
- Alternative: Event emission after commit (requires outbox pattern)

**Rejected Alternative**: Event emission after commit would require an outbox pattern to ensure events are eventually emitted. This adds complexity and eventual consistency, which is not acceptable for financial operations.

### Trade-off 2: Read Models Updated Synchronously

**Decision**: Read models are updated within the same transaction as source data.

**Rationale**:
- Ensures read models are immediately consistent
- Simplifies failure handling
- No eventual consistency issues

**Trade-offs**:
- Slightly longer transaction duration
- Read model updates can fail and roll back source data
- Alternative: Async read model updates (requires eventual consistency)

**Rejected Alternative**: Async read model updates would introduce eventual consistency, which is not acceptable for financial operations. Read models must be immediately consistent.

### Trade-off 3: WebSocket for Real-Time Updates

**Decision**: WebSocket is used for real-time event streaming, but is not authoritative.

**Rationale**:
- Provides real-time visibility
- Reduces polling load
- Clear separation: database is authoritative

**Trade-offs**:
- WebSocket delivery is not guaranteed
- Clients must handle disconnections
- Alternative: Polling API (simpler but less efficient)

**Rejected Alternative**: Polling would increase server load and latency. WebSocket provides better real-time experience while maintaining clear authority boundaries.

### Trade-off 4: Celery Tasks for External Payouts

**Decision**: External payouts are initiated via Celery tasks.

**Rationale**:
- Prevents long-running HTTP requests
- Enables retry logic
- Separates concerns

**Trade-offs**:
- Adds complexity (message broker, workers)
- Requires idempotency handling
- Alternative: Synchronous external API calls (simpler but blocks requests)

**Rejected Alternative**: Synchronous external API calls would block HTTP requests and make timeout/retry handling difficult. Celery provides better fault tolerance.

## Known Scalability Limits

### Current Limits

1. **Event Sequence Number Generation**: Uses `MAX(sequence_number) + 1`, which can become a bottleneck at very high write rates. **Solution**: Use database sequences or distributed ID generation.

2. **Read Model Rebuilds**: Rebuilding read models from scratch can be slow for large datasets. **Solution**: Incremental updates and background jobs.

3. **WebSocket Connections**: Django Channels can handle thousands of connections, but may need horizontal scaling. **Solution**: Use Redis channel layer for multi-server deployment.

4. **Database Connection Pool**: Default Django connection pool may be insufficient. **Solution**: Use connection pooling (PgBouncer) and increase `CONN_MAX_AGE`.

### Scaling Strategies

1. **Horizontal Scaling**: Add more Django/Celery workers behind a load balancer
2. **Database Read Replicas**: Use read replicas for read-heavy queries
3. **Partitioning**: Partition large tables (events, ledger_entries) by date
4. **Caching**: Cache frequently accessed read models in Redis
5. **Message Queue**: Use RabbitMQ or Kafka for higher throughput than Redis

## Planned Refactors and Improvements

### Short-Term (1-3 months)

1. **Database Sequences**: Replace `MAX(sequence_number) + 1` with PostgreSQL sequences for better concurrency.

2. **Incremental Read Model Updates**: Instead of rebuilding from scratch, update read models incrementally based on events.

3. **Reconciliation Jobs**: Automated jobs to detect and fix inconsistencies between database and events.

4. **Enhanced Monitoring**: Add metrics for payout success rates, task execution times, and event lag.

### Medium-Term (3-6 months)

1. **Event Sourcing**: Fully embrace event sourcing pattern with event store as primary source of truth.

2. **CQRS Optimization**: Separate read and write databases for better scalability.

3. **Distributed Tracing**: Add OpenTelemetry for distributed tracing across services.

4. **Advanced Retry Strategies**: Implement exponential backoff and circuit breakers for external API calls.

### Long-Term (6-12 months)

1. **Multi-Region Deployment**: Support multi-region deployment with eventual consistency for non-critical operations.

2. **Stream Processing**: Use Kafka for event streaming and stream processing for read model updates.

3. **Machine Learning**: Add fraud detection and anomaly detection using ML models.

4. **GraphQL API**: Provide GraphQL API for flexible client queries.

## Conclusion

This system is designed with correctness and fault tolerance as primary concerns. Every design decision prioritizes data integrity and system safety over performance or simplicity. The system can handle failures gracefully and provides strong guarantees around financial operations.

The architecture is intentionally conservative, favoring immediate consistency and explicit failure handling over eventual consistency and implicit guarantees. This approach is appropriate for money-critical systems where correctness is non-negotiable.




#   z e m e n y - l e d g e r - s a f e - r e p o r t  
 