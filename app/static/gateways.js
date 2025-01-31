document.addEventListener("DOMContentLoaded", () => {
    loadTenants();
    document.getElementById("tenantSelect").addEventListener("change", () => {
        loadGateways();
    });
});

function loadTenants() {
    fetch("/tenants")
    .then(response => response.json())
    .then(data => {
        let select = document.getElementById("tenantSelect");
        select.innerHTML = "";
        data.forEach(tenant => {
            let option = document.createElement("option");
            option.value = tenant.id;
            option.textContent = tenant.name;
            select.appendChild(option);
        });

        if (data.length > 0) {
            select.value = data[0].id; // Auto-select first tenant
            loadGateways(); // Load gateways for first tenant
        }
    })
    .catch(error => console.error("Error loading tenants:", error));
}

function loadGateways() {
    const tenantId = document.getElementById("tenantSelect").value;
    if (!tenantId) return;

    fetch(`/gateways/${tenantId}`)
    .then(response => response.json())
    .then(data => {
        let list = document.getElementById("gatewayList");
        list.innerHTML = "";
        if (data.error) {
            console.error("Error loading gateways:", data.error);
            return;
        }

        data.forEach(gateway => {
            let item = document.createElement("li");
            item.textContent = `${gateway.name} (ID: ${gateway.id}) - ${gateway.description}`;

            let deleteBtn = document.createElement("button");
            deleteBtn.textContent = "Remove";
            deleteBtn.onclick = () => removeGateway(gateway.id);

            item.appendChild(deleteBtn);
            list.appendChild(item);
        });
    })
    .catch(error => console.error("Error loading gateways:", error));
}

function removeGateway(gatewayId) {
    if (!confirm("Are you sure you want to delete this gateway?")) return;

    fetch(`/remove-gateway/${gatewayId}`, {
        method: "DELETE"
    })
    .then(response => response.json())
    .then(data => {
        alert(data.message || data.error);
        loadGateways();
    })
    .catch(error => console.error("Error removing gateway:", error));
}

function uploadGateways() {
    const tenantId = document.getElementById("tenantSelect").value;
    if (!tenantId) {
        alert("Please select a tenant first.");
        return;
    }

    const file = document.getElementById("gatewayCsvFile").files[0];
    if (!file) {
        alert("Please select a CSV file.");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("tenant_id", tenantId);

    fetch("/upload-gateways", {
        method: "POST",
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        alert(data.message || data.error);
        loadGateways();
    })
    .catch(error => console.error("Error uploading gateways:", error));
}

function previewGatewayCSV() {
    const file = document.getElementById("gatewayCsvFile").files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function (event) {
        const csvContent = event.target.result;
        const rows = csvContent.split("\n").map(row => row.split(","));
        const tableBody = document.getElementById("gatewayCsvPreviewTable").querySelector("tbody");
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

function addGateway() {
    const tenantId = document.getElementById("tenantSelect").value;
    if (!tenantId) {
        alert("Please select a tenant first.");
        return;
    }

    const gatewayData = {
        tenant_id: tenantId,
        name: document.getElementById("gatewayName").value,
        gateway_id: document.getElementById("gatewayId").value,
        description: document.getElementById("gatewayDescription").value,
        latitude: document.getElementById("latitude").value || 0.0,
        longitude: document.getElementById("longitude").value || 0.0,
        altitude: document.getElementById("altitude").value || 0.0,
        stats_interval: document.getElementById("statsInterval").value || 30
    };

    fetch("/add-gateway", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(gatewayData)
    })
    .then(response => response.json())
    .then(data => {
        alert(data.message || data.error);
        loadGateways();
    })
    .catch(error => console.error("Error adding gateway:", error));
}
