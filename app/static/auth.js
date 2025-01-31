document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("api_token").type = "password"; // Ensure hidden by default
    checkAuthStatus();
});

function checkAuthStatus() {
    fetch("/check-auth")
        .then(response => response.json())
        .then(data => {
            if (data.authenticated) {
                document.getElementById("devicesLink").style.display = "inline";
                document.getElementById("gatewaysLink").style.display = "inline";
            }
        })
        .catch(error => console.error("Error checking authentication:", error));
}

document.getElementById("toggleApiKey").addEventListener("click", function () {
    const apiKeyInput = document.getElementById("api_token");
    if (apiKeyInput.type === "password") {
        apiKeyInput.type = "text";
        this.textContent = "Hide";
    } else {
        apiKeyInput.type = "password";
        this.textContent = "Show";
    }
});

document.getElementById("configForm").addEventListener("submit", function (event) {
    event.preventDefault();

    const server = document.getElementById("server").value;
    const apiToken = document.getElementById("api_token").value;

    fetch("/set-config", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ server, api_token: apiToken })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            document.getElementById("statusMessage").textContent = "Error: " + data.error;
            document.getElementById("statusMessage").style.color = "red";
        } else {
            document.getElementById("statusMessage").textContent = "Successfully connected!";
            document.getElementById("statusMessage").style.color = "green";
            document.getElementById("devicesLink").style.display = "inline";
            document.getElementById("gatewaysLink").style.display = "inline";
        }
    })
    .catch(error => console.error("Error saving configuration:", error));
});
function logout() {
    fetch('/logout', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            alert(data.message);
            window.location.href = '/';
        })
        .catch(error => console.error('Error logging out:', error));
}
