(function () {
    "use strict";
    const root = document.getElementById("api-docs");
    const specUrl = root.dataset.specUrl;
    const groupsEl = document.getElementById("groups");
    const authInput = document.getElementById("auth-header");
    document.getElementById("spec-link").href = specUrl;
    try {
        authInput.value = window.localStorage.getItem("rest_api_auth") || "";
    } catch {
        /* storage unavailable */
    }
    authInput.addEventListener("change", () => {
        try {
            window.localStorage.setItem("rest_api_auth", authInput.value);
        } catch {
            /* storage unavailable */
        }
    });

    function el(tag, attrs = {}, ...children) {
        const node = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs)) {
            if (key === "class") {
                node.className = value;
            } else if (key.startsWith("on")) {
                node.addEventListener(key.slice(2), value);
            } else {
                node.setAttribute(key, value);
            }
        }
        for (const child of children.flat()) {
            if (child !== null && child !== undefined) {
                node.append(child.nodeType ? child : document.createTextNode(String(child)));
            }
        }
        return node;
    }

    function curl(method, url, auth, body) {
        const parts = [`curl -X ${method} '${url}'`];
        if (root.dataset.db) {
            parts.push(`-H 'X-Odoo-Database: ${root.dataset.db}'`);
        }
        if (auth) {
            parts.push(`-H 'Authorization: ${auth}'`);
        }
        if (body) {
            parts.push(`-H 'Content-Type: application/json' -d '${body.replace(/'/g, "'\\''")}'`);
        }
        return parts.join(" \\\n  ");
    }

    function operation(server, path, method, op) {
        const params = op.parameters || [];
        const inputs = {};
        const hasBody = Boolean(op.requestBody);
        const bodyInput = hasBody ? el("textarea", { placeholder: '{"name": "Example"}' }) : null;
        const output = el("div");
        const paramRows = params.map((p) => {
            inputs[p.name] = el("input", { placeholder: p.example || (p.schema && p.schema.type) || "" });
            return el("div", { class: "row" },
                el("label", {}, el("code", {}, p.name), p.required ? " *" : "", el("span", { class: "muted" }, ` ${p.in}`)),
                inputs[p.name]);
        });
        async function send() {
            let finalPath = path;
            const query = new URLSearchParams();
            for (const p of params) {
                const value = inputs[p.name].value.trim();
                if (p.in === "path") {
                    finalPath = finalPath.replace(`{${p.name}}`, encodeURIComponent(value));
                } else if (value) {
                    query.set(p.name, value);
                }
            }
            const url = server + finalPath + (query.toString() ? `?${query}` : "");
            // same origin: the page's cookie selects the database (the API itself ignores web sessions)
            const headers = {};
            const auth = authInput.value.trim();
            if (auth && op.security === undefined) {
                headers.Authorization = auth;
            }
            const body = bodyInput && bodyInput.value.trim() ? bodyInput.value.trim() : null;
            if (body) {
                headers["Content-Type"] = "application/json";
            }
            output.replaceChildren(el("p", { class: "muted" }, "Sending..."));
            try {
                const response = await fetch(url, { method: method.toUpperCase(), headers, body, credentials: "same-origin" });
                const text = await response.text();
                let pretty = text;
                try {
                    pretty = JSON.stringify(JSON.parse(text), null, 2);
                } catch {
                    /* not JSON */
                }
                output.replaceChildren(
                    el("p", {}, el("span", { class: `status ${response.ok ? "ok" : "ko"}` }, `${response.status}`),
                        ` ${response.statusText}`),
                    el("pre", { class: "response" }, pretty.slice(0, 20000)),
                    el("p", { class: "muted" }, "curl"),
                    el("pre", { class: "curl" }, curl(method.toUpperCase(), url, headers.Authorization, body)));
            } catch (error) {
                output.replaceChildren(el("p", { class: "ko" }, String(error)));
            }
        }
        return el("details", { class: "op", "data-search": `${method} ${path} ${op.summary || ""} ${(op.tags || []).join(" ")}`.toLowerCase() },
            el("summary", {},
                el("span", { class: `method m-${method}` }, method.toUpperCase()),
                el("span", { class: "path" }, path),
                el("span", { class: "muted" }, op.summary || ""),
                el("span", { class: "lock" }, op.security && !op.security.length ? "public" : "🔒 auth")),
            el("div", { class: "body" },
                op.description ? el("p", {}, op.description) : null,
                paramRows.length ? el("div", {}, el("h4", {}, "Parameters"), paramRows) : null,
                hasBody ? el("div", {}, el("h4", {}, "JSON body"), bodyInput) : null,
                el("button", { class: "try", type: "button", onclick: send }, "Try it"),
                output));
    }

    function render(spec) {
        document.getElementById("title").textContent = spec.info.title;
        document.getElementById("description").textContent = spec.info.description || "";
        const server = (spec.servers && spec.servers[0] && spec.servers[0].url) || "/api/v1";
        const byTag = new Map((spec.tags || []).map((t) => [t.name, []]));
        for (const [path, item] of Object.entries(spec.paths)) {
            for (const [method, op] of Object.entries(item)) {
                const tag = (op.tags && op.tags[0]) || "Other";
                if (!byTag.has(tag)) {
                    byTag.set(tag, []);
                }
                byTag.get(tag).push(operation(server, path, method, op));
            }
        }
        groupsEl.replaceChildren(...[...byTag.entries()].filter(([, ops]) => ops.length).map(([tag, ops]) =>
            el("section", { class: "group" }, el("h2", {}, tag), ops)));
    }

    document.getElementById("filter").addEventListener("input", (ev) => {
        const query = ev.target.value.trim().toLowerCase();
        for (const op of groupsEl.querySelectorAll(".op")) {
            op.style.display = !query || op.dataset.search.includes(query) ? "" : "none";
        }
        for (const group of groupsEl.querySelectorAll(".group")) {
            group.style.display = [...group.querySelectorAll(".op")].some((op) => op.style.display !== "none") ? "" : "none";
        }
    });

    fetch(specUrl, { credentials: "same-origin" })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then(render)
        .catch((error) => groupsEl.replaceChildren(el("p", { class: "ko" }, `Could not load the specification: ${error}`)));
})();
