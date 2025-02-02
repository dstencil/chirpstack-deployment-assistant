# **Chirpstack Deployment Assistant 🚀**  
*A web-based tool for bulk provisioning and managing ChirpStack devices & gateways.*

⚠️ Early Release Notice ⚠️
This project is still a rough draft/early release. Features are functional but under active development. Expect changes, improvements, and potential bugs.

Key To-Do's:

    Proper Login/Logout Handling for server connections
    Additional Pages for enhanced functionality
    Ongoing code clean-up and optimizations
    
## 🌟 Features
✅ **Bulk Upload** – Easily provision **devices & gateways** from CSV.  
✅ **Tenant & Application Auto-Discovery** – Dynamically load **tenants, applications, and device profiles**.  
✅ **Device & Gateway Management** – Manually add, edit, or delete devices/gateways.  
✅ **Secure API Authentication** – API token-based authentication with session storage.  
✅ **Fully Containerized** – **Docker-ready** for easy deployment.  

---

## 🛠️ Installation  

### With Docker
```
docker pull ghcr.io/dstencil/chirpstack-deployment-assistant:latest
docker run -p 5000:5000 chirpstack-deployment-assistant:latest
```

### Local Build
 
```
git clone https://github.com/your-username/chirpstack-deployment-assistant.git
cd chirpstack-deployment-assistant
docker build -t chirpstack-deployment-assistant .
docker run -p 5000:5000 chirpstack-deployment-assistant
```

### Open in Browser
```
http://localhost:5000
```

📖 Usage Guide

🔹 1. Authenticate

    Enter ChirpStack API URL & API Token to log in.

🔹 2. Select Tenant & Application

    Tenants auto-load from ChirpStack.
    Applications & device profiles update dynamically.

🔹 3. Bulk Upload Devices or Gateways

    Upload a CSV file with device/gateway details.
    Preview data before provisioning.

🔹 4. Manual Device & Gateway Management

    Add individual devices/gateways using input fields.
    Delete or modify existing ones

📌 Environment Variables
```
Variable	Description
FLASK_RUN_HOST=0.0.0.0	Allows external access
FLASK_ENV=production	Sets Flask to production mode
```
