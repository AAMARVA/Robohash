#!/usr/bin/env python3
"""
Tests for AAMARVA RoboHash service:
- Strict CORS origin allowlist (only https://aamarva.com and https://ais-dev-sy4lhzb3bv4g4mm7spkr5c-89865814157.asia-southeast1.run.app)
- Rejection of unapproved origins (http://aamarva.com, https://evil-aamarva.com, example.com, robohash.org)
- Rate limiting exemption ONLY for approved origins
- Rate limiting enforcement for requests without approved origins
- Set 1 ONLY image generation (even with ?set=set2, ?set=any, /set_set3)
- Deterministic seed generation
- Zero outbound network calls (no robohash.org, no gravatar, fully self-sustaining)
"""

import io
import os
import unittest
from unittest.mock import patch
from PIL import Image, ImageChops

import tornado.testing
import tornado.web

from robohash.webfront import (
    APPROVED_ORIGINS,
    MainHandler,
    ImgHandler,
    SafeStaticFileHandler,
    rate_limiter,
)
from robohash import Robohash


class TestRobohashService(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        settings = {
            "static_path": os.path.join(os.path.dirname(os.path.dirname(__file__)), "robohash", "static"),
        }
        return tornado.web.Application([
            (r'/(crossdomain\.xml)', SafeStaticFileHandler, {"path": os.path.join(os.path.dirname(os.path.dirname(__file__)), "robohash", "static/")}),
            (r"/static/(.*)", SafeStaticFileHandler, {"path": os.path.join(os.path.dirname(os.path.dirname(__file__)), "robohash", "static/")}),
            (r"/", MainHandler),
            (r"/(.*)", ImgHandler),
        ], **settings)

    def setUp(self):
        super().setUp()
        rate_limiter.clear()

    # 1. CORS allowlist tests
    def test_aamarva_origin_allowed(self):
        """https://aamarva.com is allowed and receives exact CORS headers."""
        headers = {"Origin": "https://aamarva.com"}
        response = self.fetch("/testrobot.png", headers=headers)
        self.assertEqual(response.code, 200)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "https://aamarva.com")
        self.assertEqual(response.headers.get("Content-Type"), "image/png")

    def test_asia_southeast1_google_run_origin_allowed(self):
        """https://ais-dev-sy4lhzb3bv4g4mm7spkr5c-89865814157.asia-southeast1.run.app is allowed."""
        origin = "https://ais-dev-sy4lhzb3bv4g4mm7spkr5c-89865814157.asia-southeast1.run.app"
        headers = {"Origin": origin}
        response = self.fetch("/testrobot.png", headers=headers)
        self.assertEqual(response.code, 200)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), origin)

    def test_options_preflight_for_approved_origin(self):
        """OPTIONS preflight for approved origin returns 204 and CORS headers."""
        headers = {
            "Origin": "https://aamarva.com",
            "Access-Control-Request-Method": "GET",
        }
        response = self.fetch("/testrobot.png", method="OPTIONS", headers=headers)
        self.assertEqual(response.code, 204)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "https://aamarva.com")
        self.assertIn("GET", response.headers.get("Access-Control-Allow-Methods", ""))

    # 2. CORS rejection tests
    def test_example_com_rejected(self):
        """example.com origin is rejected with 403."""
        for origin in ["https://example.com", "http://example.com"]:
            with self.subTest(origin=origin):
                response = self.fetch("/testrobot.png", headers={"Origin": origin})
                self.assertEqual(response.code, 403)
                self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_robohash_org_rejected(self):
        """robohash.org origin is rejected with 403."""
        for origin in ["https://robohash.org", "http://robohash.org"]:
            with self.subTest(origin=origin):
                response = self.fetch("/testrobot.png", headers={"Origin": origin})
                self.assertEqual(response.code, 403)
                self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_http_aamarva_com_rejected(self):
        """http://aamarva.com (unencrypted HTTP) is rejected with 403."""
        response = self.fetch("/testrobot.png", headers={"Origin": "http://aamarva.com"})
        self.assertEqual(response.code, 403)
        self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_evil_aamarva_com_rejected(self):
        """https://evil-aamarva.com (subdomain/suffix spoofing) is rejected with 403."""
        for origin in [
            "https://evil-aamarva.com",
            "https://aamarva.com.evil.com",
            "https://sub.aamarva.com",
            "https://not-aamarva.com",
        ]:
            with self.subTest(origin=origin):
                response = self.fetch("/testrobot.png", headers={"Origin": origin})
                self.assertEqual(response.code, 403)
                self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_options_preflight_for_unapproved_origin_rejected(self):
        """OPTIONS preflight for unapproved origin is rejected with 403."""
        headers = {
            "Origin": "https://evil-aamarva.com",
            "Access-Control-Request-Method": "GET",
        }
        response = self.fetch("/testrobot.png", method="OPTIONS", headers=headers)
        self.assertEqual(response.code, 403)

    # 3. Rate limiting tests
    def test_approved_origins_not_rate_limited(self):
        """Approved origins are never rate-limited even under high request volume."""
        # Temporarily configure a small rate limit
        old_max = rate_limiter.max_requests
        rate_limiter.max_requests = 3
        try:
            headers = {"Origin": "https://aamarva.com"}
            for i in range(10):
                response = self.fetch(f"/robot_{i}.png", headers=headers)
                self.assertEqual(response.code, 200)

            run_origin = "https://ais-dev-sy4lhzb3bv4g4mm7spkr5c-89865814157.asia-southeast1.run.app"
            for i in range(10):
                response = self.fetch(f"/robot_run_{i}.png", headers={"Origin": run_origin})
                self.assertEqual(response.code, 200)
        finally:
            rate_limiter.max_requests = old_max

    def test_unapproved_origin_rate_limiting(self):
        """Requests without approved origins are subject to rate limiting and receive 429 when exceeded."""
        old_max = rate_limiter.max_requests
        rate_limiter.max_requests = 3
        try:
            # First 3 requests succeed
            for i in range(3):
                response = self.fetch(f"/robot_norate_{i}.png")
                self.assertEqual(response.code, 200)

            # 4th request exceeds rate limit and receives 429
            response = self.fetch("/robot_norate_overflow.png")
            self.assertEqual(response.code, 429)
            self.assertIn("Retry-After", response.headers)
        finally:
            rate_limiter.max_requests = old_max

    # 4. Set 1 ONLY generation
    def test_set1_only_enforcement(self):
        """Requests asking for set2, set3, or any are forced to Set 1."""
        # Image generated with explicit set1
        resp_set1 = self.fetch("/myseed.png?set=set1", headers={"Origin": "https://aamarva.com"})
        self.assertEqual(resp_set1.code, 200)

        # Image generated requesting set2
        resp_set2 = self.fetch("/myseed.png?set=set2", headers={"Origin": "https://aamarva.com"})
        self.assertEqual(resp_set2.code, 200)

        # Image generated requesting set=any
        resp_any = self.fetch("/myseed.png?set=any", headers={"Origin": "https://aamarva.com"})
        self.assertEqual(resp_any.code, 200)

        # All three must produce the exact same Set 1 image
        img1 = Image.open(io.BytesIO(resp_set1.body))
        img2 = Image.open(io.BytesIO(resp_set2.body))
        img_any = Image.open(io.BytesIO(resp_any.body))

        diff2 = ImageChops.difference(img1.convert("RGBA"), img2.convert("RGBA"))
        diff_any = ImageChops.difference(img1.convert("RGBA"), img_any.convert("RGBA"))
        self.assertFalse(diff2.getbbox(), "Requesting set2 did not produce Set 1 image")
        self.assertFalse(diff_any.getbbox(), "Requesting set=any did not produce Set 1 image")

    # 5. Deterministic generation
    def test_deterministic_generation(self):
        """The same seed string deterministically produces the same image across calls."""
        resp_a = self.fetch("/deterministic_test.png", headers={"Origin": "https://aamarva.com"})
        resp_b = self.fetch("/deterministic_test.png", headers={"Origin": "https://aamarva.com"})
        self.assertEqual(resp_a.body, resp_b.body)

    # 6. Self-sustaining / Zero external calls
    def test_no_external_network_calls(self):
        """Gravatar parameters do not trigger external HTTP requests; local Set 1 is generated."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            response = self.fetch("/test@example.com.png?gravatar=yes", headers={"Origin": "https://aamarva.com"})
            self.assertEqual(response.code, 200)
            mock_urlopen.assert_not_called()

        with patch("urllib.request.urlopen") as mock_urlopen:
            response = self.fetch("/test@example.com.png?gravatar=hashed", headers={"Origin": "https://aamarva.com"})
            self.assertEqual(response.code, 200)
            mock_urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
