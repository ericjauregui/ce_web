"""Generous write limits for the current single-worker Render service."""
from __future__ import annotations

import ipaddress
import os

from flask import Flask, current_app, jsonify, make_response, render_template, request
from flask_limiter import Limiter


def client_address() -> str:
    address = request.remote_addr or "unknown"
    # Only trust the nearest forwarded address behind the configured Render
    # ingress. Never use the spoofable leftmost value or trust headers locally.
    if current_app.config["RATE_LIMIT_TRUST_PROXY"]:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[-1].strip()
        try:
            address = str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return address


def install_rate_limiting(app: Flask) -> Limiter:
    app.config.setdefault("RATE_LIMIT_TRUST_PROXY", os.getenv("RENDER", "").lower() == "true")
    app.config.setdefault("CHECKOUT_RATE_LIMIT", "30 per 10 minutes")
    app.config.setdefault("CART_RATE_LIMIT", "300 per minute")
    app.config.setdefault("CONNECT_EVENT_RATE_LIMIT", "600 per minute")
    app.config.setdefault("SITE_ANALYTICS_RATE_LIMIT", "600 per minute")
    limiter = Limiter(
        client_address,
        app=app,
        default_limits=[],
        storage_uri="memory://",
        strategy="moving-window",
        headers_enabled=True,
    )
    app.extensions["ce_rate_limiter"] = limiter
    limiter.request_filter(lambda: app.testing and not app.config.get("RATE_LIMIT_TESTING", False))

    checkout_limit = limiter.limit(lambda: app.config["CHECKOUT_RATE_LIMIT"], methods=["POST"])
    app.view_functions["checkout"] = checkout_limit(app.view_functions["checkout"])
    cart_limit = limiter.shared_limit(
        lambda: app.config["CART_RATE_LIMIT"], scope="cart-writes", methods=["POST"]
    )
    for endpoint in ("api_cart_add", "api_cart_set", "api_cart_remove", "api_cart_clear", "api_cart_note"):
        app.view_functions[endpoint] = cart_limit(app.view_functions[endpoint])
    app.view_functions["connect_event"] = limiter.limit(
        lambda: app.config["CONNECT_EVENT_RATE_LIMIT"], methods=["POST"]
    )(app.view_functions["connect_event"])
    app.view_functions["site_analytics_event"] = limiter.limit(
        lambda: app.config["SITE_ANALYTICS_RATE_LIMIT"], methods=["POST"]
    )(app.view_functions["site_analytics_event"])

    @app.errorhandler(429)
    def too_many_requests(error):
        if request.path.startswith("/api/"):
            response = jsonify(ok=False, error="Too many cart updates. Please wait a minute and try again.")
            response.status_code = 429
        else:
            response = make_response(render_template("429.html"), 429)
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        return response

    return limiter
