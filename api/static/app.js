"use strict";

// ---------- helpers ----------

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const MAX_BYTES = 256 * 1024;

function b64(buf) {
    let s = "";
    for (const byte of new Uint8Array(buf)) s += String.fromCharCode(byte);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function unb64(s) {
    return Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
}

async function encrypt(text) {
    const key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt"]);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(text));
    return { ct: b64(ct), iv: b64(iv), key: b64(await crypto.subtle.exportKey("raw", key)) };
}

async function decrypt(ct, iv, keyStr) {
    const key = await crypto.subtle.importKey("raw", unb64(keyStr), "AES-GCM", false, ["decrypt"]);
    const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(iv) }, key, unb64(ct));
    return new TextDecoder().decode(pt);
}

// what a wrong key "decrypts" to: GCM's keystream (AES-CTR) without the tag check.
// output is random-looking bytes, different per key, same for the same key.
async function wrongKeyDecrypt(ct, iv, keyStr) {
    let raw;
    try { raw = unb64(keyStr); } catch { raw = null; }
    if (!raw || raw.length !== 32) {
        raw = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(keyStr)));
    }
    const key = await crypto.subtle.importKey("raw", raw, "AES-CTR", false, ["decrypt"]);
    const counter = new Uint8Array(16);
    counter.set(unb64(iv));
    counter[15] = 2; // GCM encrypts the payload starting at counter block 2
    const body = unb64(ct).slice(0, -16);
    return new Uint8Array(await crypto.subtle.decrypt({ name: "AES-CTR", counter, length: 32 }, key, body));
}

function flash(btn, msg) {
    const orig = btn.dataset.label || (btn.dataset.label = btn.textContent);
    btn.textContent = msg;
    clearTimeout(btn._t);
    btn._t = setTimeout(() => { btn.textContent = orig; }, 1400);
}

async function copy(btn, value) {
    try { await navigator.clipboard.writeText(value); flash(btn, "Copied"); }
    catch { flash(btn, "Failed"); }
}

function store(fn) {
    try { return fn(sessionStorage); } catch { return null; }
}

// tab inserts spaces, ctrl/cmd+enter submits
function editorKeys(textarea, form) {
    textarea.addEventListener("keydown", (e) => {
        if (e.key === "Tab") {
            e.preventDefault();
            textarea.setRangeText("    ", textarea.selectionStart, textarea.selectionEnd, "end");
        } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && form) {
            e.preventDefault();
            form.requestSubmit();
        }
    });
}

function ago(seconds) {
    const d = Date.now() / 1000 - seconds;
    if (d < 60) return "now";
    if (d < 3600) return Math.floor(d / 60) + "m";
    if (d < 86400) return Math.floor(d / 3600) + "h";
    if (d < 86400 * 30) return Math.floor(d / 86400) + "d";
    if (d < 86400 * 365) return Math.floor(d / 86400 / 30) + "mo";
    return Math.floor(d / 86400 / 365) + "y";
}

// ---------- pages ----------

const pages = {
    index() {
        const text = $("#text");
        const form = $("#pasteForm");
        const btn = $("#createButton");
        const status = $("#status");
        let saving = false;
        editorKeys(text, form);

        text.addEventListener("input", () => {
            const n = text.value.length;
            // base64 + json overhead: ~4/3 of the plaintext must fit in the request limit
            const over = new TextEncoder().encode(text.value).length * 4 / 3 + 200 > MAX_BYTES;
            status.textContent = !n ? "" : over ? "Too large" : n + " chars";
            btn.disabled = saving || over;
        });

        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            // requestSubmit() (cmd+enter) ignores the disabled button, so guard here
            if (saving || !text.value) return;
            saving = true;
            btn.disabled = true;
            btn.textContent = "Saving…";
            try {
                const { ct, iv, key } = await encrypt(text.value);
                const res = await fetch("/create", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ ct, iv }),
                });
                if (!res.ok) {
                    throw new Error({ 413: "Too large", 429: "Slow down, try again shortly" }[res.status] || "Upload failed");
                }
                const { id } = await res.json();
                store(s => s.setItem("fresh", id));
                location.href = "/" + id + "#" + key;
            } catch (err) {
                status.textContent = err.message;
                saving = false;
                btn.disabled = false;
                btn.textContent = "Save";
            }
        });
    },

    async view() {
        const data = JSON.parse($("#payload").textContent);
        const box = $("#text");
        const status = $("#status");
        const copyBtn = $("#copyButton");
        const dlBtn = $("#downloadButton");

        // ctrl/cmd+a anywhere selects only the paste, not the page chrome
        document.addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "a") {
                e.preventDefault();
                box.focus();
                box.select();
            }
        });

        copyBtn.onclick = (e) => copy(e.target, box.value);
        $("#linkButton").onclick = (e) => copy(e.target, location.href);
        $("#noticeCopy").onclick = (e) => copy(e.target, location.href);
        dlBtn.onclick = () => {
            const a = document.createElement("a");
            a.href = URL.createObjectURL(new Blob([box.value], { type: "text/plain" }));
            a.download = data.id + ".txt";
            a.click();
            URL.revokeObjectURL(a.href);
        };

        if (store(s => s.getItem("fresh")) === data.id) {
            store(s => s.removeItem("fresh"));
            $("#notice").hidden = false;
        }

        const hex = (bytes) => [...bytes].map(b => b.toString(16).padStart(2, "0")).join("");
        const lock = (why, bytes) => {
            box.value = hex(bytes);
            box.classList.add("locked");
            status.textContent = why;
        };

        const keyStr = location.hash.slice(1);
        // no key: show the stored ciphertext (minus the GCM tag) as hex
        if (!keyStr) return lock("Missing key · showing encrypted bytes", unb64(data.ct).slice(0, -16));
        try {
            box.value = await decrypt(data.ct, data.iv, keyStr);
        } catch {
            return lock("Wrong key · showing what this key decrypts to", await wrongKeyDecrypt(data.ct, data.iv, keyStr));
        }
        const lines = box.value.split("\n").length;
        status.textContent = lines + (lines === 1 ? " line" : " lines") + " · " + box.value.length + " chars";
        copyBtn.disabled = dlBtn.disabled = false;
    },

    panel() {
        const tbody = $("#table tbody");
        const rows = tbody ? $$("tr", tbody) : [];
        const filter = $("#filter");
        const selectAll = $("#selectAll");
        const bulk = $("#bulkDelete");
        const now = Date.now() / 1000;
        const box = (r) => $("input[type=checkbox]", r);
        const visible = () => rows.filter(r => !r.hidden);
        const checked = (list) => list.filter(r => box(r).checked);

        rows.forEach(r => { $(".age", r).textContent = ago(+r.dataset.ts); });
        $("#recent").textContent = rows.filter(r => now - r.dataset.ts < 86400).length;
        if (rows.length) $("#newest").textContent = ago(Math.max(...rows.map(r => +r.dataset.ts)));

        function refresh() {
            const sel = checked(rows).length;
            const vis = visible();
            const visSel = checked(vis).length;
            bulk.disabled = sel === 0;
            bulk.textContent = sel ? "Delete " + sel : "Delete";
            $("#count").textContent = vis.length + " / " + rows.length;
            selectAll.checked = vis.length > 0 && visSel === vis.length;
            selectAll.indeterminate = visSel > 0 && visSel < vis.length;
            const noMatch = $("#noMatch");
            if (noMatch) noMatch.hidden = vis.length > 0;
            rows.forEach(r => r.classList.toggle("selected", box(r).checked));
        }

        filter.addEventListener("input", () => {
            const q = filter.value.trim().toLowerCase();
            rows.forEach(r => {
                r.hidden = Boolean(q) && !r.dataset.name.toLowerCase().includes(q);
                if (r.hidden) box(r).checked = false;
            });
            refresh();
        });

        selectAll.addEventListener("change", () => {
            visible().forEach(r => { box(r).checked = selectAll.checked; });
            refresh();
        });

        if (tbody) tbody.addEventListener("change", refresh);

        $("#listForm").addEventListener("submit", (e) => {
            const n = checked(rows).length;
            if (!n || !confirm("Permanently delete " + n + " paste" + (n === 1 ? "" : "s") + "?")) e.preventDefault();
        });

        $$(".sort").forEach(btn => btn.addEventListener("click", () => {
            const key = btn.dataset.key;
            const desc = btn.classList.contains("active") ? !btn.classList.contains("desc") : key !== "name";
            $$(".sort").forEach(b => b.classList.remove("active", "desc"));
            btn.classList.add("active");
            btn.classList.toggle("desc", desc);
            const val = r => key === "name" ? r.dataset.name : +r.dataset[key];
            rows.sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * (desc ? -1 : 1));
            rows.forEach(r => tbody.appendChild(r));
        }));

        document.addEventListener("keydown", (e) => {
            if (e.key === "/" && document.activeElement !== filter) {
                e.preventDefault();
                filter.focus();
            } else if (e.key === "Escape" && document.activeElement === filter) {
                filter.value = "";
                filter.dispatchEvent(new Event("input"));
                filter.blur();
            }
        });

        const msg = $("#flash");
        if (msg) {
            history.replaceState(null, "", "/panel");
            setTimeout(() => msg.classList.add("fade"), 3000);
        }

        refresh();
    },
};

// ---------- boot ----------

// any form with data-confirm asks first
document.addEventListener("submit", (e) => {
    const text = e.target.dataset && e.target.dataset.confirm;
    if (text && !confirm(text)) e.preventDefault();
});

const init = pages[document.body.dataset.page];
if (init) init();
