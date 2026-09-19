import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 100,
  duration: '5s',
};

export default function () {
  const url = 'http://localhost:8000/ledger/transaction';
  const payload = JSON.stringify({
    user_id: 'test_user_1',
    amount: 10.0,
    entry_type: 'WITHDRAWAL',
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const res = http.post(url, payload, params);

  check(res, {
    'status is 200 or 400': (r) => r.status === 200 || r.status === 400,
  });
}