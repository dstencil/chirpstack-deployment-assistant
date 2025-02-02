from flask import Flask, request, jsonify, render_template, session
import grpc
from chirpstack_api import api
import csv
import os
from werkzeug.utils import secure_filename
app = Flask(__name__)
app.secret_key = "your_secret_key"


os.makedirs("uploads", exist_ok=True)


def get_grpc_clients():
    """Establish gRPC connections to ChirpStack services."""
    if "server" not in session or "api_token" not in session:
        return None
    channel = grpc.insecure_channel(session["server"])
    return {
        "tenant_client": api.TenantServiceStub(channel),
        "app_client": api.ApplicationServiceStub(channel),
        "device_client": api.DeviceServiceStub(channel),
        "dp_client": api.DeviceProfileServiceStub(channel),
        "gateway_client": api.GatewayServiceStub(channel),
    }


def get_auth_token():
    if "api_token" not in session:
        return None
    return [("authorization", f"Bearer {session['api_token']}")]


@app.route('/')
def auth():
    """Render authentication page."""
    return render_template('auth.html')


@app.route('/set-config', methods=['POST'])
def set_config():
    """Set API server and token in session."""
    session["server"] = request.json.get("server")
    session["api_token"] = request.json.get("api_token")

    clients = get_grpc_clients()
    auth_token = get_auth_token()

    if not clients or not auth_token:
        return jsonify({"error": "Invalid server or API token"}), 400

    try:
        req = api.ListTenantsRequest(limit=1)
        clients["tenant_client"].List(req, metadata=auth_token)
        session["authenticated"] = True  # Mark session as authenticated
        return jsonify({"message": "Successfully connected", "status": "logged in"})
    except grpc.RpcError:
        session.pop("authenticated", None)  # Remove session auth on failure
        return jsonify({"error": "Failed to authenticate"}), 400


def require_auth():
    """Redirect to login page if not authenticated."""
    if not session.get("authenticated"):
        return redirect(url_for('auth'))
    
@app.route('/check-auth')
def check_auth():
    """Check if the user is authenticated."""
    return jsonify({"authenticated": session.get("authenticated", False)})

@app.route('/tenants', methods=['GET'])
def get_tenants():
    """Retrieve all tenants."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        req = api.ListTenantsRequest(limit=100)
        resp = clients["tenant_client"].List(req, metadata=auth_token)
        return jsonify([{"id": t.id, "name": t.name} for t in resp.result])
    except grpc.RpcError as e:
        return jsonify({"error": f"gRPC error: {e.details()}"}), 500


@app.route('/applications/<tenant_id>', methods=['GET'])
def get_applications(tenant_id):
    """Retrieve all applications for a given tenant."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        req = api.ListApplicationsRequest(tenant_id=tenant_id, limit=100)
        resp = clients["app_client"].List(req, metadata=auth_token)
        return jsonify([{"id": app.id, "name": app.name} for app in resp.result])
    except grpc.RpcError as e:
        return jsonify({"error": f"gRPC error: {e.details()}"}), 500


@app.route('/device-profiles/<tenant_id>', methods=['GET'])
def get_device_profiles(tenant_id):
    """Retrieve all device profiles for a given tenant."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        req = api.ListDeviceProfilesRequest(tenant_id=tenant_id, limit=100)
        resp = clients["dp_client"].List(req, metadata=auth_token)
        profiles = [{"id": dp.id, "name": dp.name} for dp in resp.result]

        if not profiles:
            return jsonify({"error": "No device profiles found for this tenant."}), 404

        return jsonify(profiles)
    except grpc.RpcError as e:
        return jsonify({"error": f"gRPC error: {e.details()}"}), 500


@app.route('/devices/<application_id>', methods=['GET'])
def get_devices(application_id):
    """Retrieve all devices for a given application."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        req = api.ListDevicesRequest(application_id=application_id, limit=100)
        resp = clients["device_client"].List(req, metadata=auth_token)
        return jsonify([{"id": d.dev_eui, "name": d.name, "dev_eui": d.dev_eui} for d in resp.result])
    except grpc.RpcError as e:
        return jsonify({"error": f"gRPC error: {e.details()}"}), 500


@app.route('/upload-devices', methods=['POST'])
def upload_devices():
    """Process uploaded CSV and create devices."""
    if 'file' not in request.files or 'tenant_id' not in request.form or 'application_id' not in request.form:
        return jsonify({"error": "Missing required fields"}), 400

    file = request.files['file']
    tenant_id = request.form['tenant_id']
    application_id = request.form['application_id']
    filename = os.path.join("uploads", file.filename)
    file.save(filename)

    with open(filename, "r") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            create_device(tenant_id, application_id, row)

    return jsonify({"message": "Devices uploaded successfully."})


@app.route('/add-device', methods=['POST'])
def add_device():
    """Manually add a single device."""
    data = request.json

    required_fields = ["tenant_id", "application_id", "device_profile_id", "device_name", "dev_eui", "app_key"]
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    response = create_device(data["tenant_id"], data["application_id"], data)
    return jsonify(response)


def create_device(tenant_id, application_id, row):
    """Create a single device from CSV or manual input."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return {"error": "Not authenticated"}

    try:
        req = api.CreateDeviceRequest()
        req.device.dev_eui = row["dev_eui"]
        req.device.name = row["device_name"]
        req.device.description = row.get("description", "")
        req.device.application_id = application_id
        req.device.device_profile_id = row["device_profile_id"]

        # Optional fields
        req.device.variables["app_key"] = row["app_key"]
        if "app_eui" in row and row["app_eui"]:
            req.device.variables["app_eui"] = row["app_eui"]

        clients["device_client"].Create(req, metadata=auth_token)
        return {"message": f"Device '{row['device_name']}' created successfully."}
    except grpc.RpcError as e:
        return {"error": f"gRPC error while creating device: {e.details()}"}  

@app.route('/remove-device/<device_id>', methods=['DELETE'])
def remove_device(device_id):
    """Remove a device."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()

    try:
        req = api.DeleteDeviceRequest(dev_eui=device_id)
        clients["device_client"].Delete(req, metadata=auth_token)
        return jsonify({"message": "Device removed successfully."})
    except grpc.RpcError as e:
        return jsonify({"error": f"gRPC error: {e.details()}"}), 500

@app.route('/upload-gateways', methods=['POST'])
def upload_gateways():
    """Process uploaded CSV and create gateways."""
    if 'file' not in request.files or 'tenant_id' not in request.form:
        return jsonify({"error": "Missing required fields"}), 400

    file = request.files['file']
    tenant_id = request.form['tenant_id']
    filename = secure_filename(file.filename)
    filepath = os.path.normpath(os.path.join("uploads", filename))
    if not filepath.startswith(os.path.abspath("uploads")):
        return jsonify({"error": "Invalid file path"}), 400
    file.save(filepath)

    with open(filepath, "r") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            create_gateway(tenant_id, row)

    return jsonify({"message": "Gateways uploaded successfully."})
def create_gateway(tenant_id, row):
    """Create a single gateway from CSV or manual input."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    if not clients or not auth_token:
        return {"error": "Not authenticated"}

    def safe_float(value, default=0.0):
        try:
            return float(value) if value.strip() else default
        except ValueError:
            return default

    try:
        req = api.CreateGatewayRequest()
        req.gateway.gateway_id = row["gateway_id"]
        req.gateway.name = row["gateway_name"]
        req.gateway.description = row.get("description", "")
        req.gateway.tenant_id = tenant_id

        # Use safe_float function to handle empty or invalid numbers
        req.gateway.location.latitude = safe_float(row.get("latitude", "0.0"))
        req.gateway.location.longitude = safe_float(row.get("longitude", "0.0"))
        req.gateway.location.altitude = safe_float(row.get("altitude", "0.0"))
        req.gateway.stats_interval = int(row.get("stats_interval", 30)) if row.get("stats_interval") else 30

        clients["gateway_client"].Create(req, metadata=auth_token)
        return {"message": f"Gateway '{row['gateway_name']}' created successfully."}
    except grpc.RpcError as e:
        return {"error": f"gRPC error while creating gateway: {e.details()}"}
    
@app.route('/gateways/<tenant_id>', methods=['GET'])
def get_gateways(tenant_id):
    """Retrieve all gateways for a given tenant."""
    clients = get_grpc_clients()
    auth_token = get_auth_token()
    
    if not clients or not auth_token:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        req = api.ListGatewaysRequest(tenant_id=tenant_id, limit=100)
        resp = clients["gateway_client"].List(req, metadata=auth_token)
        return jsonify([{
            "id": g.gateway_id,
            "name": g.name,
            "description": g.description,
            "latitude": g.location.latitude,
            "longitude": g.location.longitude,
            "altitude": g.location.altitude
        } for g in resp.result])
    except grpc.RpcError as e:
        return jsonify({"error": f"gRPC error: {e.details()}"}), 500



@app.route('/devices')
def devices():
    """Render device management page."""
    if require_auth():
        return require_auth()
    return render_template('devices.html')


@app.route('/gateways')
def gateways():
    """Render gateway management page."""
    if require_auth():
        return require_auth()
    return render_template('gateways.html')

@app.route('/logout')
def logout():
    """Log out and clear session."""
    session.clear()
    return redirect(url_for('auth'))


if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    app.run(debug=debug_mode)
