document.addEventListener("DOMContentLoaded", () => {
    loadTenants();
});

function loadTenants() {
    fetch("/tenants")
    .then(response => response.json())
    .then(data => {
        let select = document.getElementById("tenantSelect");
        select.innerHTML = '<option value="">Select a Tenant</option>';
        data.forEach(tenant => {
            let option = document.createElement("option");
            option.value = tenant.id;
            option.textContent = tenant.name;
            select.appendChild(option);
        });

        if (data.length > 0) {
            loadApplications(data[0].id);
            loadDeviceProfiles(data[0].id);
        }
    })
    .catch(error => console.error("Error loading tenants:", error));
}

function loadApplications(tenantId) {
    fetch(`/applications/${tenantId}`)
    .then(response => response.json())
    .then(data => {
        let select = document.getElementById("applicationSelect");
        select.innerHTML = '<option value="">Select an Application</option>';
        data.forEach(app => {
            let option = document.createElement("option");
            option.value = app.id;
            option.textContent = app.name;
            select.appendChild(option);
        });

        if (data.length > 0) {
            loadDevices(data[0].id);
        }
    })
    .catch(error => console.error("Error loading applications:", error));
}

function loadDeviceProfiles(tenantId) {
    fetch(`/device-profiles/${tenantId}`)
    .then(response => response.json())
    .then(data => {
        let select = document.getElementById("deviceProfileSelect");
        select.innerHTML = '<option value="">Select a Device Profile</option>';
        
        if (data.error) {
            console.error("Error loading device profiles:", data.error);
            return;
        }

        data.forEach(profile => {
            let option = document.createElement("option");
            option.value = profile.id;
            option.textContent = profile.name;
            select.appendChild(option);
        });
    })
    .catch(error => console.error("Error loading device profiles:", error));
}

function loadDevices(applicationId) {
    fetch(`/devices/${applicationId}`)
    .then(response => response.json())
    .then(data => {
        let list = document.getElementById("deviceList");
        list.innerHTML = "";
        data.forEach(device => {
            let item = document.createElement("li");
            item.textContent = `${device.name} (EUI: ${device.dev_eui})`;
            let deleteBtn = document.createElement("button");
            deleteBtn.textContent = "Remove";
            deleteBtn.onclick = () => removeDevice(device.id);
            item.appendChild(deleteBtn);
            list.appendChild(item);
        });
    })
    .catch(error => console.error("Error loading devices:", error));
}

function uploadDevices() {
    const tenantId = document.getElementById("tenantSelect").value;
    const applicationId = document.getElementById("applicationSelect").value;
    if (!tenantId || !applicationId) {
        alert("Please select a tenant and application first.");
        return;
    }

    const file = document.getElementById("csvFile").files[0];
    if (!file) {
        alert("Please select a CSV file.");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("tenant_id", tenantId);
    formData.append("application_id", applicationId);

    fetch("/upload-devices", {
        method: "POST",
        body: formData,
    })
    .then(response => response.json())
    .then(data => {
        alert(data.message || data.error);
        loadDevices(applicationId);
    })
    .catch(error => console.error("Error uploading:", error));
}

function previewCSV() {
    const file = document.getElementById("csvFile").files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function (event) {
        const csvContent = event.target.result;
        const rows = csvContent.split("\n").map(row => row.split(","));
        const tableBody = document.getElementById("csvPreviewTable").querySelector("tbody");
        tableBody.innerHTML = "";

        rows.slice(1).forEach(row => {
            let tr = document.createElement("tr");
            row.forEach(cell => {
                let td = document.createElement("td");
                td.textContent = cell;
                tr.appendChild(td);
            });
            tableBody.appendChild(tr);
        });
    };
    reader.readAsText(file);
}

function addDevice() {
    const tenantId = document.getElementById("tenantSelect").value;
    const applicationId = document.getElementById("applicationSelect").value;
    const deviceProfileId = document.getElementById("deviceProfileSelect").value;

    if (!tenantId || !applicationId || !deviceProfileId) {
        alert("Please select a tenant, application, and device profile.");
        return;
    }

    const deviceData = {
        tenant_id: tenantId,
        application_id: applicationId,
        device_profile_id: deviceProfileId,
        device_name: document.getElementById("deviceName").value,
        dev_eui: document.getElementById("devEUI").value,
        app_key: document.getElementById("appKey").value,
        app_eui: document.getElementById("appEUI").value,
        description: document.getElementById("description").value,
    };

    fetch("/add-device", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(deviceData),
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert("Error: " + data.error);
        } else {
            alert("Device added successfully!");
            loadDevices(applicationId);
        }
    })
    .catch(error => console.error("Error adding device:", error));
}

function removeDevice(deviceId) {
    if (!confirm("Are you sure you want to remove this device?")) return;

    fetch(`/remove-device/${deviceId}`, {
        method: "DELETE",
    })
    .then(response => response.json())
    .then(data => {
        alert(data.message || data.error);
        loadDevices(document.getElementById("applicationSelect").value);
    })
    .catch(error => console.error("Error removing device:", error));
}

document.getElementById("tenantSelect").addEventListener("change", function() {
    const tenantId = this.value;
    if (tenantId) {
        loadApplications(tenantId);
        loadDeviceProfiles(tenantId);
    }
});

document.getElementById("applicationSelect").addEventListener("change", function() {
    const applicationId = this.value;
    if (applicationId) {
        loadDevices(applicationId);
    }
});
