"""Shared pytest configuration for all test suites.

Sets API_KEY before any test module is imported so:
- the startup lifespan guard (if invoked) finds a valid key
- per-request require_api_key checks pass when the auth header is present

Test clients must still pass the matching header explicitly:
    TestClient(app, headers={"X-Api-Key": "test-key"})
"""

import os


def pytest_configure(config):
    os.environ.setdefault("API_KEY", "test-key")
