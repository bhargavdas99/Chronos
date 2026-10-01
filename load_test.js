import http from 'k6/http';
import { check, sleep } from 'k6';

// Test topology configuration
export const options = {
  scenarios: {
    // High concurrency stress scenario
    ledger_stress: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 200,
      stages: [
        { duration: '10s', target: 50 },  // Warm-up to 50 req/s
        { duration: '30s', target: 200 }, // Ramp-up to 200 req/s
        { duration: '20s', target: 200 }, // Hold steady at 200 req/s
        { duration: '10s', target: 0 },   // Cool-down
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],   // Less than 1% HTTP failures allowed
    http_req_duration: ['p(95)<100'], // 95% of requests must complete under 100ms
  },
};

const BASE_URL = 'http://localhost';

export function setup() {
  // Pre-seed a test user account before load generation begins
  const payload = JSON.stringify({
    user_id: 'usr_k6_stress',
    initial_balance: '100000.0000',
  });

  const params = {
    headers: { 'Content-Type': 'application/json' },
  };

  const res = http.post(`${BASE_URL}/accounts`, payload, params);
  check(res, { 'Account Created or Exists': (r) => r.status === 201 || r.status === 400 });
}

export default function () {
  // Randomize transaction amounts between $1.00 and $50.00
  const amount = (Math.random() * 49 + 1).toFixed(4);

  const payload = JSON.stringify({
    user_id: 'usr_k6_stress',
    amount: amount,
    entry_type: 'DEPOSIT',
  });

  const params = {
    headers: { 'Content-Type': 'application/json' },
  };

  const res = http.post(`${BASE_URL}/ledger/transaction`, payload, params);

  // Assert expected HTTP responses
  check(res, {
    'Transaction Status 200': (r) => r.status === 200,
  });

  // Micro-think time between user iterations
  sleep(0.05);
}