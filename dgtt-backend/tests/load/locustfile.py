"""Kiểm thử tải (NFR-01, NFR-03) bằng Locust.

Chuẩn bị: chạy backend + `python -m seeds.seed_dev` (tạo phiên PDG-1 với bidder1, bidder2).
Chạy:  locust -f tests/load/locustfile.py --host http://localhost:8000
Đặt biến SESSION_ID, BIDDERS (mặc định "bidder1,bidder2") nếu cần.
"""

import itertools
import os
import random
import uuid

from locust import HttpUser, between, task

SESSION_ID = int(os.getenv("SESSION_ID", "1"))
BIDDERS = itertools.cycle(os.getenv("BIDDERS", "bidder1,bidder2").split(","))
PASSWORD = os.getenv("PASSWORD", "Matkhau@123")


class BidderUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self) -> None:
        response = self.client.post("/api/v1/auth/login", json={"login": next(BIDDERS), "password": PASSWORD})
        self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    @task(3)
    def view_state(self) -> None:
        self.client.get(f"/api/v1/sessions/{SESSION_ID}/state", headers=self.headers, name="/sessions/[id]/state")

    @task(1)
    def place_bid(self) -> None:
        state = self.client.get(
            f"/api/v1/sessions/{SESSION_ID}/state", headers=self.headers, name="/sessions/[id]/state"
        ).json()
        amount = int(float(state["minimum_next_bid"])) + random.choice([0, 0, 1]) * int(float(state["bid_increment"]))
        self.client.post(
            f"/api/v1/sessions/{SESSION_ID}/bids",
            headers=self.headers,
            json={"amount": amount, "transaction_code": uuid.uuid4().hex},
            name="/sessions/[id]/bids",
        )
