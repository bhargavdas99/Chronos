import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    ledger_stress: {
      executor: 'ramping-arrival-rate',
      startRate: 20,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 300,
      stages: [
        { duration: '10s', target: 100 }, // Warm-up to 100 RPS
        { duration: '30s', target: 300 }, // Ramp-up to 300 RPS
        { duration: '20s', target: 300 }, // Hold steady at 300 RPS peak
        { duration: '10s', target: 0 },   // Cool-down
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],   // Less than 1% HTTP failures
    http_req_duration: ['p(95)<500', 'p(99)<1500'], // P95 < 500ms, P99 < 1500ms
  },
};

const BASE_URL = 'http://localhost';

export function setup() {
  // Pre-seed test account
  const payload = JSON.stringify({
    user_id: 'usr_k6_stress_v2',
    initial_balance: 1000000.00,
  });

  const params = {
    headers: { 'Content-Type': 'application/json' },
  };

  const res = http.post(`${BASE_URL}/accounts`, payload, params);
  check(res, { 'Account Created or Exists': (r) => r.status === 201 || r.status === 400 });
}

export default function () {
  const amount = parseFloat((Math.random() * 49 + 1).toFixed(2));

  // 80% Unique Keys (DB + Redis + Kafka + RabbitMQ path)
  // 20% Colliding Keys (Redis Fast Cache / Concurrency Lock path)
  const isDuplicateKey = Math.random() < 0.2;
  const idempotencyKey = isDuplicateKey 
    ? `k6-colliding-key-${Math.floor(Math.random() * 10)}` 
    : `k6-key-${__VU}-${__ITER}-${Date.now()}`;

  const payload = JSON.stringify({
    user_id: 'usr_k6_stress_v2',
    amount: amount,
    entry_type: 'DEPOSIT',
    reference_id: null,
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
  };

  const res = http.post(`${BASE_URL}/ledger/transaction`, payload, params);

  check(res, {
    'Status 200 OK': (r) => r.status === 200,
    'Valid Payload Return': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.new_balance !== undefined || body.amount_processed !== undefined;
      } catch (e) {
        return false;
      }
    },
  });

  sleep(0.01);
}