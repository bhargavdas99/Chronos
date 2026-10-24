import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    distributed_ledger_stress: {
      executor: "ramping-arrival-rate",
      startRate: 20,
      timeUnit: "1s",
      preAllocatedVUs: 50,
      maxVUs: 300,
      stages: [
        { duration: "10s", target: 100 },
        { duration: "30s", target: 300 },
        { duration: "20s", target: 300 },
        { duration: "10s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500", "p(99)<1500"],
  },
};

const BASE_URL = "http://localhost";
const USER_POOL_SIZE = 50;

// Valid RFC4122 version 4 UUID generator for k6's JS runtime
function uuidv4() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// 10 fixed valid UUIDs for testing duplicate collisions
const COLLIDING_KEYS = [
  "00000000-0000-4000-a000-000000000001",
  "00000000-0000-4000-a000-000000000002",
  "00000000-0000-4000-a000-000000000003",
  "00000000-0000-4000-a000-000000000004",
  "00000000-0000-4000-a000-000000000005",
  "00000000-0000-4000-a000-000000000006",
  "00000000-0000-4000-a000-000000000007",
  "00000000-0000-4000-a000-000000000008",
  "00000000-0000-4000-a000-000000000009",
  "00000000-0000-4000-a000-000000000010",
];

export function setup() {
  const params = {
    headers: { "Content-Type": "application/json" },
  };

  for (let i = 1; i <= USER_POOL_SIZE; i++) {
    const payload = JSON.stringify({
      user_id: `usr_dist_${i}`,
      initial_balance: 1000000.0,
    });
    http.post(`${BASE_URL}/accounts`, payload, params);
  }
}

export default function () {
  const amount = parseFloat((Math.random() * 49 + 1).toFixed(2));
  const randomUserIndex = Math.floor(Math.random() * USER_POOL_SIZE) + 1;
  const userId = `usr_dist_${randomUserIndex}`;

  const isDuplicateKey = Math.random() < 0.2;
  const idempotencyKey = isDuplicateKey
    ? COLLIDING_KEYS[Math.floor(Math.random() * COLLIDING_KEYS.length)]
    : uuidv4();

  const payload = JSON.stringify({
    user_id: userId,
    amount: amount,
    entry_type: "DEPOSIT",
    idempotency_key: idempotencyKey,
    reference_id: null,
  });

  const params = {
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
  };

  const res = http.post(`${BASE_URL}/ledger/transaction`, payload, params);

  check(res, {
    "Status 200 OK": (r) => r.status === 200,
    "Valid Payload Return": (r) => {
      try {
        const body = JSON.parse(r.body);
        return (
          body.new_balance !== undefined || body.amount_processed !== undefined
        );
      } catch (e) {
        return false;
      }
    },
  });

  sleep(0.01);
}
