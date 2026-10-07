import csv
import os
import secrets
import threading
from pathlib import Path

import grpc
from cachetools import TTLCache
from chirpstack_api import api
from chirpstack_tools import ChirpStackClient, ChirpStackConfig, DeviceSpec, GatewaySpec
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower()
    in {"1", "true", "yes"},
    MAX_CONTENT_LENGTH=1024 * 1024,
)

# WSGI entry point.
application = app

UPLOAD_DIR = Path(
    os.getenv("UPLOAD_DIR", "/tmp/chirpstack-uploads")
).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Flask's default session cookie is signed, but not encrypted. Keep ChirpStack
# credentials server-side and put only an opaque session identifier in the cookie.
_CREDENTIALS = TTLCache(
    maxsize=int(os.getenv("MAX_CREDENTIAL_SESSIONS", "256")),
    ttl=int(os.getenv("CREDENTIAL_TTL_SECONDS", "28800")),
)
_CREDENTIALS_LOCK = threading.Lock()


def _session_id():
    sid = session.get("sid")
    if not sid:
        sid = secrets.token_urlsafe(32)
        session.clear()
        session["sid"] = sid
    return sid


def _set_credentials(server, api_token):
    with _CREDENTIALS_LOCK:
        _CREDENTIALS[_session_id()] = {
            "server": server,
            "api_token": api_token,
        }


def _get_credentials():
    sid = session.get("sid")
    if not sid:
        return None
    with _CREDENTIALS_LOCK:
        return _CREDENTIALS.get(sid)


def _clear_credentials():
    sid = session.get("sid")
    if sid:
        with _CREDENTIALS_LOCK:
            _CREDENTIALS.pop(sid, None)
    session.clear()


def _grpc_channel(server):
    if os.getenv("CHIRPSTACK_GRPC_TLS", "false").lower() in {
        "1",
        "true",
        "yes",
    }:
        return grpc.secure_channel(server, grpc.ssl_channel_credentials())
    return grpc.insecure_channel(server)


def _server_allowed(server):
    configured = os.getenv("CHIRPSTACK_ALLOWED_SERVERS", "")
    allowed = {value.strip() for value in configured.split(",") if value.strip()}
    return not allowed or server in allowed


def _create_grpc_clients(config):
    channel = _grpc_channel(config["server"])
    return {
        "tenant_client": api.TenantServiceStub(channel),
        "app_client": api.ApplicationServiceStub(channel),
        "device_client": api.DeviceServiceStub(channel),
        "dp_client": api.DeviceProfileServiceStub(channel),
        "gateway_client": api.GatewayServiceStub(channel),
    }


def _auth_metadata(config):
    return [("authorization", f"Bearer {config['api_token']}")]


def get_grpc_clients():
    config = _get_credentials()
    if not session.get("authenticated") or not config:
        return None
    return _create_grpc_clients(config)


def get_auth_token():
    config = _get_credentials()
    if not session.get("authenticated") or not config:
        return None
    return _auth_metadata(config)


def _save_csv(upload):
    filename = secure_filename(upload.filename or "")
    if not filename or not filename.lower().endswith(".csv"):
        raise ValueError("Only CSV uploads are accepted")

    path = UPLOAD_DIR / f"{secrets.token_hex(8)}-{filename}"
    upload.save(path)
    return path


def _key_is_valid(value):
    if not isinstance(value, str) or len(value) != 32:
        return False
    try:
        bytes.fromhex(value)
        return True
    except ValueError:
        return False


def _list_all(client, request_factory, page_size=100):
    """Return all list results using ChirpStack's limit/offset pagination."""
    items = []
    offset = 0
    while True:
        req = request_factory(page_size, offset)
        resp = client.List(req, metadata=get_auth_token(), timeout=10)
        items.extend(resp.result)
        offset += len(resp.result)
        if offset >= resp.total_count or not resp.result:
            return items


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "Upload exceeds the 1 MiB limit"}), 413


@app.route("/")
def auth():
    """Render authentication page."""
    return render_template("auth.html")


@app.route("/set-config", methods=["POST"])
def set_config():
    """Validate and store the ChirpStack endpoint and token server-side."""
    data = request.get_json(silent=True) or {}
    server = str(data.get("server") or "").strip()
    api_token = str(data.get("api_token") or "").strip()

    if not server or not api_token:
        return jsonify({"error": "Server and API token are required"}), 400
    if not _server_allowed(server):
        return jsonify({"error": "Server is not in the configured allowlist"}), 400

    candidate = {"server": server, "api_token": api_token}
    try:
        clients = _create_grpc_clients(candidate)
        clients["tenant_client"].List(
            api.ListTenantsRequest(limit=1),
            metadata=_auth_metadata(candidate),
            timeout=10,
        )
    except grpc.RpcError as exc:
        app.logger.warning(
            "ChirpStack authentication failed: %s", exc.code().name
        )
        _clear_credentials()
        return jsonify({"error": "Failed to authenticate"}), 400

    _set_credentials(server, api_token)
    session["authenticated"] = True
    return jsonify({"message": "Successfully connected", "status": "logged in"})


def require_auth():
    """Redirect to login page if not authenticated."""
    if not session.get("authenticated") or not _get_credentials():
        return redirect(url_for("auth"))
    return None


@app.route("/check-auth")
def check_auth():
    """Check if the user is authenticated."""
    authenticated = bool(session.get("authenticated") and _get_credentials())
    return jsonify({"authenticated": authenticated})


@app.route("/tenants", methods=["GET"])
def get_tenants():
    """Retrieve all tenants."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        items = _list_all(
            clients["tenant_client"],
            lambda limit, offset: api.ListTenantsRequest(
                limit=limit, offset=offset
            ),
        )
        return jsonify([{"id": t.id, "name": t.name} for t in items])
    except grpc.RpcError as exc:
        app.logger.warning("Failed to list tenants: %s", exc.code().name)
        return jsonify({"error": "Failed to list tenants"}), 502


@app.route("/applications/<tenant_id>", methods=["GET"])
def get_applications(tenant_id):
    """Retrieve all applications for a given tenant."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        items = _list_all(
            clients["app_client"],
            lambda limit, offset: api.ListApplicationsRequest(
                tenant_id=tenant_id, limit=limit, offset=offset
            ),
        )
        return jsonify(
            [{"id": item.id, "name": item.name} for item in items]
        )
    except grpc.RpcError as exc:
        app.logger.warning("Failed to list applications: %s", exc.code().name)
        return jsonify({"error": "Failed to list applications"}), 502


@app.route("/device-profiles/<tenant_id>", methods=["GET"])
def get_device_profiles(tenant_id):
    """Retrieve all device profiles for a given tenant."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        items = _list_all(
            clients["dp_client"],
            lambda limit, offset: api.ListDeviceProfilesRequest(
                tenant_id=tenant_id, limit=limit, offset=offset
            ),
        )
        profiles = [{"id": dp.id, "name": dp.name} for dp in items]
        if not profiles:
            return (
                jsonify({"error": "No device profiles found for this tenant."}),
                404,
            )
        return jsonify(profiles)
    except grpc.RpcError as exc:
        app.logger.warning(
            "Failed to list device profiles: %s", exc.code().name
        )
        return jsonify({"error": "Failed to list device profiles"}), 502


@app.route("/devices/<application_id>", methods=["GET"])
def get_devices(application_id):
    """Retrieve all devices for a given application."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        items = _list_all(
            clients["device_client"],
            lambda limit, offset: api.ListDevicesRequest(
                application_id=application_id,
                limit=limit,
                offset=offset,
            ),
        )
        return jsonify(
            [
                {
                    "id": d.dev_eui,
                    "name": d.name,
                    "dev_eui": d.dev_eui,
                    "device_profile_id": d.device_profile_id,
                    "last_seen_at": (
                        d.last_seen_at.ToJsonString()
                        if d.HasField("last_seen_at")
                        else None
                    ),
                }
                for d in items
            ]
        )
    except grpc.RpcError as exc:
        app.logger.warning("Failed to list devices: %s", exc.code().name)
        return jsonify({"error": "Failed to list devices"}), 502


@app.route("/upload-devices", methods=["POST"])
def upload_devices():
    """Process an uploaded CSV and create devices."""
    if (
        "file" not in request.files
        or "tenant_id" not in request.form
        or "application_id" not in request.form
    ):
        return jsonify({"error": "Missing required fields"}), 400

    path = None
    try:
        path = _save_csv(request.files["file"])
        with path.open("r", encoding="utf-8-sig", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                result = create_device(
                    request.form["tenant_id"],
                    request.form["application_id"],
                    row,
                )
                if "error" in result:
                    return jsonify(result), 400
    except (OSError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        if path:
            path.unlink(missing_ok=True)

    return jsonify({"message": "Devices uploaded successfully."})


@app.route("/add-device", methods=["POST"])
def add_device():
    """Manually add a single device."""
    data = request.get_json(silent=True) or {}
    required_fields = [
        "tenant_id",
        "application_id",
        "device_profile_id",
        "device_name",
        "dev_eui",
        "app_key",
    ]
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400

    response = create_device(
        data["tenant_id"], data["application_id"], data
    )
    return jsonify(response), 400 if "error" in response else 200


def create_device(tenant_id, application_id, row):
    """Idempotently provision a device through the shared ChirpStack client."""
    del tenant_id
    config = _get_credentials()
    if not session.get("authenticated") or not config:
        return {"error": "Not authenticated"}

    try:
        app_key = str(row.get("app_key") or "").strip() or None
        explicit_nwk_key = str(row.get("nwk_key") or "").strip() or None
        spec = DeviceSpec(
            dev_eui=str(row.get("dev_eui") or ""),
            name=str(row.get("device_name") or ""),
            device_profile_id=str(row.get("device_profile_id") or ""),
            nwk_key=explicit_nwk_key or app_key or "",
            app_key=app_key if explicit_nwk_key else None,
            join_eui=str(
                row.get("join_eui") or row.get("app_eui") or ""
            ).strip()
            or None,
            description=str(row.get("description") or ""),
        )
        with ChirpStackClient(
            ChirpStackConfig(
                server=config["server"],
                api_token=config["api_token"],
                tls=os.getenv("CHIRPSTACK_GRPC_TLS", "false").lower()
                in {"1", "true", "yes"},
            )
        ) as client:
            status = client.ensure_device(
                application_id=application_id,
                device_profile_id=spec.device_profile_id,
                dev_eui=spec.dev_eui,
                name=spec.name,
                nwk_key=spec.nwk_key,
                app_key=spec.app_key,
                join_eui=spec.join_eui,
                description=spec.description,
            )
        return {"status": status, "dev_eui": spec.dev_eui}
    except ValueError as exc:
        return {"error": str(exc)}
    except grpc.RpcError as exc:
        app.logger.warning(
            "Device provisioning failed: %s", exc.code().name
        )
        return {"error": "Failed to provision device"}


@app.route("/remove-device/<device_id>", methods=["DELETE"])
def remove_device(device_id):
    """Remove a device."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        req = api.DeleteDeviceRequest(dev_eui=device_id)
        clients["device_client"].Delete(
            req, metadata=auth_token, timeout=10
        )
        return jsonify({"message": "Device removed successfully."})
    except grpc.RpcError as exc:
        app.logger.warning("Failed to remove device: %s", exc.code().name)
        return jsonify({"error": "Failed to remove device"}), 502


@app.route("/upload-gateways", methods=["POST"])
def upload_gateways():
    """Process an uploaded CSV and create gateways."""
    if "file" not in request.files or "tenant_id" not in request.form:
        return jsonify({"error": "Missing required fields"}), 400

    path = None
    try:
        path = _save_csv(request.files["file"])
        with path.open("r", encoding="utf-8-sig", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                result = create_gateway(request.form["tenant_id"], row)
                if "error" in result:
                    return jsonify(result), 400
    except (OSError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        if path:
            path.unlink(missing_ok=True)

    return jsonify({"message": "Gateways uploaded successfully."})


def create_gateway(tenant_id, row):
    """Idempotently provision a gateway through the shared client."""
    config = _get_credentials()
    if not session.get("authenticated") or not config:
        return {"error": "Not authenticated"}

    try:
        spec = GatewaySpec(
            gateway_id=str(row.get("gateway_id") or ""),
            name=str(row.get("gateway_name") or ""),
            description=str(row.get("description") or ""),
            latitude=float(row.get("latitude") or 0),
            longitude=float(row.get("longitude") or 0),
            altitude=float(row.get("altitude") or 0),
            stats_interval=int(row.get("stats_interval") or 30),
        )
        with ChirpStackClient(
            ChirpStackConfig(
                server=config["server"],
                api_token=config["api_token"],
                tls=os.getenv("CHIRPSTACK_GRPC_TLS", "false").lower()
                in {"1", "true", "yes"},
            )
        ) as client:
            status = client.ensure_gateway(
                tenant_id=tenant_id,
                gateway_id=spec.gateway_id,
                name=spec.name,
                description=spec.description,
                latitude=spec.latitude,
                longitude=spec.longitude,
                altitude=spec.altitude,
                stats_interval=spec.stats_interval,
                tags=spec.tags,
                metadata=spec.metadata,
            )
        return {"status": status, "gateway_id": spec.gateway_id}
    except (TypeError, ValueError) as exc:
        return {"error": str(exc)}
    except grpc.RpcError as exc:
        app.logger.warning(
            "Gateway provisioning failed: %s", exc.code().name
        )
        return {"error": "Failed to provision gateway"}


@app.route("/gateways/<tenant_id>", methods=["GET"])
def get_gateways(tenant_id):
    """Retrieve all gateways for a given tenant."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        items = _list_all(
            clients["gateway_client"],
            lambda limit, offset: api.ListGatewaysRequest(
                tenant_id=tenant_id, limit=limit, offset=offset
            ),
        )
        return jsonify(
            [
                {
                    "id": g.gateway_id,
                    "name": g.name,
                    "description": g.description,
                    "last_seen_at": (
                        g.last_seen_at.ToJsonString()
                        if g.HasField("last_seen_at")
                        else None
                    ),
                }
                for g in items
            ]
        )
    except grpc.RpcError as exc:
        app.logger.warning("Failed to list gateways: %s", exc.code().name)
        return jsonify({"error": "Failed to list gateways"}), 502


@app.route("/devices")
def devices():
    """Render device management page."""
    auth_response = require_auth()
    if auth_response:
        return auth_response
    return render_template("devices.html")


@app.route("/gateways")
def gateways():
    """Render gateway management page."""
    auth_response = require_auth()
    if auth_response:
        return auth_response
    return render_template("gateways.html")


@app.route("/logout", methods=["POST"])
def logout():
    """Log out and destroy server-side credentials."""
    _clear_credentials()
    return jsonify({"message": "Logged out successfully."})


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
