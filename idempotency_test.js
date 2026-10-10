import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    idempotency_stampede: {
      executor: 'per-vu-iterations',
      vus: 50,              // 50 concurrent VUs
      iterations: 1,        // 1 request per VU at the exact same instant
      maxDuration: '10s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'], // 100% of requests must succeed
  },
};

const BASE_URL = 'http://localhost';
const TARGET_USER_ID = 'usr_idempotency_test_fixed';
const SHARED_IDEMPOTENCY_KEY = 'idem_key_stampede_10000';

export function setup() {
  const payload = JSON.stringify({
    user_id: TARGET_USER_ID,
    initial_balance: '100.0000',
  });

  const params = {
    headers: { 'Content-Type': 'application/json' },
  };

  const res = http.post(`${BASE_URL}/accounts`, payload, params);
  check(res, { 'Account Seeded': (r) => r.status === 201 || r.status === 400 });
}

export default function () {
  const payload = JSON.stringify({
    user_id: TARGET_USER_ID,
    amount: '10.0000',
    entry_type: 'WITHDRAWAL',
  });

  const params = {
    headers: { 
      'Content-Type': 'application/json',
      'Idempotency-Key': SHARED_IDEMPOTENCY_KEY,
    },
  };

  const res = http.post(`${BASE_URL}/ledger/transaction`, payload, params);

  check(res, {
    'Status 200 OK': (r) => r.status === 200,
  });

  sleep(0.01);
}