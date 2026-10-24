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
     [ Redis (Idempotency Cache) ]                       [ PgBouncer Pooler ]
     *(Fail-Open Graceful Degradation)*                         │
                                                                ▼
                                                        [ PostgreSQL 15 ]
                                                                │
                                         ┌──────────────────────┴────────────────────┐
                                         ▼                                           ▼
                                  [ Apache Kafka ]                            [ RabbitMQ ]
                              (Event Streaming / Log)                    (Async Background Tasks)

```

---

## Project Structure

```text
chronos/
├── app/                  # FastAPI core application (api routes, schemas, core config)
├── config/               # Infrastructure configurations (nginx.conf, prometheus.yml)
├── k6_scripts/           # Dual-profile k6 load testing suites (Distributed & Contention)
├── Dockerfile            # Container definition for FastAPI app replicas
├── docker-compose.yml    # Full-stack multi-container orchestration
├── requirements.txt      # Pinned, conflict-free dependency definitions
├── schema.sql            # PostgreSQL database schema and initial tables
├── worker.py             # Asynchronous RabbitMQ/Kafka background consumer worker
└── README.md

```

---

## Performance & Proof-of-Work (Dual-Profile Load Testing)

Chronos is rigorously validated using **k6** across two distinct performance profiles, backed by real-time metric collection via **Prometheus** and dashboard visualization via **Grafana**.

### 1. Distributed Scale Profile (`k6_scripts/load_test_distributed.js`)

Simulates a high-volume retail banking environment by partitioning writes across a pool of independent accounts to test raw throughput and connection pooling.

* **Throughput:** Sustained ~200 RPS across 14,000+ total transactions.
* **Tail Latency:** Achieved a blistering **p(95) of 16.48ms** and **p(99) of 22.45ms**.
* **Failure Rate:** **0.00% failure rate** with 100% data integrity verified.

### 2. Hot-Row Contention Profile (`k6_scripts/load_test_contention.js`)

Tests extreme concurrency limits against a single entity row (`usr_k6_stress_v2`) using row-level locks (`SELECT FOR UPDATE`).

* **Data Safety:** Proves that even under fierce lock contention, database serialization successfully prevents race conditions, deadlocks, and double-spending with **0.00% data corruption**.

### Real-Time Observability (Grafana Dashboard)

Real-time metric collection via Prometheus visualized through Grafana during peak load testing:

![Chronos Grafana Production Metrics](./assets/grafana-metrics.png)

---

## Resilience & Chaos Engineering

Financial systems must survive infrastructure failures gracefully. Chronos implements robust fault-tolerance mechanisms:

1. **Fail-Open Idempotency:** If the Redis cache/locking layer experiences an outage, the idempotency layer catches the exception, logs a warning, and safely fails-open—allowing requests to process directly through the database without returning `500 Internal Server Errors` to clients.
2. **Seamless Load Balancer Failover:** Nginx load balances traffic across multiple FastAPI container replicas (`app-1`, `app-2`, `app-3`), ensuring zero downtime during individual container scaling or restarts.

---

## Core Engineering Decisions

1. **Bypasting ORMs for Raw AsyncPG:**
* Heavy ORMs introduce hidden query overhead and abstraction leaks when managing fine-grained transaction boundaries. Using **AsyncPG with raw SQL** gives direct control over transaction scopes, query execution plans, and explicit row locking.


2. **Idempotency with Fail-Open Safety:**
* Financial APIs require strict idempotency to prevent duplicate charges or transfers from client retries. Chronos uses **Redis** to track request fingerprints, paired with a fail-open wrapper to guarantee high availability even during cache degradation.


3. **Transaction Pooling via PgBouncer:**
* Direct high-concurrency connections can overwhelm PostgreSQL's connection limit. PgBouncer multiplexes client connections efficiently, preventing connection storms and keeping database memory footprints stable.



---

## Quickstart & Local Setup

Get the entire containerized stack up and running in under 2 minutes.

### Prerequisites

* [Docker & Docker Compose](https://docs.docker.com/get-docker/) installed on your machine.
* [k6](https://k6.io/) installed locally (if running load tests outside Docker).

### 1. Clone the Repository

```bash
git clone [https://github.com/your-username/chronos-ledger-engine.git](https://github.com/your-username/chronos-ledger-engine.git)
cd chronos-ledger-engine

```

### 2. Spin Up the Stack

Build and start all services (FastAPI replicas, Nginx, PostgreSQL, PgBouncer, Redis, Kafka, RabbitMQ, Prometheus, and Grafana):

```bash
docker compose up --build -d

```

### 3. Initialize Database Schema

Run the `schema.sql` script to create the required tables (`accounts`, `ledger_entries`) and performance indexes inside your PostgreSQL container:

```bash
docker exec -i chronos-postgres psql -U postgres -d chronos_db < schema.sql

```

*(Note: Replace `chronos-postgres`, `postgres`, and `chronos_db` with your actual container name, username, and database name from your environment configuration if they differ).*

### 4. Verify Health & Observability

* **API Gateway (Nginx):** `http://localhost/ledger/transaction`
* **Prometheus UI:** `http://localhost:9090`
* **Grafana Dashboards:** `http://localhost:3000` *(Default login: `admin` / `admin`)*

### 5. Run k6 Load Tests

**Run the Distributed Throughput Benchmark:**

```bash
docker run --rm -i --net=host grafana/k6 run - < k6_scripts/load_test_distributed.js

```

**Run the Hot-Row Contention Profile:**

```bash
docker run --rm -i --net=host grafana/k6 run - < k6_scripts/load_test_contention.js

```