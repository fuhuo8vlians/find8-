import io
import json
import os
import sys
import threading
import urllib.parse
import webbrowser

from flask import Flask, Response, jsonify, render_template, request, send_file
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

from core.config import load_config, save_config
from core.data_manager import (
    add_asset,
    add_batch_assets,
    add_company,
    add_company_to_project,
    add_project,
    delete_asset,
    delete_assets_batch,
    delete_project,
    export_excel_bytes,
    extract_domains,
    filter_assets,
    get_assets,
    get_company_names,
    get_companies,
    get_project_companies,
    get_projects,
    get_unique_values,
    init as init_data,
    parse_excel,
    remove_company_from_project,
    resolve_stream,
    update_asset_dns,
)
from core.proxy import disable_proxy, enable_proxy, get_proxy_status, validate_proxy

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
app.config["SECRET_KEY"] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

_scan_thread = None
_scan_running = False

init_data()
ALLOWED_EXTENSIONS = {"xlsx", "xls"}


# ============================================================
#  页面路由
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
#  公司 API
# ============================================================
@app.route("/api/companies", methods=["GET"])
def api_get_companies():
    return jsonify(get_companies())


@app.route("/api/companies", methods=["POST"])
def api_add_company():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "公司名称不能为空"}), 400
    company = add_company(name)
    return jsonify(company)


# ============================================================
#  项目 API
# ============================================================
@app.route("/api/projects", methods=["GET"])
def api_get_projects():
    return jsonify(get_projects())


@app.route("/api/projects", methods=["POST"])
def api_add_project():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "项目名称不能为空"}), 400
    project = add_project(name, data.get("description", ""))
    return jsonify(project)


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def api_delete_project(project_id):
    delete_project(project_id)
    return jsonify({"status": "ok"})


@app.route("/api/projects/<int:project_id>/companies", methods=["GET"])
def api_get_project_companies(project_id):
    return jsonify(get_project_companies(project_id))


@app.route("/api/projects/<int:project_id>/companies", methods=["POST"])
def api_add_company_to_project(project_id):
    data = request.get_json() or {}
    company_id = data.get("companyId")
    if not company_id:
        return jsonify({"error": "companyId 不能为空"}), 400
    result = add_company_to_project(project_id, company_id)
    if not result:
        return jsonify({"error": "公司不存在"}), 404
    return jsonify({"status": "ok"})


@app.route("/api/projects/<int:project_id>/companies/<int:company_id>", methods=["DELETE"])
def api_remove_company_from_project(project_id, company_id):
    remove_company_from_project(project_id, company_id)
    return jsonify({"status": "ok"})


# ============================================================
#  资产筛选 API
# ============================================================
@app.route("/api/assets/filter", methods=["POST"])
def api_filter_assets():
    data = request.get_json() or {}
    result = filter_assets(
        project_ids=data.get("projectIds"),
        company_ids=data.get("companyIds"),
        company_names=data.get("companyNames"),
        root_domains=data.get("rootDomains"),
        sub_domain_pattern=data.get("subDomainPattern"),
        ip_pattern=data.get("ipPattern"),
    )
    return jsonify(result)


@app.route("/api/assets/unique-values", methods=["GET"])
def api_unique_values():
    field = request.args.get("field", "")
    if field not in ("rootDomain", "ip", "companyName"):
        return jsonify({"error": "不支持的字段"}), 400
    return jsonify(get_unique_values(field))


# ============================================================
#  资产 API
# ============================================================
@app.route("/api/assets", methods=["GET"])
def api_get_assets():
    sort_by = request.args.get("sort", None)
    sort_order = request.args.get("order", "asc")
    company = request.args.get("company", None)
    return jsonify(get_assets(sort_by=sort_by, sort_order=sort_order, company_filter=company))


@app.route("/api/assets", methods=["POST"])
def api_add_asset():
    data = request.get_json() or {}
    company_name = data.get("companyName", "").strip()
    root_domains = data.get("rootDomain", [])
    if isinstance(root_domains, str):
        root_domains = [d.strip() for d in root_domains.splitlines() if d.strip()]
    if not company_name:
        return jsonify({"error": "公司名称不能为空"}), 400
    if not root_domains:
        return jsonify({"error": "根域名不能为空"}), 400
    result = add_asset(company_name, root_domains, data.get("subDomain", ""), data.get("url", ""), data.get("projectId"))
    return jsonify(result)


@app.route("/api/assets/batch", methods=["POST"])
def api_batch_assets():
    data = request.get_json() or []
    if not data:
        return jsonify({"error": "数据为空"}), 400

    def generate():
        result = add_batch_assets(data)
        yield json.dumps(result, ensure_ascii=False) + "\n"

    return Response(generate(), mimetype="application/json")


@app.route("/api/assets/<int:asset_id>", methods=["DELETE"])
def api_delete_asset(asset_id):
    delete_asset(asset_id)
    return jsonify({"status": "ok"})


@app.route("/api/assets/batch-delete", methods=["POST"])
def api_batch_delete_assets():
    data = request.get_json() or {}
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"error": "请选择要删除的资产"}), 400
    deleted = delete_assets_batch(ids)
    return jsonify({"deleted": deleted})


@app.route("/api/company-names", methods=["GET"])
def api_company_names():
    return jsonify(get_company_names())


@app.route("/api/assets/<int:asset_id>/dns", methods=["PUT"])
def api_update_dns(asset_id):
    asset = update_asset_dns(asset_id)
    if not asset:
        return jsonify({"error": "资产不存在"}), 404
    return jsonify(asset)


# ============================================================
#  DNS 解析 API（流式）
# ============================================================
@app.route("/api/dns-resolve", methods=["POST"])
def api_dns_resolve():
    data = request.get_json() or {}
    subdomain = data.get("subdomain", "").strip()
    if not subdomain:
        return jsonify({"error": "域名不能为空"}), 400

    def generate():
        for chunk in resolve_stream(subdomain):
            yield json.dumps(chunk, ensure_ascii=False) + "\n"

    return Response(generate(), mimetype="application/json")


# ============================================================
#  Excel 导入/导出
# ============================================================
@app.route("/api/excel/import", methods=["POST"])
def api_excel_import():
    if "file" not in request.files:
        return jsonify({"error": "缺少文件"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "未选择文件"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "仅支持 .xlsx / .xls 格式"}), 400

    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", secure_filename(file.filename))
    try:
        file.save(filepath)
        result = parse_excel(filepath)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Excel解析失败: {str(e)}"}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route("/api/assets/export", methods=["GET"])
def api_export_assets():
    company = request.args.get("company", None)
    output = export_excel_bytes(company_filter=company)
    if output is None:
        return jsonify({"error": "没有资产数据可供导出"}), 400
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="资产数据.xlsx",
        max_age=0,
    )


# ============================================================
#  域名提取工具
# ============================================================
@app.route("/api/domains/extract", methods=["POST"])
def api_extract_domains():
    data = request.get_json() or {}
    text = data.get("text", "")
    domains = extract_domains(text)
    return jsonify({"domains": domains, "count": len(domains)})


# ============================================================
#  代理验证 API
# ============================================================
@app.route("/api/proxy/validate", methods=["POST"])
def api_validate_proxy():
    data = request.get_json() or {}
    socks5_url = data.get("url", "").strip()
    if not socks5_url:
        return jsonify({"error": "代理地址不能为空"}), 400
    config = load_config()
    pool_cfg = config.get("proxy", {}).get("pool", {})
    test_url = pool_cfg.get("test_url", "http://httpbin.org/ip")
    test_timeout = pool_cfg.get("test_timeout", 10)
    result = validate_proxy(socks5_url, test_url, test_timeout)
    return jsonify(result)


# ============================================================
#  SocketIO 事件
# ============================================================
@socketio.on("connect")
def on_connect():
    emit("connected", {"status": "ok"})


@socketio.on("get_config")
def on_get_config():
    config = load_config()
    emit("config", config)


@socketio.on("save_config")
def on_save_config(data):
    config = load_config()
    if "proxy" in data:
        config["proxy"].update(data["proxy"])
    if "server" in data:
        config["server"].update(data["server"])
    if "tools" in data:
        config["tools"].update(data["tools"])
    save_config(config)
    emit("config_saved", {"status": "ok"})


@socketio.on("toggle_proxy")
def on_toggle_proxy(data):
    enabled = data.get("enabled", False)
    config = load_config()
    if enabled:
        url = config["proxy"].get("socks5", "socks5://127.0.0.1:1080")
        enable_proxy(url)
    else:
        disable_proxy()
    config["proxy"]["enabled"] = enabled
    save_config(config)
    emit("proxy_status", get_proxy_status())


@socketio.on("get_proxy_status")
def on_get_proxy_status():
    config = load_config()
    status = get_proxy_status()
    status["url"] = config["proxy"].get("socks5", "")
    emit("proxy_status", status)


@socketio.on("start_scan")
def on_start_scan(data):
    global _scan_thread, _scan_running
    if _scan_running:
        emit("scan_error", {"msg": "已有扫描任务在运行中"})
        return

    module_name = data.get("module", "subdomain")
    targets = data.get("targets", [])
    selected_tools = data.get("tools", {})

    # survive_probe 使用 selectedAssets，不需要 targets
    if module_name == "survive_probe":
        if not data.get("selectedAssets"):
            emit("scan_error", {"msg": "请先勾选资产"})
            return
    elif not targets:
        emit("scan_error", {"msg": "请输入目标域名"})
        return

    if module_name in ("subdomain",) and not any(selected_tools.values()):
        emit("scan_error", {"msg": "请至少选择一个工具"})
        return

    _scan_running = True
    sid = request.sid

    def run_scan():
        global _scan_running
        try:
            if module_name == "subdomain":
                from modules.subdomain import run_subdomain_collection

                result = run_subdomain_collection(targets, selected_tools, socketio, sid)
                socketio.emit("scan_complete", result, to=sid)
                # 扫描结果自动入库
                _auto_save_scan_results(targets, result)
            elif module_name == "port_scan":
                from modules.port_scan import run_port_scan

                strategy = data.get("portStrategy", "top100")
                spray_dict = data.get("sprayDict", "small")
                tscan_opts = data.get("tscanOpts", {})
                result = run_port_scan(targets, strategy, spray_dict, tscan_opts, socketio, sid)
                socketio.emit("scan_complete", result, to=sid)
                _auto_save_scan_results(targets, result)
            elif module_name == "dir_brute":
                from modules.dir_brute import run as db_run
                dir_tool = data.get("dirTool", "brute")
                dir_config = {"dirTool": dir_tool}
                if dir_tool == "brute":
                    dir_config["bruteDict"] = data.get("bruteDict", "small")
                elif dir_tool == "dirsearch":
                    dir_config["dirsearchOpts"] = data.get("dirsearchOpts", {})
                result = db_run(targets, dir_config, socketio, sid)
                socketio.emit("scan_complete", result, to=sid)
                _auto_save_dir_results(targets, result)
            elif module_name == "survive_probe":
                from modules.survive_probe import run_survive_probe
                selected = data.get("selectedAssets", [])
                result = run_survive_probe(selected, socketio, sid)
                socketio.emit("scan_complete", result, to=sid)
            elif module_name == "js_analysis":
                from modules.js_analysis import run as js_run
                result = js_run(targets, load_config(), socketio, sid)
                socketio.emit("scan_complete", result, to=sid)
        except Exception as e:
            socketio.emit("scan_error", {"msg": str(e)}, to=sid)
        finally:
            _scan_running = False

    _scan_thread = threading.Thread(target=run_scan, daemon=True)
    _scan_thread.start()


@socketio.on("stop_scan")
def on_stop_scan():
    global _scan_running
    _scan_running = False
    try:
        from modules.subdomain import stop as sub_stop
        sub_stop()
    except Exception:
        pass
    emit("scan_stopped", {"msg": "扫描已停止"})


# ============================================================
#  工具函数
# ============================================================
def _save_port_assets(url_items):
    """端口扫描结果直接写入资产库"""
    from core.data_manager import _load_json, _save_json, ASSETS_FILE, COMPANIES_FILE, normalize_root_domain
    from datetime import datetime

    assets = _load_json(ASSETS_FILE)
    companies = _load_json(COMPANIES_FILE)
    next_id = max((a["id"] for a in assets), default=0) + 1

    # Build root domain index
    root_to_company = {}
    for c in companies:
        for rd in c.get("rootDomains", []):
            root_to_company[rd] = (c["id"], c["name"])

    # Build IP -> company mapping from existing DNS-resolved assets
    ip_to_company = {}
    for a in assets:
        ip = a.get("ip")
        cid = a.get("companyId")
        if ip and cid and cid != 1:
            if ip not in ip_to_company or a.get("rootDomain"):
                ip_to_company[ip] = {
                    "companyId": cid,
                    "companyName": a.get("companyName", ""),
                    "rootDomain": a.get("rootDomain", ""),
                    "subDomain": a.get("subDomain", ""),
                }

    # Build URL -> asset index for dedup + update-in-place
    url_to_asset = {}
    for a in assets:
        u = a.get("url", "")
        if u:
            url_to_asset[u] = a

    added = 0
    updated = 0
    url_seen = set()  # track URLs already processed in this batch
    for item in url_items:
        url = item["url"]
        if not url:
            continue

        # Parse hostname from URL
        hostname = ""
        if "://" in url:
            parsed = urllib.parse.urlparse(url)
            hostname = parsed.hostname or ""
            if not hostname:
                netloc = parsed.netloc or url.split("://")[-1].split("/")[0]
                hostname = netloc.split(":")[0] if ":" in netloc else netloc
        else:
            hostname = url.rsplit(":", 1)[0] if ":" in url else url

        if not hostname:
            continue

        # Skip duplicates within this batch
        if url in url_seen:
            continue
        url_seen.add(url)

        is_ip = bool(__import__("re").match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', hostname))

        # Determine correct company
        cid, cname = 1, "默认公司"
        matched_root = None
        if is_ip:
            ip_info = ip_to_company.get(hostname)
            if ip_info:
                cid = ip_info["companyId"]
                cname = ip_info["companyName"]
                matched_root = ip_info.get("rootDomain") or ""
        else:
            for root in sorted(root_to_company.keys(), key=len, reverse=True):
                if hostname.endswith("." + root) or hostname == root:
                    cid, cname = root_to_company[root]
                    matched_root = root
                    break

        # If URL already exists but attributed to wrong company, fix it in-place
        existing = url_to_asset.get(url)
        if existing is not None and not isinstance(existing, bool):
            if existing.get("companyId") == 1 and cid != 1:
                existing["companyId"] = cid
                existing["companyName"] = cname
                existing["rootDomain"] = matched_root or existing.get("rootDomain", "")
                existing["subDomain"] = existing.get("subDomain", "") or (hostname if matched_root else "")
                existing["ip"] = existing.get("ip") or (hostname if is_ip else None)
                updated += 1
            continue

        asset = {
            "id": next_id,
            "companyId": cid,
            "companyName": cname,
            "rootDomain": matched_root or (hostname if is_ip else ""),
            "subDomain": hostname if matched_root else ("" if is_ip else hostname),
            "url": url,
            "ip": hostname if is_ip else None,
            "dnsStatus": "pending",
            "statusCode": item.get("statusCode"),
            "title": item.get("title"),
            "fingerprint": item.get("fingerprint"),
            "cdn": None,
            "timestamp": datetime.now().isoformat(),
        }
        assets.append(asset)
        next_id += 1
        added += 1

    _save_json(ASSETS_FILE, assets)
    print(f"[*] _save_port_assets: 新增 {added} 条, 修正归属 {updated} 条 (总资产: {len(assets)})")
    return added + updated

def _auto_save_scan_results(targets, result):
    """扫描结果自动入库"""
    subdomains = result.get("subdomains", [])
    http_results = result.get("http_results", [])
    spray_results = result.get("spray_results", [])
    ports = result.get("ports", [])

    print(f"[*] _auto_save_scan_results: subdomains={len(subdomains)}, http={len(http_results)}, spray={len(spray_results)}, ports={len(ports)}")

    if subdomains:
        batch = []
        for item in subdomains:
            batch.append({"subDomain": item["subdomain"], "companyName": "", "rootDomain": targets[0] if targets else ""})
        try:
            add_batch_assets(batch)
        except Exception:
            pass

    # 端口扫描的 HTTP 结果 + 原始端口 入库
    if http_results or spray_results or ports:
        all_urls = []
        http_url_set = set()
        for h in http_results:
            url = h.get("url", "")
            if url:
                http_url_set.add(url)
                all_urls.append({
                    "url": url,
                    "statusCode": h.get("statusCode", ""),
                    "title": h.get("title", ""),
                    "fingerprint": h.get("tech", ""),
                })
        for s in spray_results:
            url = s.get("url", "")
            if url and url not in http_url_set:
                http_url_set.add(url)
                all_urls.append({
                    "url": url,
                    "statusCode": s.get("statusCode", ""),
                    "title": s.get("title", ""),
                    "fingerprint": "",
                })
        # 原始端口结果也入库（非HTTP服务的端口，如SSH/MySQL等）
        for p in ports:
            ip = p.get("ip", "")
            port = p.get("port", "")
            if ip and port:
                port_key = f"{ip}:{port}"
                # 跳过已有HTTP URL覆盖的端口
                if not any(port_key in u for u in http_url_set):
                    all_urls.append({
                        "url": port_key,
                        "statusCode": p.get("status", ""),
                        "title": "",
                        "fingerprint": p.get("fingerprint", "") or p.get("protocol", ""),
                    })
        if all_urls:
            try:
                _save_port_assets(all_urls)
                print(f"[*] 端口扫描结果已入库: {len(all_urls)} 条")
            except Exception as e:
                import traceback
                print(f"[!] 端口扫描入库失败: {e}")
                traceback.print_exc()


def _auto_save_dir_results(targets, result):
    """目录爆破结果自动入库"""
    results = result.get("results", [])
    if not results:
        return
    all_urls = []
    url_set = set()
    for r in results:
        url = r.get("url", "")
        if url and url not in url_set:
            url_set.add(url)
            all_urls.append({
                "url": url,
                "statusCode": r.get("statusCode", ""),
                "title": r.get("title", ""),
                "fingerprint": "",
            })
    if all_urls:
        try:
            _save_port_assets(all_urls)
            print(f"[*] 目录爆破结果已入库: {len(all_urls)} 条")
        except Exception as e:
            import traceback
            print(f"[!] 目录爆破入库失败: {e}")
            traceback.print_exc()


# ============================================================
#  启动
# ============================================================
def main():
    config = load_config()
    host = config["server"].get("host", "0.0.0.0")
    port = config["server"].get("port", 5500)
    web_only = "--web" in sys.argv
    if not web_only:
        url = f"http://localhost:{port}"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"[*] find8威廉斯 v1.0 启动: http://{host}:{port}")
    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
