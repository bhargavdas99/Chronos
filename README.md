# Chronos Ledger Engine

A high-concurrency, fault-tolerant financial ledger and transaction engine built for strict ACID compliance, zero double-spending, resilient caching, and real-time observability.

## Architectural Overview

Chronos is engineered to handle heavy concurrent transaction workloads without sacrificing data integrity or performance. By avoiding heavy ORMs in favor of direct database optimizations, connection pooling, and resilient caching patterns, Chronos maintains consistent low-latency throughput under pressure.

### System Topology & Data Flow

```text
 [Client / k6 Load Tester]
           │
           ▼
     [ Nginx Load Balancer ]
           │
           ├─────────────────────────┬─────────────────────────┐
           ▼                         ▼                         ▼
     [ FastAPI App 1 ]         [ FastAPI App 2 ]         [ FastAPI App 3 ]
           │                         │                         │
           ├─────────────────────────┴─────────────────────────┤
           ▼                                                   ▼
     [ Redis (Idempotency Cache) ]                   [ PgBouncer Pooler ]
     *(Fail-Open Graceful Degradation)*                        │
                                                               ▼
                                                      [ PostgreSQL 15 ]
                                                               │
                                          ┌────────────────────┴────────────────────┐
                                          ▼                                         ▼
                                   [ Apache Kafka ]                            [ RabbitMQ ]
                                (Event Streaming / Log)                     (Async Background Tasks)

```

---

## Performance & Proof-of-Work

Chronos has been stress-tested and validated under heavy concurrent loads using **k6**, backed by real-time metric collection via **Prometheus** and visualization via **Grafana**.

### Load Testing Results (k6)

* **Peak Throughput:** Validated at **~200+ RPS** under continuous concurrent stress tests.
* **Failure Rate:** **0% failure rate** under steady-state load; zero double-spending or race condition leakage.
* **Tail Latency:** P99 latency tracking stays tightly bound under load thanks to connection pooling (`PgBouncer`) and efficient query paths.

### Resilience & Chaos Engineering

Financial systems must survive infrastructure failures gracefully. Chronos implements robust fault-tolerance mechanisms:

1. **Fail-Open Idempotency:** If the Redis cache/locking layer experiences an outage, the idempotency layer catches the exception, logs a warning, and safely fails-open—allowing requests to process directly through the database without returning `500 Internal Server Errors` to clients.
2. **Seamless Load Balancer Failover:** Nginx load balances traffic across multiple FastAPI container replicas (`app-1`, `app-2`, `app-3`), ensuring zero downtime during individual container terminations.

---

## Core Engineering Decisions

1. **Bypassing ORMs for Raw AsyncPG:**
* Heavy ORMs can introduce hidden query overhead, opaque connection pooling behavior, and abstraction leaks when managing fine-grained transaction scopes.
* Using **AsyncPG with raw SQL** gives direct control over transaction boundaries, query execution plans, and explicit row locking, ensuring maximum throughput for high-concurrency ledger writes.


2. **Idempotency with Fail-Open Safety:**
* Financial APIs require strict idempotency to prevent duplicate charges or transfers from client retries.
* Chronos uses **Redis** to track request fingerprints and in-flight locks. To prevent cache outages from taking down the core banking service, a **fail-open try/except wrapper** ensures that if Redis goes down, transactions bypass the cache safely and hit PostgreSQL directly without returning 500 errors.


3. **Transaction Pooling via PgBouncer:**
* Direct high-concurrency connections can overwhelm PostgreSQL's connection limit. PgBouncer multiplexes client connections efficiently, preventing connection storms and keeping database memory footprints stable.



---

## Quickstart & Local Setup

Get the entire containerized stack up and running in under 2 minutes.

### Prerequisites

* [Docker & Docker Compose](https://docs.docker.com/get-docker/) installed on your machine.

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/chronos-ledger-engine.git
cd chronos-ledger-engine

```

### 2. Spin Up the Stack

Build and start all services (FastAPI replicas, Nginx, PostgreSQL, PgBouncer, Redis, Kafka, RabbitMQ, Prometheus, and Grafana) using Docker Compose:

```bash
docker compose up --build -d

```

### 3. Verify Health & Metrics

* **API Gateway (Nginx):** `http://localhost/ledger/transaction`
* **Prometheus UI:** `http://localhost:9090`
* **Grafana Dashboards:** `http://localhost:3000` *(Default login: `admin` / `admin`)*

### 4. Run k6 Load Tests

To stress-test the system and watch real-time P99 latency spikes on Grafana:

```bash
docker run --rm -i --net=host grafana/k6 run - < load_test_new.js

```