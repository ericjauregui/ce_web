from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, request, session

from domains.file_cache import get_path_version

NO_STORE = "private, no-store, max-age=0"
MUTABLE_STATIC = "public, max-age=300, must-revalidate"
IMMUTABLE_STATIC = "public, max-age=31536000, immutable"
PUBLIC_METADATA = "public, max-age=300, must-revalidate"
PUBLIC_CONTACT = "public, max-age=3600, must-revalidate"
PUBLIC_CONNECT = "public, max-age=60, must-revalidate"

# These endpoints contain no customer-specific cart data and use an empty cart
# context when rendered inside the shared page layout. Keep this list small.
PUBLIC_ENDPOINT_POLICIES = {
    "favicon": MUTABLE_STATIC,
    "robots": PUBLIC_METADATA,
    "sitemap": PUBLIC_METADATA,
    "team_member_vcard": PUBLIC_CONTACT,
    "team_member_vcard_qr": PUBLIC_METADATA,
    "connect_vcard": PUBLIC_CONNECT,
    "connect_event": NO_STORE,
    "site_analytics_event": NO_STORE,
    "site_analytics_dashboard": NO_STORE,
}


def _is_current_asset_version(app: Flask) -> bool:
    filename = (request.view_args or {}).get("filename")
    supplied_version = request.args.get("v", "")
    if not isinstance(filename, str) or not supplied_version or not app.static_folder:
        return False

    static_root = Path(app.static_folder).resolve()
    asset_path = (static_root / filename).resolve()
    try:
        asset_path.relative_to(static_root)
    except ValueError:
        return False

    current_version = get_path_version(asset_path)
    return current_version is not None and supplied_version == current_version


def install_cache_control(app: Flask) -> None:
    @app.before_request
    def keep_customer_session_permanent() -> None:
        # Static, public metadata/contact requests, and private analytics must
        # not create a customer cart session.
        if (
            request.endpoint == "static"
            or request.endpoint in PUBLIC_ENDPOINT_POLICIES
        ):
            return
        session.permanent = True

    @app.after_request
    def apply_cache_policy(response: Response) -> Response:
        # Flask's send_file may have supplied an Expires value based on its
        # global default. Cache-Control below is the single policy authority.
        response.headers.pop("Expires", None)

        # Do not let an error page or failed private download remain in a
        # browser or shared edge cache.
        if response.status_code >= 400:
            response.headers["Cache-Control"] = NO_STORE
            return response

        if request.endpoint == "static":
            response.headers["Cache-Control"] = (
                IMMUTABLE_STATIC if _is_current_asset_version(app) else MUTABLE_STATIC
            )
            return response

        public_policy = PUBLIC_ENDPOINT_POLICIES.get(request.endpoint or "")
        response.headers["Cache-Control"] = public_policy or NO_STORE
        return response
