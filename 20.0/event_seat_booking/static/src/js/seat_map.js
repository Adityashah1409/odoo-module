/* Seat map on the website: choose seats, best-seat finder, hold and countdown (no framework needed). */
(function () {
    "use strict";

    function rpc(url, params) {
        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: params }),
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.error) {
                    throw new Error((data.error.data && data.error.data.message) || data.error.message);
                }
                return data.result;
            });
    }

    function money(map, value) {
        const symbol = map.dataset.currencySymbol || "";
        const text = Number(value || 0).toFixed(2);
        return map.dataset.currencyPosition === "before" ? `${symbol} ${text}` : `${text} ${symbol}`;
    }

    function initMap(map) {
        if (map.dataset.seatReady) {
            return;
        }
        map.dataset.seatReady = "1";
        const single = map.dataset.mode === "single";
        const selected = new Map();
        const list = map.querySelector(".o_seat_selection");
        const total = map.querySelector(".o_seat_total");
        const button = map.querySelector(".o_seat_continue");
        const errorBox = map.querySelector(".o_seat_error");
        const input = map.querySelector("input[name='seat_id']");

        function showError(message) {
            if (errorBox) {
                errorBox.textContent = message || "";
                errorBox.classList.toggle("d-none", !message);
            }
        }

        function render() {
            map.querySelectorAll(".o_seat[data-seat-id]").forEach((el) => {
                el.classList.toggle("o_seat_selected", selected.has(el.dataset.seatId));
            });
            if (list) {
                list.innerHTML = "";
                if (!selected.size) {
                    const empty = document.createElement("li");
                    empty.className = "text-muted o_seat_empty";
                    empty.textContent = list.dataset.empty || "Click on free seats to choose them.";
                    list.appendChild(empty);
                }
                for (const seat of selected.values()) {
                    const item = document.createElement("li");
                    item.className = "d-flex justify-content-between o_seat_chosen";
                    item.innerHTML = `<span></span><span></span>`;
                    item.children[0].textContent = `${seat.section} · ${seat.name}`;
                    item.children[1].textContent = money(map, seat.price);
                    list.appendChild(item);
                }
            }
            if (total) {
                total.textContent = money(map, [...selected.values()].reduce((sum, s) => sum + s.price, 0));
            }
            if (button) {
                button.disabled = !selected.size;
            }
            if (input) {
                input.value = [...selected.keys()][0] || "";
            }
        }

        function toggle(el) {
            const id = el.dataset.seatId;
            if (selected.has(id)) {
                selected.delete(id);
            } else {
                if (single) {
                    selected.clear();
                }
                const section = el.closest(".o_seat_section");
                selected.set(id, {
                    name: el.dataset.seatName,
                    price: parseFloat(el.dataset.price || "0"),
                    section: section ? section.dataset.ticketName : "",
                    ticket: section ? section.dataset.ticketId : "",
                });
            }
            showError("");
            render();
        }

        map.querySelectorAll(".o_seat_mine[data-seat-id]").forEach((el) => toggle(el));

        map.addEventListener("click", (ev) => {
            const el = ev.target.closest(".o_seat[data-seat-id]");
            if (el && !el.disabled) {
                toggle(el);
            }
        });

        const best = map.querySelector(".o_seat_best_button");
        if (best) {
            best.addEventListener("click", () => {
                const ticketId = map.querySelector(".o_seat_best_section").value;
                const count = parseInt(map.querySelector(".o_seat_best_count").value || "1", 10);
                rpc("/event/seats/best", { ticket_id: ticketId, count: count }).then((result) => {
                    if (!result.seat_ids.length) {
                        showError(best.dataset.none || "Not enough free seats together in this section.");
                        return;
                    }
                    for (const [id, seat] of [...selected.entries()]) {
                        if (seat.ticket === ticketId) {
                            selected.delete(id);
                        }
                    }
                    result.seat_ids.forEach((id) => {
                        const el = map.querySelector(`.o_seat[data-seat-id='${id}']`);
                        if (el && !selected.has(String(id))) {
                            toggle(el);
                        }
                    });
                    const first = map.querySelector(".o_seat_selected");
                    if (first && first.scrollIntoView) {
                        first.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
                    }
                });
            });
        }

        if (button && !single) {
            button.addEventListener("click", () => {
                button.disabled = true;
                rpc("/event/seats/hold", { event_id: map.dataset.eventId, seat_ids: [...selected.keys()].map(Number) })
                    .then((result) => {
                        if (result.error) {
                            showError(result.error);
                            button.disabled = false;
                            return;
                        }
                        window.location.href = result.next;
                    })
                    .catch((error) => {
                        showError(error.message);
                        button.disabled = false;
                    });
            });
        }
        render();
    }

    function initCountdown(el) {
        const until = new Date(el.dataset.until.replace(" ", "T") + "Z").getTime();
        const label = el.textContent;
        const tick = () => {
            const left = Math.max(0, Math.round((until - Date.now()) / 1000));
            const minutes = String(Math.floor(left / 60)).padStart(2, "0");
            const seconds = String(left % 60).padStart(2, "0");
            el.textContent = `${label} ${minutes}:${seconds}`;
            if (!left) {
                clearInterval(timer);
                el.classList.replace("text-bg-warning", "text-bg-danger");
            }
        };
        const timer = setInterval(tick, 1000);
        tick();
    }

    function start() {
        document.querySelectorAll(".o_seat_map[data-event-id]").forEach(initMap);
        document.querySelectorAll(".o_seat_countdown[data-until]").forEach(initCountdown);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
