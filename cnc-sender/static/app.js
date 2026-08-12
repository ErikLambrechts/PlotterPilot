const state = {
    connected: false,
    position: {
        x: 0,
        y: 0,
        z: 0
    },
    machine: {
        width: 300,
        height: 200,
        z_min: -5,
        z_max: 20
    },
    host: "plotbot.local",
    port: 23
};

const canvas = document.getElementById("workspace");
const ctx = canvas.getContext("2d");

const posX = document.getElementById("posX");
const posY = document.getElementById("posY");
const posZ = document.getElementById("posZ");

const connectionDot =
    document.getElementById("connectionDot");

const connectionText =
    document.getElementById("connectionText");

const hostText =
    document.getElementById("hostText");

const hostValue =
    document.getElementById("hostValue");

const portValue =
    document.getElementById("portValue");

const errorMessage =
    document.getElementById("errorMessage");

const lastCommand =
    document.getElementById("lastCommand");

const jogStep =
    document.getElementById("jogStep");

const workspaceSize =
    document.getElementById("workspaceSize");


function setConnectionState(status) {
    state.connected = Boolean(status.connected);

    connectionDot.classList.remove(
        "connected",
        "error"
    );

    if (status.state === "Error") {
        connectionDot.classList.add("error");
    } else if (state.connected) {
        connectionDot.classList.add("connected");
    }

    connectionText.textContent =
        status.state || "Disconnected";

    hostText.textContent =
        status.host || state.host;

    hostValue.textContent =
        status.host || state.host;

    portValue.textContent =
        status.port ?? state.port;

    if (status.last_error) {
        errorMessage.textContent =
            status.last_error;

        errorMessage.classList.remove("hidden");
    } else {
        errorMessage.classList.add("hidden");
    }
}


function updateState(status) {
    setConnectionState(status);

    if (status.position) {
        state.position = {
            ...state.position,
            ...status.position
        };
    }

    if (status.machine) {
        state.machine = {
            ...state.machine,
            ...status.machine
        };
    }

    state.host = status.host || state.host;
    state.port = status.port || state.port;

    posX.textContent =
        Number(state.position.x).toFixed(2);

    posY.textContent =
        Number(state.position.y).toFixed(2);

    posZ.textContent =
        Number(state.position.z).toFixed(2);

    workspaceSize.textContent =
        `${state.machine.width} × ${state.machine.height} mm`;

    lastCommand.textContent =
        status.last_command || "—";

    // The position now comes from FluidNC's actual
    // realtime status report.
    if (status.controller_status) {
        const controllerState =
            status.controller_status.state;

        if (
            controllerState &&
            controllerState !== "Disconnected"
        ) {
            connectionText.textContent =
                controllerState;
        }
    }

    drawWorkspace();
}


async function api(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            "Content-Type": "application/json"
        },
        ...options
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(
            data.error || "Request failed"
        );
    }

    return data;
}


async function refreshStatus() {
    try {
        const status =
            await api("/api/status");

        updateState(status);
    } catch (error) {
        setConnectionState({
            connected: false,
            state: "Error",
            host: state.host,
            port: state.port,
            last_error: error.message
        });
    }
}


async function connect() {
    try {
        const status =
            await api("/api/connect", {
                method: "POST"
            });

        updateState(status);
    } catch (error) {
        await refreshStatus();
    }
}


async function disconnect() {
    try {
        const status =
            await api("/api/disconnect", {
                method: "POST"
            });

        updateState(status);
    } catch (error) {
        await refreshStatus();
    }
}


async function jog(axis, distance) {
    if (!state.connected) {
        return;
    }

    try {
        const status =
            await api("/api/jog", {
                method: "POST",
                body: JSON.stringify({
                    axis,
                    distance
                })
            });

        updateState(status);
    } catch (error) {
        showError(error.message);
    }
}


async function home(axis) {
    if (!state.connected) {
        return;
    }

    try {
        const status =
            await api("/api/home", {
                method: "POST",
                body: JSON.stringify({
                    axis
                })
            });

        updateState(status);
    } catch (error) {
        showError(error.message);
    }
}


async function moveTo(x, y) {
    if (!state.connected) {
        return;
    }

    try {
        const status =
            await api("/api/move", {
                method: "POST",
                body: JSON.stringify({
                    x,
                    y
                })
            });

        updateState(status);
    } catch (error) {
        showError(error.message);
    }
}


function showError(message) {
    errorMessage.textContent = message;
    errorMessage.classList.remove("hidden");

    setTimeout(() => {
        errorMessage.classList.add("hidden");
    }, 5000);
}


function resizeCanvas() {
    const container =
        canvas.parentElement;

    const width =
        container.clientWidth - 24;

    const height =
        container.clientHeight - 24;

    const ratio =
        state.machine.width /
        state.machine.height;

    let canvasWidth = width;
    let canvasHeight = width / ratio;

    if (canvasHeight > height) {
        canvasHeight = height;
        canvasWidth = height * ratio;
    }

    const dpr =
        window.devicePixelRatio || 1;

    canvas.width =
        Math.round(canvasWidth * dpr);

    canvas.height =
        Math.round(canvasHeight * dpr);

    canvas.style.width =
        `${canvasWidth}px`;

    canvas.style.height =
        `${canvasHeight}px`;

    ctx.setTransform(
        dpr,
        0,
        0,
        dpr,
        0,
        0
    );

    drawWorkspace();
}


function drawWorkspace() {
    if (!canvas.width || !canvas.height) {
        return;
    }

    const width =
        parseFloat(canvas.style.width) || 1;

    const height =
        parseFloat(canvas.style.height) || 1;

    ctx.clearRect(
        0,
        0,
        width,
        height
    );

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(
        0,
        0,
        width,
        height
    );

    const mmToPxX =
        width / state.machine.width;

    const mmToPxY =
        height / state.machine.height;

    // Grid
    ctx.lineWidth = 1;
    ctx.strokeStyle = "#e5e8eb";

    const grid = 10;

    for (
        let x = 0;
        x <= state.machine.width;
        x += grid
    ) {
        const px = x * mmToPxX;

        ctx.beginPath();
        ctx.moveTo(px, 0);
        ctx.lineTo(px, height);
        ctx.stroke();
    }

    for (
        let y = 0;
        y <= state.machine.height;
        y += grid
    ) {
        const py =
            height -
            y * mmToPxY;

        ctx.beginPath();
        ctx.moveTo(0, py);
        ctx.lineTo(width, py);
        ctx.stroke();
    }

    // Outer machine boundary
    ctx.strokeStyle = "#aeb6bd";
    ctx.lineWidth = 2;

    ctx.strokeRect(
        0,
        0,
        width,
        height
    );

    // Axes
    ctx.strokeStyle = "#858e96";
    ctx.lineWidth = 1;

    ctx.beginPath();
    ctx.moveTo(0, height);
    ctx.lineTo(width, height);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(0, height);
    ctx.stroke();

    // Coordinate labels
    ctx.fillStyle = "#69727a";
    ctx.font = "11px system-ui";

    ctx.fillText(
        "0, 0",
        5,
        height - 6
    );

    ctx.fillText(
        `${state.machine.width}`,
        width - 28,
        height - 6
    );

    ctx.fillText(
        `${state.machine.height}`,
        5,
        14
    );

    // Current head position
    const px =
        state.position.x * mmToPxX;

    const py =
        height -
        state.position.y * mmToPxY;

    ctx.beginPath();
    ctx.arc(
        px,
        py,
        7,
        0,
        Math.PI * 2
    );

    ctx.fillStyle = "#1769aa";
    ctx.fill();

    ctx.beginPath();
    ctx.arc(
        px,
        py,
        11,
        0,
        Math.PI * 2
    );

    ctx.strokeStyle = "#1769aa";
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = "#1769aa";
    ctx.font = "12px system-ui";

    ctx.fillText(
        `X ${state.position.x.toFixed(1)}  Y ${state.position.y.toFixed(1)}`,
        Math.min(
            px + 14,
            width - 130
        ),
        Math.max(
            py - 12,
            15
        )
    );
}


function workspaceClick(event) {
    if (!state.connected) {
        return;
    }

    const rect =
        canvas.getBoundingClientRect();

    const px =
        event.clientX - rect.left;

    const py =
        event.clientY - rect.top;

    const x =
        px / rect.width *
        state.machine.width;

    const y =
        (1 - py / rect.height) *
        state.machine.height;

    moveTo(x, y);
}


document
    .querySelectorAll(".jog-button")
    .forEach(button => {
        button.addEventListener(
            "click",
            () => {
                const axis =
                    button.dataset.axis;

                const direction =
                    Number(button.dataset.direction);

                const step =
                    Number(jogStep.value);

                jog(
                    axis,
                    direction * step
                );
            }
        );
    });


document
    .getElementById("connectButton")
    .addEventListener(
        "click",
        connect
    );


document
    .getElementById("disconnectButton")
    .addEventListener(
        "click",
        disconnect
    );


document
    .getElementById("homeX")
    .addEventListener(
        "click",
        () => home("X")
    );


document
    .getElementById("homeY")
    .addEventListener(
        "click",
        () => home("Y")
    );


document
    .getElementById("homeXY")
    .addEventListener(
        "click",
        () => home("XY")
    );


canvas.addEventListener(
    "click",
    workspaceClick
);


document.addEventListener(
    "keydown",
    event => {
        const tag =
            event.target.tagName.toLowerCase();

        if (
            tag === "input" ||
            tag === "select" ||
            tag === "textarea"
        ) {
            return;
        }

        let axis = null;
        let direction = 0;

        switch (event.key) {
            case "ArrowLeft":
                axis = "X";
                direction = -1;
                break;

            case "ArrowRight":
                axis = "X";
                direction = 1;
                break;

            case "ArrowUp":
                axis = "Y";
                direction = 1;
                break;

            case "ArrowDown":
                axis = "Y";
                direction = -1;
                break;

            case "PageUp":
                axis = "Z";
                direction = 1;
                break;

            case "PageDown":
                axis = "Z";
                direction = -1;
                break;

            default:
                return;
        }

        event.preventDefault();

        let step =
            Number(jogStep.value);

        if (event.shiftKey) {
            step *= 10;
        }

        jog(
            axis,
            direction * step
        );
    }
);


window.addEventListener(
    "resize",
    resizeCanvas
);


resizeCanvas();
refreshStatus();

// Keep the displayed state reasonably fresh.
setInterval(
    refreshStatus,
    1000
);
