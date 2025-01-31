document.getElementById("authForm").addEventListener("submit", function (e) {
    e.preventDefault();
    const server = document.getElementById("server").value;
    const api_token = document.getElementById("api_token").value;

    fetch("/set-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ server, api_token }),
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById("status").innerText = data.message || data.error;
        if (data.status === "logged in") {
            sessionStorage.setItem("auth", "true");
        }
    })
    .catch(error => console.error("Error:", error));
});
