function fallbackCopy(text) {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.left = "-9999px";
  area.style.top = "0";
  document.body.appendChild(area);
  area.focus();
  area.select();

  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (e) {
    ok = false;
  }

  document.body.removeChild(area);
  return ok;
}

function copyToClipboard(text) {
  if (!text) {
    alert("没有可复制的内容");
    return;
  }

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard
      .writeText(text)
      .then(() => alert("已复制"))
      .catch(() => {
        alert(fallbackCopy(text) ? "已复制" : "复制失败，请手动选择复制");
      });
    return;
  }

  alert(fallbackCopy(text) ? "已复制" : "复制失败，请手动选择复制");
}

function copyText(id) {
  const el = document.getElementById(id);
  copyToClipboard(el ? el.innerText : "");
}

function copyValue(el) {
  copyToClipboard(el.value || el.innerText || "");
}

function toggleBox(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = el.style.display === "none" ? "block" : "none";
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.innerText = value;
}

function setWidth(id, value) {
  const el = document.getElementById(id);
  if (el) el.style.width = value + "%";
}

async function refreshDashboard() {
  if (!window.IWANTRUN_DASHBOARD) return;

  try {
    const res = await fetch("/api/dashboard", { cache: "no-store" });
    if (!res.ok) return;

    const data = await res.json();
    const s = data.stats;
    const n = data.net;

    setText("cpu-percent", s.cpu_percent + "%");
    setWidth("cpu-bar", s.cpu_percent);
    setText("mem-value", s.mem_used + " / " + s.mem_total);
    setText("mem-sub", "使用率 " + s.mem_percent + "%");
    setWidth("mem-bar", s.mem_percent);
    setText("disk-value", s.disk_used + " / " + s.disk_total);
    setText("disk-sub", "使用率 " + s.disk_percent + "%");
    setWidth("disk-bar", s.disk_percent);
    setText("up-speed", n.up_speed);
    setText("down-speed", n.down_speed);
    setText("total-sent", n.total_sent);
    setText("total-recv", n.total_recv);
    setText("singbox-version", data.singbox_version);
    setText("open-port-count", data.open_ports.length);

    const box = document.getElementById("open-ports-box");
    if (box) {
      box.innerHTML = data.open_ports
        .slice(0, 8)
        .map((p) => `<span class="firewall-port">${p}</span>`)
        .join("");
    }
  } catch (e) {
    // Dashboard refresh is best-effort; keep the page usable if polling fails.
  }
}

if (window.IWANTRUN_DASHBOARD) {
  refreshDashboard();
  setInterval(refreshDashboard, 3000);
}
