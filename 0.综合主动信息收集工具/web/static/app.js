// ============================================================
//  State
// ============================================================
const socket = io();
let currentTab = "dashboard";
let scanRunning = false;
let resultData = [];
let domains = [];
let sortBy = null, sortOrder = "asc";
let selectedIds = new Set();      // asset IDs
let currentAssets = [];           // last loaded asset list
let allCompanies = [];
let allProjects = [];
let filterTimeout = null;
let filterAbort = null;
let portStrategy = "top100";
let sprayDict = "small";
let tscanOpts = { np: true, nosmart: false, threads: 600, timeout: 3 };
let portTargets = [];   // cancel stale filter requests

// ============================================================
//  Init
// ============================================================
socket.on("connect", () => {
  socket.emit("get_config");
  socket.emit("get_proxy_status");
});
loadDashboardStats();
loadFilterOptions();
restoreFilterState();

// ============================================================
//  Tab Switching
// ============================================================
function switchTab(tab) {
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach(el => el.classList.remove("active"));
  const nav = document.querySelector(`.nav-item[data-tab="${tab}"]`);
  const panel = document.getElementById(`tab-${tab}`);
  if (nav) nav.classList.add("active");
  if (panel) panel.classList.add("active");
  currentTab = tab;
  if (tab === "asset-list") { loadFilterOptions(); doFilter(); }
  if (tab === "asset-single") { loadCompanyDatalist(); loadSingleProjectOptions(); }
  if (tab === "projects") loadProjects();
  if (tab === "dashboard") loadDashboardStats();
}

// ============================================================
//  Toast
// ============================================================
function showToast(msg, type) {
  type = type || "info";
  let c = document.querySelector(".toast-container");
  if (!c) { c = document.createElement("div"); c.className = "toast-container"; document.body.appendChild(c); }
  const t = document.createElement("div"); t.className = `toast ${type}`; t.textContent = msg;
  c.appendChild(t); setTimeout(() => t.remove(), 3000);
}

// ============================================================
//  Dashboard
// ============================================================
function loadDashboardStats() {
  fetch("/api/assets").then(r => r.json()).then(a => {
    const el = document.getElementById("statAssets"); if (el) el.textContent = a.length;
  }).catch(() => {});
  fetch("/api/projects").then(r => r.json()).then(p => {
    const el = document.getElementById("statProjects"); if (el) el.textContent = p.length;
  }).catch(() => {});
}

// ============================================================
//  Filter Options (load dropdowns)
// ============================================================
function loadFilterOptions() {
  fetch("/api/projects").then(r => r.json()).then(ps => {
    allProjects = ps;
    const sel = document.getElementById("fProject");
    if (sel) { const v = sel.value; sel.innerHTML = '<option value="">全部项目</option>' + ps.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join(""); sel.value = v; }
  }).catch(() => {});
  loadCompanyOptions();
}

function loadCompanyOptions() {
  fetch("/api/company-names").then(r => r.json()).then(names => {
    allCompanies = names;
    updateCompanyDropdown(names);
  }).catch(() => {});
}

function onProjectFilterChange() {
  const pid = document.getElementById("fProject")?.value;
  if (pid) {
    fetch(`/api/projects/${pid}/companies`).then(r => r.json()).then(cs => {
      updateCompanyDropdown(cs.map(c => c.name));
      doFilter();
    }).catch(() => {});
  } else {
    updateCompanyDropdown(allCompanies);
    doFilter();
  }
}

function onCompanyFilterChange() {
  doFilter();
}

function updateCompanyDropdown(names) {
  const sel = document.getElementById("companyFilter");
  if (!sel) return;
  const v = sel.value;
  sel.innerHTML = '<option value="">全部公司</option>' + names.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  sel.value = names.includes(v) ? v : "";
}

// ============================================================
//  Asset List — Filter + Render
// ============================================================
function debounceFilter() {
  if (filterTimeout) clearTimeout(filterTimeout);
  filterTimeout = setTimeout(doFilter, 300);
}

function doFilter() {
  const projectId = document.getElementById("fProject")?.value;
  const companyName = document.getElementById("companyFilter")?.value;
  const rootDomain = document.getElementById("fRootDomain")?.value.trim();
  const subDomain = document.getElementById("fSubDomain")?.value.trim();
  const ip = document.getElementById("fIP")?.value.trim();

  // 记忆筛选状态
  saveFilterState();

  const body = {};
  if (projectId) body.projectIds = [parseInt(projectId)];
  if (companyName) body.companyNames = [companyName];
  if (rootDomain) body.rootDomains = [rootDomain];
  if (subDomain) body.subDomainPattern = subDomain;
  if (ip) body.ipPattern = ip;

  // Always use filter API for consistency
  fetch("/api/assets/filter", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then(r => r.json()).then(assets => {
      currentAssets = assets;
      applySortAndRender();
    }).catch(() => {});
}

function applySortAndRender() {
  if (sortBy) {
    const rev = sortOrder === "desc";
    currentAssets.sort((a, b) => {
      let va = a[sortBy] || "", vb = b[sortBy] || "";
      if (sortBy === "ip") { va = ipSortKey(va); vb = ipSortKey(vb); return rev ? (vb > va ? 1 : -1) : (va > vb ? 1 : -1); }
      if (sortBy === "timestamp") return rev ? vb.localeCompare(va) : va.localeCompare(vb);
      va = String(va); vb = String(vb);
      return rev ? vb.localeCompare(va) : va.localeCompare(vb);
    });
  }
  renderAssetTable(currentAssets);
}

function ipSortKey(ip) {
  if (!ip) return "000.000.000.000";
  return ip.split(".").map(p => String(parseInt(p) || 0).padStart(3, "0")).join(".");
}

function loadAllAssets() {
  document.getElementById("fProject") && (document.getElementById("fProject").value = "");
  document.getElementById("companyFilter") && (document.getElementById("companyFilter").value = "");
  ["fRootDomain", "fSubDomain", "fIP"].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
  sortBy = null; sortOrder = "asc";
  document.querySelectorAll(".sort-arrow").forEach(el => { el.textContent = ""; el.classList.remove("active"); });
  fetch("/api/assets").then(r => r.json()).then(a => { currentAssets = a; renderAssetTable(a); }).catch(() => {});
}

function clearFilter() {
  document.getElementById("fProject") && (document.getElementById("fProject").value = "");
  document.getElementById("companyFilter") && (document.getElementById("companyFilter").value = "");
  ["fRootDomain", "fSubDomain", "fIP"].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
  loadAllAssets();
}

function renderAssetTable(assets) {
  const tbody = document.getElementById("assetTableBody");
  selectedIds.clear();
  document.getElementById("selectAll") && (document.getElementById("selectAll").checked = false);
  document.getElementById("btnBatchDelete") && (document.getElementById("btnBatchDelete").disabled = true);
  document.getElementById("selectedCount") && (document.getElementById("selectedCount").textContent = "0");

  if (!assets || !assets.length) {
    tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;color:var(--text-secondary);padding:30px;">无匹配数据</td></tr>';
    return;
  }
  const frag = document.createDocumentFragment();
  assets.forEach(a => {
    const tr = document.createElement("tr");
    const sc = a.dnsStatus === "resolved" ? "resolved" : a.dnsStatus === "error" ? "error" : "pending";
    const st = { pending: "待解析", resolved: "已解析", error: "失败" }[a.dnsStatus] || a.dnsStatus;
    const ts = a.timestamp ? a.timestamp.replace("T", " ").substring(0, 19) : "";
    tr.innerHTML = `<td><input type="checkbox" class="asset-checkbox" data-id="${a.id}" onchange="toggleAssetSelect(${a.id}, this.checked)"></td>
      <td>${esc(a.companyName)}</td><td>${esc(a.rootDomain)}</td><td>${esc(a.subDomain)}</td>
      <td>${a.url ? `<a href="${esc(a.url)}" target="_blank" class="asset-link">${esc(a.url)}</a>` : "-"}</td>
      <td>${a.ip || "-"}</td>
      <td>${a.statusCode || "-"}</td>
      <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(a.title||'')}">${a.title || "-"}</td><td style="max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(a.fingerprint||'')}">${a.fingerprint || "-"}</td>
      <td><span class="status-pill ${sc}">${st}</span></td>
      <td>${a.cdn ? `<span class="status-pill warning">${esc(a.cdn)}</span>` : "-"}</td>
      <td>${ts}</td>`;
    frag.appendChild(tr);
  });
  tbody.innerHTML = ""; tbody.appendChild(frag);
  document.getElementById("btnBatchDelete") && (document.getElementById("btnBatchDelete").disabled = true);
}

// ============================================================
//  Selection helpers
// ============================================================
function toggleSelectAll() {
  const checked = document.getElementById("selectAll").checked;
  document.querySelectorAll(".asset-checkbox").forEach(cb => {
    cb.checked = checked;
    const id = parseInt(cb.dataset.id);
    if (checked) selectedIds.add(id); else selectedIds.delete(id);
  });
  updateSelectionUI();
}

function toggleAssetSelect(id, checked) {
  if (checked) selectedIds.add(id); else selectedIds.delete(id);
  const allCbs = document.querySelectorAll(".asset-checkbox");
  document.getElementById("selectAll") && (document.getElementById("selectAll").checked = selectedIds.size === allCbs.length && allCbs.length > 0);
  updateSelectionUI();
}

function selectAllVisible() {
  document.querySelectorAll(".asset-checkbox").forEach(cb => { cb.checked = true; selectedIds.add(parseInt(cb.dataset.id)); });
  document.getElementById("selectAll") && (document.getElementById("selectAll").checked = true);
  updateSelectionUI();
}

function invertSelection() {
  document.querySelectorAll(".asset-checkbox").forEach(cb => {
    const id = parseInt(cb.dataset.id);
    if (selectedIds.has(id)) { selectedIds.delete(id); cb.checked = false; }
    else { selectedIds.add(id); cb.checked = true; }
  });
  updateSelectionUI();
}

function clearSelection() {
  selectedIds.clear();
  document.querySelectorAll(".asset-checkbox").forEach(cb => cb.checked = false);
  document.getElementById("selectAll") && (document.getElementById("selectAll").checked = false);
  updateSelectionUI();
}

function updateSelectionUI() {
  document.getElementById("selectedCount") && (document.getElementById("selectedCount").textContent = selectedIds.size);
  document.getElementById("btnBatchDelete") && (document.getElementById("btnBatchDelete").disabled = selectedIds.size === 0);
}

// ============================================================
//  Sort
// ============================================================
function sortAssets(field) {
  if (sortBy === field) sortOrder = sortOrder === "asc" ? "desc" : "asc";
  else { sortBy = field; sortOrder = "asc"; }
  document.querySelectorAll(".sort-arrow").forEach(el => { el.textContent = ""; el.classList.remove("active"); });
  const arrow = document.getElementById(`arrow-${field}`);
  if (arrow) { arrow.textContent = sortOrder === "asc" ? " ▲" : " ▼"; arrow.classList.add("active"); }
  applySortAndRender();
  // Re-apply checkbox state after re-render
  setTimeout(restoreCheckboxes, 50);
}

function restoreCheckboxes() {
  document.querySelectorAll(".asset-checkbox").forEach(cb => {
    cb.checked = selectedIds.has(parseInt(cb.dataset.id));
  });
  updateSelectionUI();
}

// ============================================================
//  Delete & Export
// ============================================================
function batchDeleteAssets() {
  if (selectedIds.size === 0) return;
  if (!confirm(`确认删除 ${selectedIds.size} 条资产？`)) return;
  fetch("/api/assets/batch-delete", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids: Array.from(selectedIds) })
  }).then(r => r.json()).then(d => {
    showToast(`已删除 ${d.deleted} 条`, "success");
    selectedIds.clear();
    doFilter();
    loadDashboardStats();
    loadCompanyOptions();
  }).catch(e => showToast("删除失败: " + e.message, "error"));
}

function exportAssets() {
  const company = document.getElementById("companyFilter")?.value || "";
  window.open("/api/assets/export" + (company ? "?company=" + encodeURIComponent(company) : ""), "_blank");
}

// ============================================================
//  Quick Scan — from asset list
// ============================================================
function quickScanFromList(module) {
  if (selectedIds.size === 0) { showToast("请先勾选资产", "error"); return; }

  // Get selected assets
  const selected = currentAssets.filter(a => selectedIds.has(a.id));
  if (!selected.length) { showToast("请重新筛选再试", "error"); return; }

  let targets = [];
  if (module === "subdomain") {
    const dset = new Set();
    selected.forEach(a => {
      if (a.rootDomain) dset.add(a.rootDomain);
    });
    targets = Array.from(dset);
  } else if (module === "portscan") {
    const dset = new Set();
    selected.forEach(a => {
      if (a.ip) dset.add(a.ip);
      if (a.subDomain) dset.add(a.subDomain);
      else if (a.rootDomain) dset.add(a.rootDomain);
    });
    targets = Array.from(dset);
    if (!targets.length) { showToast("所选资产无IP地址", "error"); return; }
    inlineAddLog(`选中 ${selected.length} 条 → ${targets.length} 个目标（${portStrategy}端口 / spray${sprayDict === 'large' ? '大字典' : '小字典'}）`);
    document.getElementById("btnInlineStop").style.display = "inline-block";
    document.getElementById("inlineScanLog").style.display = "block";
    document.getElementById("inlineScanLog").scrollIntoView({ behavior: "smooth" });
    socket.emit("start_scan", { module: "port_scan", targets, portStrategy, sprayDict, tscanOpts });
    return;
  } else if (module === "dirbrute") {
    // 目录爆破: 收集URL
    const dset = new Set();
    selected.forEach(a => {
      if (a.url) dset.add(a.url);
      else if (a.subDomain) {
        dset.add(a.url || ("http://" + a.subDomain));
      } else if (a.ip) {
        dset.add("http://" + a.ip);
      }
    });
    targets = Array.from(dset).filter(Boolean);
    if (!targets.length) { showToast("所选资产无有效URL", "error"); return; }
    inlineAddLog(`选中 ${selected.length} 条 → ${targets.length} 个目录爆破目标`);
    document.getElementById("btnInlineStop").style.display = "inline-block";
    document.getElementById("inlineScanLog").style.display = "block";
    document.getElementById("inlineScanLog").scrollIntoView({ behavior: "smooth" });

    // 读取目录爆破 Tab 的工具选择和选项
    const tool = document.querySelector('input[name="dirTool"]:checked')?.value || "brute";
    const data = { module: "dir_brute", targets, dirTool: tool };
    if (tool === "brute") {
      data.bruteDict = document.querySelector('input[name="bruteDict"]:checked')?.value || "small";
      inlineAddLog(`工具: Brute | 字典: ${data.bruteDict}`);
    } else {
      data.dirsearchOpts = {
        bypass403: document.getElementById("chkBypass403")?.checked ?? false,
        jsfind: document.getElementById("chkJsfind")?.checked ?? false,
        fingerprint: document.getElementById("chkFingerprint")?.checked ?? false,
        recursive: document.getElementById("chkRecursive")?.checked ?? false,
        threads: parseInt(document.getElementById("dsThreads")?.value) || 25,
      };
      inlineAddLog(`工具: dirsearch | 线程: ${data.dirsearchOpts.threads}`);
    }
    socket.emit("start_scan", data);
    return;
  } else if (module === "survive") {
    // 存活探测: 发送选中资产数据给后端
    inlineAddLog(`选中 ${selected.length} 条资产 → 存活探测 (httpx + ehole)`);
    document.getElementById("btnInlineStop").style.display = "inline-block";
    document.getElementById("inlineScanLog").style.display = "block";
    document.getElementById("inlineScanLog").scrollIntoView({ behavior: "smooth" });
    socket.emit("start_scan", { module: "survive_probe", selectedAssets: selected });
    return;
  } else {
    targets = selected.filter(a => a.url).map(a => a.url);
  }

  if (!targets.length) { showToast("所选资产无有效目标", "error"); return; }

  // Show inline scan log
  const logDiv = document.getElementById("inlineScanLog");
  logDiv.style.display = "block";
  const logArea = document.getElementById("inlineLogArea");
  logArea.innerHTML = "";
  inlineAddLog(`选中 ${selected.length} 条资产 → ${targets.length} 个目标`);
  inlineAddLog(`目标: ${targets.slice(0, 15).join(", ")}${targets.length > 15 ? " ...共" + targets.length + "个" : ""}`);
  document.getElementById("btnInlineStop").style.display = "inline-block";
  logDiv.scrollIntoView({ behavior: "smooth" });

  // 读取子域名收集 Tab 的工具选择
  const tools = {
    oneforall: document.getElementById("chkOneForAll")?.checked ?? true,
    subfinder: document.getElementById("chkSubfinder")?.checked ?? true,
    tscan: document.getElementById("chkTscan")?.checked ?? true
  };
  if (!tools.oneforall && !tools.subfinder && !tools.tscan) { showToast("请到子域名收集Tab至少勾选一个工具", "error"); return; }
  socket.emit("start_scan", { module, targets, tools });
}

function stopQuickScan() {
  socket.emit("stop_scan");
  document.getElementById("btnInlineStop").style.display = "none";
  inlineAddLog("用户停止扫描");
}

function clearInlineScan() {
  document.getElementById("inlineScanLog").style.display = "none";
  document.getElementById("btnInlineStop").style.display = "none";
}

function inlineAddLog(msg) {
  const area = document.getElementById("inlineLogArea");
  if (!area) return;
  const div = document.createElement("div");
  div.className = "log-entry system";
  div.textContent = msg;
  area.appendChild(div);
  area.scrollTop = area.scrollHeight;
}

// ============================================================
//  SocketIO — Scan events (update both classic + inline log)
// ============================================================
socket.on("scan_log", d => {
  addLog(d.level || "stdout", d.msg);
  inlineAddLog(d.msg);
});

socket.on("tool_output", d => {
  addLog(d.type, d.line);
  inlineAddLog(d.line);
});

socket.on("scan_complete", data => {
  scanRunning = false;
  document.getElementById("btnStartScan") && (document.getElementById("btnStartScan").disabled = false);
  document.getElementById("btnStopScan") && (document.getElementById("btnStopScan").disabled = true);
  document.getElementById("btnInlineStop") && (document.getElementById("btnInlineStop").style.display = "none");

  if (data.subdomains && data.subdomains.length) {
    resultData = data.subdomains;
    renderResults(data);
    document.getElementById("resultCard") && (document.getElementById("resultCard").style.display = "block");
    inlineAddLog(`扫描完成！共 ${data.total} 个子域名，已自动入库`);
  } else {
    inlineAddLog("扫描完成，未发现子域名");
  }
  if (data.total) { const el = document.getElementById("statSubdomain"); if (el) el.textContent = data.total; }
  addHistoryItem(data);
  loadDashboardStats();
  loadCompanyOptions();
  // Stay in asset-list tab, refresh data
  if (currentTab === "asset-list") doFilter();
});

socket.on("scan_error", data => {
  scanRunning = false;
  document.getElementById("btnStartScan") && (document.getElementById("btnStartScan").disabled = false);
  document.getElementById("btnStopScan") && (document.getElementById("btnStopScan").disabled = true);
  document.getElementById("btnInlineStop") && (document.getElementById("btnInlineStop").style.display = "none");
  inlineAddLog("错误: " + data.msg);
  showToast("扫描出错: " + data.msg, "error");
});

socket.on("scan_stopped", data => {
  document.getElementById("btnInlineStop") && (document.getElementById("btnInlineStop").style.display = "none");
  inlineAddLog(data.msg);
});

// ============================================================
//  Single Asset Form
// ============================================================
function loadCompanyDatalist() {
  fetch("/api/companies").then(r => r.json()).then(cs => {
    const dl = document.getElementById("companyList");
    if (dl) dl.innerHTML = cs.map(c => `<option value="${esc(c.name)}">`).join("");
  }).catch(() => {});
}

function loadSingleProjectOptions() {
  fetch("/api/projects").then(r => r.json()).then(ps => {
    const sel = document.getElementById("singleProject");
    if (sel) sel.innerHTML = '<option value="">无</option>' + ps.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
  }).catch(() => {});
}

function submitSingleAsset() {
  const cn = document.getElementById("singleCompany").value.trim();
  const rd = document.getElementById("singleRootDomains").value.trim();
  const sd = document.getElementById("singleSubDomain").value.trim();
  const ur = document.getElementById("singleUrl").value.trim();
  const pid = document.getElementById("singleProject")?.value;
  if (!cn) { showToast("请输入公司名称", "error"); return; }
  if (!rd) { showToast("请输入根域名", "error"); return; }
  const rds = rd.split("\n").map(d => d.trim()).filter(Boolean);
  const body = { companyName: cn, rootDomain: rds, subDomain: sd, url: ur };
  if (pid) body.projectId = parseInt(pid);
  fetch("/api/assets", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  }).then(r => r.json()).then(d => {
    if (d.error) { showToast(d.error, "error"); return; }
    showToast(`成功添加 ${d.added} 条`, "success");
    ["singleRootDomains", "singleSubDomain", "singleUrl"].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    loadDashboardStats(); loadCompanyOptions(); loadFilterOptions();
  }).catch(e => showToast("提交失败: " + e.message, "error"));
}

// ============================================================
//  Batch Import
// ============================================================
function submitBatchAssets() {
  const text = document.getElementById("batchSubdomains").value.trim();
  if (!text) { showToast("请输入子域名", "error"); return; }
  const batch = text.split("\n").map(l => l.trim()).filter(Boolean).map(sub => {
    let s = sub;
    if (!s.startsWith("http")) s = "http://" + s;
    let h;
    try { h = new URL(s).hostname; } catch (_) { h = s; }
    return { subDomain: h, companyName: "", rootDomain: "" };
  });
  const btn = document.getElementById("btnBatchSubmit");
  btn.disabled = true; btn.textContent = "处理中...";

  fetch("/api/assets/batch", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(batch)
  }).then(r => {
    if (!r.ok) return r.text().then(t => { throw new Error(t); });
    return r.text();
  }).then(text => {
    const lines = text.trim().split("\n");
    if (!lines.length) throw new Error("Empty response");
    const last = JSON.parse(lines[lines.length - 1]);
    showToast(`导入完成：共 ${last.total} 条，新增 ${last.new} 条`, "success");
    document.getElementById("batchSubdomains").value = "";
    loadDashboardStats(); loadCompanyOptions(); loadFilterOptions();
  }).catch(e => showToast("批量导入失败: " + e.message, "error"))
    .finally(() => { btn.disabled = false; btn.textContent = "🚀 批量导入并解析DNS"; });
}

// ============================================================
//  Excel
// ============================================================
function previewExcel() {
  const file = document.getElementById("excelFile").files[0];
  if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  fetch("/api/excel/import", { method: "POST", body: fd }).then(r => r.json()).then(d => {
    if (d.error) { showToast(d.error, "error"); return; }
    document.getElementById("excelPreview").innerHTML = `
      <div class="card" style="border-color:var(--accent);"><h3>导入成功：${d.total} 条</h3>
      <div class="table-wrap" style="max-height:200px;"><table class="result-table"><thead><tr><th>公司</th><th>根域名</th></tr></thead>
      <tbody>${d.parsed.slice(0, 20).map(a => `<tr><td>${esc(a.companyName)}</td><td>${esc(a.rootDomain)}</td></tr>`).join("")}</tbody></table></div></div>`;
    loadDashboardStats(); loadCompanyOptions(); loadFilterOptions();
  }).catch(e => showToast("Excel解析失败: " + e.message, "error"));
}

function exportAssets() {
  const company = document.getElementById("companyFilter")?.value || "";
  window.open("/api/assets/export" + (company ? "?company=" + encodeURIComponent(company) : ""), "_blank");
}

// ============================================================
//  Projects
// ============================================================
function loadProjects() {
  fetch("/api/projects").then(r => r.json()).then(projects => {
    allProjects = projects;
    renderProjects(projects);
  }).catch(() => {});
}

function renderProjects(projects) {
  const container = document.getElementById("projectList");
  if (!projects.length) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-secondary);text-align:center;">暂无项目</p></div>';
    return;
  }
  container.innerHTML = projects.map(p => `
    <div class="card project-card">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div><h3 style="margin:0;">${esc(p.name)}</h3>
          <span style="font-size:12px;color:var(--text-secondary);">${p.companyCount||0} 个公司</span>
          ${p.description ? `<span style="font-size:12px;color:var(--text-secondary);margin-left:8px;">— ${esc(p.description)}</span>` : ""}</div>
        <button class="btn btn-sm btn-danger" onclick="deleteProject(${p.id})">删除</button>
      </div>
      <div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;" id="projectComps-${p.id}">
        <span style="font-size:12px;color:var(--text-secondary);">加载中...</span>
      </div>
      <div style="margin-top:10px;display:flex;gap:8px;">
        <select id="addCompSel-${p.id}" style="flex:1;font-size:12px;"><option value="">选择公司添加...</option></select>
        <button class="btn btn-sm btn-primary" onclick="addCompanyToProject(${p.id})">添加</button>
      </div>
    </div>
  `).join("");
  projects.forEach(p => {
    loadProjectCompanies(p.id);
    loadAvailableCompaniesForProject(p.id);
  });
}

function loadProjectCompanies(pid) {
  fetch(`/api/projects/${pid}/companies`).then(r => r.json()).then(cs => {
    const container = document.getElementById(`projectComps-${pid}`);
    if (!cs.length) container.innerHTML = '<span style="font-size:12px;color:var(--text-secondary);">暂无公司</span>';
    else container.innerHTML = cs.map(c => `
      <span class="tag">${esc(c.name)}<span class="tag-close" onclick="removeCompanyFromProject(${pid},${c.id})">&#10005;</span></span>
    `).join("");
  }).catch(() => {});
}

function loadAvailableCompaniesForProject(pid) {
  fetch("/api/companies").then(r => r.json()).then(all => {
    const sel = document.getElementById(`addCompSel-${pid}`);
    if (!sel) return;
    sel.innerHTML = '<option value="">选择公司添加...</option>' + all.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  }).catch(() => {});
}

function createProject() {
  const name = document.getElementById("newProjectName").value.trim();
  if (!name) { showToast("请输入项目名称", "error"); return; }
  const desc = document.getElementById("newProjectDesc").value.trim();
  fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description: desc }) })
    .then(r => r.json()).then(() => {
      showToast("项目创建成功", "success");
      document.getElementById("newProjectName").value = "";
      document.getElementById("newProjectDesc").value = "";
      loadProjects(); loadFilterOptions(); loadDashboardStats();
    }).catch(e => showToast("创建失败: " + e.message, "error"));
}

function deleteProject(pid) {
  if (!confirm("删除项目不会删除公司数据，仅解除关联。确认？")) return;
  fetch(`/api/projects/${pid}`, { method: "DELETE" }).then(() => {
    showToast("项目已删除", "success");
    loadProjects(); loadFilterOptions(); loadDashboardStats();
  }).catch(e => showToast("删除失败: " + e.message, "error"));
}

function addCompanyToProject(pid) {
  const sel = document.getElementById(`addCompSel-${pid}`);
  const cid = parseInt(sel.value);
  if (!cid) { showToast("请选择公司", "error"); return; }
  fetch(`/api/projects/${pid}/companies`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ companyId: cid }) })
    .then(r => r.json()).then(d => {
      if (d.error) { showToast(d.error, "error"); return; }
      loadProjectCompanies(pid);
    }).catch(e => showToast("添加失败: " + e.message, "error"));
}

function removeCompanyFromProject(pid, cid) {
  fetch(`/api/projects/${pid}/companies/${cid}`, { method: "DELETE" }).then(() => {
    loadProjectCompanies(pid);
  }).catch(() => {});
}

// ============================================================
//  Domain paste helper
// ============================================================
function handleDomainPaste(e, targetId) {
  e.preventDefault();
  const pasted = (e.clipboardData || window.clipboardData).getData("text");
  document.getElementById(targetId).value = extractDomainsFromText(pasted).join("\n");
}

function extractDomainsFromText(text) {
  const domains = new Set();
  text.split(/[\n\r]+/).forEach(line => {
    const t = line.trim(); if (!t) return;
    let h;
    try { if (!t.startsWith("http")) h = new URL("http://" + t).hostname; else h = new URL(t).hostname; }
    catch (_) { h = t.split("/")[0].split(":")[0]; }
    h = h.toLowerCase().replace(/^www\./, "");
    if (/^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)+$/.test(h)) domains.add(h);
  });
  return Array.from(domains);
}

// ============================================================
//  Subdomain Tab (manual mode)
// ============================================================
function addDomainsFromInput() {
  const input = document.getElementById("domainInput");
  const text = input.value.trim();
  if (!text) return;
  text.split("\n").map(l => {
    let d = l.trim();
    if (d.includes("://")) d = d.split("://")[1].split("/")[0];
    return d.split("/")[0].split(":")[0].toLowerCase();
  }).filter(Boolean).forEach(d => { if (!domains.includes(d)) domains.push(d); });
  renderTags();
  input.value = ""; input.focus();
}

function removeDomain(idx) { domains.splice(idx, 1); renderTags(); }
function clearDomainTags() { domains = []; renderTags(); }

function renderTags() {
  document.getElementById("domainTags").innerHTML = domains.map((d, i) =>
    `<span class="tag">${esc(d)}<span class="tag-close" onclick="removeDomain(${i})">&#10005;</span></span>`
  ).join("");
}

function startScan() {
  if (scanRunning) return;
  if (!domains.length) { showToast("请先添加目标域名", "error"); return; }
  const tools = {
    oneforall: document.getElementById("chkOneForAll").checked,
    subfinder: document.getElementById("chkSubfinder").checked,
    tscan: document.getElementById("chkTscan").checked
  };
  if (!tools.oneforall && !tools.subfinder && !tools.tscan) { showToast("请至少选择一个工具", "error"); return; }
  scanRunning = true; resultData = [];
  document.getElementById("btnStartScan").disabled = true;
  document.getElementById("btnStopScan").disabled = false;
  document.getElementById("resultCard").style.display = "none";
  clearLogs();
  addLog("system", `开始扫描 ${domains.length} 个目标: ${domains.join(", ")}`);
  socket.emit("start_scan", { module: "subdomain", targets: domains, tools });
}

function stopScan() {
  socket.emit("stop_scan");
  scanRunning = false;
  document.getElementById("btnStartScan").disabled = false;
  document.getElementById("btnStopScan").disabled = true;
  addLog("system", "用户停止扫描");
}

// ============================================================
//  Log / Results
// ============================================================
function addLog(level, msg) {
  const area = document.getElementById("logArea"); if (!area) return;
  const div = document.createElement("div"); div.className = `log-entry ${level}`; div.textContent = msg;
  area.appendChild(div); area.scrollTop = area.scrollHeight;
}

function clearLogs() { const a = document.getElementById("logArea"); if (a) a.innerHTML = '<div class="log-entry system">等待开始扫描...</div>'; }

function renderResults(data) {
  const ce = document.getElementById("resultCount"); if (ce) ce.textContent = `(${data.total} 个)`;
  const tb = document.getElementById("resultBody"); if (!tb) return;
  const frag = document.createDocumentFragment();
  data.subdomains.forEach(r => {
    const tr = document.createElement("tr");
    const src = r.source || "";
    const sc = src.includes("OneForAll") && src.includes("Subfinder") ? "both"
      : src.includes("OneForAll") && src.includes("Tscan") ? "oneforall+tscan"
      : src.includes("Subfinder") && src.includes("Tscan") ? "subfinder+tscan"
      : src.includes("两者") && src.includes("Tscan") ? "both+tscan"
      : src === "Tscan" ? "tscan"
      : src === "OneForAll" ? "oneforall"
      : src === "Subfinder" ? "subfinder"
      : "both";
    tr.innerHTML = `<td style="color:var(--text-secondary)">${r.index}</td><td>${esc(r.subdomain)}</td><td><span class="source-badge ${sc}">${r.source}</span></td>`;
    frag.appendChild(tr);
  });
  tb.innerHTML = ""; tb.appendChild(frag);
}

function exportResults() {
  if (!resultData.length) return;
  const blob = new Blob([resultData.map(r => `${r.subdomain}\t# ${r.source}`).join("\n")], { type: "text/plain" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = `subdomains_${new Date().toISOString().slice(0, 10)}.txt`; a.click(); URL.revokeObjectURL(a.href);
}

function addHistoryItem(data) {
  const list = document.getElementById("historyList"); if (!list) return;
  if (list.querySelector(".empty")) list.innerHTML = "";
  const li = document.createElement("li");
  li.textContent = `结果 (${data.total || 0}个)`; li.title = data.result_file || "";
  li.onclick = () => { resultData = data.subdomains || []; renderResults(data); document.getElementById("resultCard").style.display = "block"; switchTab("subdomain"); };
  list.insertBefore(li, list.firstChild);
}

// ============================================================
//  Dir Brute
// ============================================================
let dirTargets = [];

function addDirTargets() {
  const input = document.getElementById("dirTargetInput");
  const text = input.value.trim();
  if (!text) return;
  text.split("\n").map(l => l.trim()).filter(Boolean).forEach(t => {
    let d = t;
    if (!d.startsWith("http")) d = "http://" + d;
    if (d && !dirTargets.includes(d)) dirTargets.push(d);
  });
  renderDirTags();
  input.value = ""; input.focus();
}

function clearDirTargets() { dirTargets = []; renderDirTags(); }

function renderDirTags() {
  document.getElementById("dirTargetTags").innerHTML = dirTargets.map((d, i) =>
    `<span class="tag">${esc(d)}<span class="tag-close" onclick="dirTargets.splice(${i},1);renderDirTags();">&#10005;</span></span>`
  ).join("");
}

function onDirToolChange() {
  const tool = document.querySelector('input[name="dirTool"]:checked')?.value || "brute";
  document.getElementById("bruteOpts").style.display = tool === "brute" ? "block" : "none";
  document.getElementById("dirsearchOpts").style.display = tool === "dirsearch" ? "block" : "none";
}

function startDirBrute() {
  if (scanRunning) return;
  if (!dirTargets.length) { showToast("请先添加目标URL", "error"); return; }
  scanRunning = true;
  document.getElementById("btnDirStart").disabled = true;
  document.getElementById("btnDirStop").disabled = false;
  document.getElementById("dirResultCard").style.display = "none";
  document.getElementById("dirLogArea").innerHTML = "";

  const tool = document.querySelector('input[name="dirTool"]:checked')?.value || "brute";
  const data = { module: "dir_brute", targets: dirTargets, dirTool: tool };

  if (tool === "brute") {
    const dict = document.querySelector('input[name="bruteDict"]:checked')?.value || "small";
    data.bruteDict = dict;
    dirAddLog("system", `Brute 目录爆破 | 字典: ${dict} | 目标: ${dirTargets.length} 个`);
  } else {
    data.dirsearchOpts = {
      bypass403: document.getElementById("chkBypass403")?.checked ?? false,
      jsfind: document.getElementById("chkJsfind")?.checked ?? false,
      fingerprint: document.getElementById("chkFingerprint")?.checked ?? false,
      recursive: document.getElementById("chkRecursive")?.checked ?? false,
      threads: parseInt(document.getElementById("dsThreads")?.value) || 25,
    };
    const opts = [];
    if (data.dirsearchOpts.bypass403) opts.push("403绕过");
    if (data.dirsearchOpts.jsfind) opts.push("JS提取");
    if (data.dirsearchOpts.fingerprint) opts.push("指纹");
    if (data.dirsearchOpts.recursive) opts.push("递归");
    dirAddLog("system", `dirsearch | 线程:${data.dirsearchOpts.threads} | ${opts.join(",") || "基础扫描"} | 目标: ${dirTargets.length} 个`);
  }
  socket.emit("start_scan", data);
}

function stopDirBrute() {
  socket.emit("stop_scan");
  scanRunning = false;
  document.getElementById("btnDirStart").disabled = false;
  document.getElementById("btnDirStop").disabled = true;
  dirAddLog("system", "用户停止扫描");
}

function clearDirLogs() {
  const a = document.getElementById("dirLogArea"); if (a) a.innerHTML = '<div class="log-entry system">等待开始扫描...</div>';
}

function dirAddLog(level, msg) {
  const area = document.getElementById("dirLogArea"); if (!area) return;
  const div = document.createElement("div"); div.className = `log-entry ${level}`; div.textContent = msg;
  area.appendChild(div); area.scrollTop = area.scrollHeight;
}

// ============================================================
//  Proxy
// ============================================================
function toggleProxy() { socket.emit("get_proxy_status"); socket.once("proxy_status", s => socket.emit("toggle_proxy", { enabled: !s.enabled })); }

socket.on("proxy_status", data => {
  const dot = document.getElementById("proxyDot"), label = document.getElementById("proxyLabel");
  if (data.enabled) { dot.className = "dot online"; label.textContent = "代理: " + (data.url || ""); }
  else { dot.className = "dot offline"; label.textContent = "代理关闭"; }
});

// ============================================================
//  Settings
// ============================================================
function openSettings() { document.getElementById("settingsModal").style.display = "flex"; socket.emit("get_config"); }
function closeSettings() { document.getElementById("settingsModal").style.display = "none"; }
function saveSettings() {
  socket.emit("save_config", {
    proxy: { socks5: document.getElementById("proxyUrl").value.trim() },
    server: { port: parseInt(document.getElementById("serverPort").value) || 5500 },
    tools: {
      oneforall: { work_dir: document.getElementById("ofWorkDir").value.trim() },
      subfinder: { work_dir: document.getElementById("sfWorkDir").value.trim() }
    }
  });
}
socket.on("config", data => {
  if (data.proxy) document.getElementById("proxyUrl").value = data.proxy.socks5 || "";
  if (data.server) document.getElementById("serverPort").value = data.server.port || 5500;
  if (data.tools) {
    if (data.tools.oneforall) document.getElementById("ofWorkDir").value = data.tools.oneforall.work_dir || "";
    if (data.tools.subfinder) document.getElementById("sfWorkDir").value = data.tools.subfinder.work_dir || "";
  }
});
socket.on("config_saved", () => { showToast("设置已保存", "success"); closeSettings(); });
document.addEventListener("click", e => { if (e.target.id === "settingsModal") closeSettings(); });

// ============================================================
//  Port Scan
// ============================================================
function addPortTargets() {
  const input = document.getElementById("portTargetInput");
  const text = input.value.trim();
  if (!text) return;
  text.split("\n").map(l => l.trim()).filter(Boolean).forEach(t => {
    let d = t; if (d.includes("://")) d = d.split("://")[1].split("/")[0];
    d = d.split("/")[0].split(":")[0];
    if (d && !portTargets.includes(d)) portTargets.push(d);
  });
  renderPortTags();
  input.value = ""; input.focus();
}

function clearPortTargets() { portTargets = []; renderPortTags(); }

function renderPortTags() {
  document.getElementById("portTargetTags").innerHTML = portTargets.map((d, i) =>
    `<span class="tag">${esc(d)}<span class="tag-close" onclick="portTargets.splice(${i},1);renderPortTags();">&#10005;</span></span>`
  ).join("");
}

function setPortStrategy(s) { portStrategy = s; }
function setSprayDict(d) { sprayDict = d; }

function updateTscanOpts() {
  tscanOpts = {
    np: document.getElementById("chkNp")?.checked ?? true,
    nosmart: document.getElementById("chkNosmart")?.checked ?? false,
    threads: parseInt(document.getElementById("tscanThreads")?.value) || 600,
    timeout: parseInt(document.getElementById("tscanTimeout")?.value) || 3,
  };
}

function startPortScan() {
  if (scanRunning) return;
  if (!portTargets.length) { showToast("请先添加目标IP", "error"); return; }
  scanRunning = true;
  document.getElementById("btnPortScan").disabled = true;
  document.getElementById("btnPortStop").disabled = false;
  document.getElementById("portResultCard").style.display = "none";
  document.getElementById("portHttpCard").style.display = "none";
  const area = document.getElementById("portLogArea");
  area.innerHTML = "";
  portAddLog("system", `开始端口扫描 (${portStrategy}): ${portTargets.join(", ")}`);
  socket.emit("start_scan", { module: "port_scan", targets: portTargets, portStrategy, sprayDict, tscanOpts });
}

function stopPortScan() {
  socket.emit("stop_scan");
  try { socket.emit("stop_scan"); } catch(e) {}
  scanRunning = false;
  document.getElementById("btnPortScan").disabled = false;
  document.getElementById("btnPortStop").disabled = true;
  portAddLog("system", "用户停止扫描");
}

function portAddLog(level, msg) {
  const area = document.getElementById("portLogArea"); if (!area) return;
  const div = document.createElement("div"); div.className = `log-entry ${level}`; div.textContent = msg;
  area.appendChild(div); area.scrollTop = area.scrollHeight;
}

function clearPortLogs() {
  const a = document.getElementById("portLogArea"); if (a) a.innerHTML = '<div class="log-entry system">等待开始扫描...</div>';
}

// Hook port scan results into global scan handlers
const _origScanLog = socket._callbacks?.$scan_log;
const _origToolOutput = socket._callbacks?.$tool_output;
const _origScanComplete = socket._callbacks?.$scan_complete;
const _origScanError = socket._callbacks?.$scan_error;

// Remove old handlers and re-add with port scan support
socket.off("scan_log"); socket.off("tool_output"); socket.off("scan_complete"); socket.off("scan_error"); socket.off("scan_stopped");

socket.on("scan_log", d => {
  addLog(d.level || "stdout", d.msg);
  inlineAddLog(d.msg);
  portAddLog(d.level || "stdout", d.msg);
  dirAddLog(d.level || "stdout", d.msg);
});

socket.on("tool_output", d => {
  addLog(d.type, d.line);
  inlineAddLog(d.line);
  portAddLog(d.type, d.line);
  dirAddLog(d.type, d.line);
});

socket.on("scan_complete", data => {
  scanRunning = false;
  document.getElementById("btnStartScan") && (document.getElementById("btnStartScan").disabled = false);
  document.getElementById("btnStopScan") && (document.getElementById("btnStopScan").disabled = true);
  document.getElementById("btnPortScan") && (document.getElementById("btnPortScan").disabled = false);
  document.getElementById("btnPortStop") && (document.getElementById("btnPortStop").disabled = true);
  document.getElementById("btnInlineStop") && (document.getElementById("btnInlineStop").style.display = "none");

  // Handle subdomain results
  if (data.subdomains && data.subdomains.length) {
    resultData = data.subdomains;
    renderResults(data);
    document.getElementById("resultCard") && (document.getElementById("resultCard").style.display = "block");
    inlineAddLog(`扫描完成！共 ${data.total} 个子域名，已自动入库`);
    portAddLog("success", `子域名收集完成: ${data.total} 个`);
  }
  // Handle survive probe results (must check before port scan since both have http_results)
  if (data.module === "survive_probe") {
    inlineAddLog(`存活探测完成！更新 ${data.updated} 条资产`);
    dirAddLog("success", `存活探测完成! 探测 ${data.total} 个URL, 更新 ${data.updated} 条资产`);
    loadDashboardStats(); loadCompanyOptions();
    if (currentTab === "asset-list") doFilter();
  }
  // Handle port scan results
  else if (data.ports || data.http_results) {
    document.getElementById("portResultCard") && (document.getElementById("portResultCard").style.display = "block");
    document.getElementById("portHttpCard") && (document.getElementById("portHttpCard").style.display = "block");
    if (data.ports) {
      const tb = document.getElementById("portResultBody");
      tb.innerHTML = data.ports.map((p, i) => `<tr><td>${i+1}</td><td>${esc(p.ip)}</td><td>${p.port}</td><td>${p.protocol||"-"}</td><td>${p.status||"-"}</td><td>${esc((p.fingerprint||"").substring(0,80))}</td></tr>`).join("");
    }
    if (data.http_results) {
      const tb = document.getElementById("portHttpBody");
      tb.innerHTML = data.http_results.map((h, i) => `<tr><td>${i+1}</td><td><a href="${esc(h.url)}" target="_blank" style="color:var(--accent);">${esc((h.url||"").substring(0,80))}</a></td><td>${h.statusCode||"-"}</td><td>${esc((h.title||h.tech||"").substring(0,50))}</td><td>${esc((h.tech||"").substring(0,40))}</td></tr>`).join("");
    }
    if (data.spray_results && data.spray_results.length) {
      document.getElementById("portSprayCard") && (document.getElementById("portSprayCard").style.display = "block");
      const tb = document.getElementById("portSprayBody");
      tb.innerHTML = data.spray_results.map((s, i) => `<tr><td>${i+1}</td><td><a href="${esc(s.url)}" target="_blank" style="color:var(--accent);">${esc((s.url||"").substring(0,80))}</a></td><td>${s.statusCode||"-"}</td><td>${esc((s.title||"").substring(0,50))}</td></tr>`).join("");
    }
    portAddLog("success", `扫描完成！端口:${data.total_ports} | HTTP:${data.total_http} | 存活路径:${data.total_spray||0}`);
    loadDashboardStats(); loadCompanyOptions();
    if (currentTab === "asset-list") doFilter();
  }
  // Handle dir brute results
  if (data.results) {
    document.getElementById("dirResultCard") && (document.getElementById("dirResultCard").style.display = "block");
    const ce = document.getElementById("dirResultCount"); if (ce) ce.textContent = `(${data.total} 个)`;
    const tb = document.getElementById("dirResultBody");
    if (tb) {
      tb.innerHTML = data.results.map((r, i) => `<tr><td>${i+1}</td><td><a href="${esc(r.url)}" target="_blank" style="color:var(--accent);">${esc((r.url||"").substring(0,100))}</a></td><td>${r.statusCode||"-"}</td><td>${esc((r.title||"").substring(0,50))}</td></tr>`).join("");
    }
    dirAddLog("success", `爆破完成！共发现 ${data.total} 个路径`);
    document.getElementById("btnDirStart") && (document.getElementById("btnDirStart").disabled = false);
    document.getElementById("btnDirStop") && (document.getElementById("btnDirStop").disabled = true);
  }
  if (data.total) { const el = document.getElementById("statSubdomain"); if (el) el.textContent = data.total; }
  addHistoryItem(data);
  loadDashboardStats(); loadCompanyOptions();
  if (currentTab === "asset-list") doFilter();
});

socket.on("scan_error", data => {
  scanRunning = false;
  document.getElementById("btnStartScan") && (document.getElementById("btnStartScan").disabled = false);
  document.getElementById("btnStopScan") && (document.getElementById("btnStopScan").disabled = true);
  document.getElementById("btnPortScan") && (document.getElementById("btnPortScan").disabled = false);
  document.getElementById("btnPortStop") && (document.getElementById("btnPortStop").disabled = true);
  document.getElementById("btnDirStart") && (document.getElementById("btnDirStart").disabled = false);
  document.getElementById("btnDirStop") && (document.getElementById("btnDirStop").disabled = true);
  document.getElementById("btnInlineStop") && (document.getElementById("btnInlineStop").style.display = "none");
  inlineAddLog("错误: " + data.msg);
  portAddLog("stderr", "错误: " + data.msg);
  dirAddLog("stderr", "错误: " + data.msg);
  showToast("扫描出错: " + data.msg, "error");
});

socket.on("scan_stopped", data => {
  document.getElementById("btnInlineStop") && (document.getElementById("btnInlineStop").style.display = "none");
  document.getElementById("btnPortStop") && (document.getElementById("btnPortStop").disabled = true);
  document.getElementById("btnPortScan") && (document.getElementById("btnPortScan").disabled = false);
  document.getElementById("btnDirStart") && (document.getElementById("btnDirStart").disabled = false);
  document.getElementById("btnDirStop") && (document.getElementById("btnDirStop").disabled = true);
  inlineAddLog(data.msg);
  portAddLog("system", data.msg);
  dirAddLog("system", data.msg);
});

// ============================================================
//  Utility
// ============================================================
function esc(str) { if (!str) return ""; const div = document.createElement("div"); div.textContent = str; return div.innerHTML; }

// ============================================================
//  localStorage 筛选记忆
// ============================================================
function saveFilterState() {
  const state = {
    project: document.getElementById("fProject")?.value || "",
    company: document.getElementById("companyFilter")?.value || "",
    rootDomain: document.getElementById("fRootDomain")?.value || "",
    subDomain: document.getElementById("fSubDomain")?.value || "",
    ip: document.getElementById("fIP")?.value || "",
    portStrategy: portStrategy,
    sprayDict: sprayDict,
  };
  localStorage.setItem("assetFilter", JSON.stringify(state));
}

function restoreFilterState() {
  try {
    const saved = JSON.parse(localStorage.getItem("assetFilter") || "{}");
    if (saved.portStrategy) portStrategy = saved.portStrategy;
    if (saved.sprayDict) sprayDict = saved.sprayDict;

    // 恢复下拉框和输入框
    const restoreField = (id, value) => {
      const el = document.getElementById(id);
      if (el && value) el.value = value;
    };
    restoreField("fProject", saved.project || "");
    restoreField("fRootDomain", saved.rootDomain || "");
    restoreField("fSubDomain", saved.subDomain || "");
    restoreField("fIP", saved.ip || "");

    // 公司下拉框需要在选项加载完成后恢复
    if (saved.company) {
      const sel = document.getElementById("companyFilter");
      if (sel) {
        // 等待公司列表加载完成后再设置值
        const observer = new MutationObserver(() => {
          if (sel.options.length > 1) {
            sel.value = saved.company;
            observer.disconnect();
          }
        });
        observer.observe(sel, { childList: true });
        // Fallback: 直接设置
        setTimeout(() => { sel.value = saved.company; observer.disconnect(); }, 500);
      }
    }

    // 如果有保存的项目，触发级联加载
    if (saved.project) {
      setTimeout(() => onProjectFilterChange(), 300);
    } else if (saved.company || saved.rootDomain || saved.subDomain || saved.ip) {
      setTimeout(() => doFilter(), 500);
    }
  } catch (e) { /* ignore */ }
}
