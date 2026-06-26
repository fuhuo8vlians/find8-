"""
存活探测模块 — httpx(状态码+标题+技术栈) + ehole(指纹识别)
选中资产 → 构造URL列表 → httpx探测 → ehole指纹 → 更新资产库
"""
import json
import os
import re
import shutil
from datetime import datetime

from core.config import load_config, resolve_path
from core.tool_runner import ToolRunner

_runner = ToolRunner()


def _emit(socketio, sid, event, data):
    if socketio and sid:
        socketio.emit(event, data, to=sid)


def _log(socketio, sid, msg, level="info"):
    _emit(socketio, sid, "scan_log", {"time": datetime.now().strftime("%H:%M:%S"), "msg": msg, "level": level})


def _collect_urls_from_assets(selected_assets):
    """从选中资产中收集 URL 列表，去重，优先用已有URL"""
    url_map = {}  # host_key -> best_url
    for a in selected_assets:
        existing_url = (a.get("url") or "").strip()
        subdomain = (a.get("subDomain") or "").strip()
        ip = (a.get("ip") or "").strip()
        root_domain = (a.get("rootDomain") or "").strip()

        if existing_url:
            # 确保有协议前缀
            if "://" not in existing_url:
                existing_url = "http://" + existing_url
            hostname = existing_url.split("://")[-1].split("/")[0]
            key = hostname.lower().rstrip(".")
            if key and key not in url_map:
                url_map[key] = existing_url

        if subdomain:
            key = subdomain.lower()
            if key and key not in url_map:
                url_map[key] = f"http://{subdomain}"

        if ip:
            key = ip.lower()
            if key and key not in url_map:
                url_map[key] = f"http://{ip}"

        if root_domain and not subdomain and not ip:
            key = root_domain.lower()
            if key and key not in url_map:
                url_map[key] = f"http://{root_domain}"

    return list(url_map.values())


def run_survive_probe(selected_assets, socketio, sid):
    """存活探测入口: httpx + ehole，结果直接更新资产库"""
    config = load_config()
    httpx_cfg = config["tools"].get("httpx", {})
    ehole_cfg = config["tools"].get("ehole", {})

    httpx_work_dir = resolve_path(httpx_cfg.get("work_dir", "../其他工具"))
    ehole_work_dir = resolve_path(ehole_cfg.get("work_dir", "../其他工具/ehloe_Des方案"))
    httpx_exe = os.path.join(httpx_work_dir, "httpx.exe")
    ehole_exe = os.path.join(ehole_work_dir, "ehole.exe")

    urls = _collect_urls_from_assets(selected_assets)
    if not urls:
        _log(socketio, sid, "未找到有效URL", "stderr")
        return {"total": 0, "updated": 0}

    _log(socketio, sid, f"存活探测: {len(selected_assets)} 条资产 → {len(urls)} 个URL")

    # 写入 URL 列表
    url_file = os.path.join(httpx_work_dir, "urls.txt")
    with open(url_file, "w", encoding="utf-8") as f:
        for u in urls:
            f.write(u + "\n")

    # 清理旧结果
    for fname in ["httpx_result.json", "_ehole_urls.txt", "ehole_result.xlsx"]:
        fp = os.path.join(httpx_work_dir, fname)
        if os.path.exists(fp):
            try: os.remove(fp)
            except: pass

    # ===== Step 1: httpx 探测 =====
    url_status = {}  # url -> {statusCode, title, tech}
    if os.path.exists(httpx_exe):
        _log(socketio, sid, "--- Step 1/2: httpx 状态码+标题+技术栈 ---")
        cmd = f'httpx.exe -l urls.txt -sc -title -tech-detect -json -o httpx_result.json'
        _log(socketio, sid, f"执行: {cmd}")

        returncode, output = _runner.run(
            httpx_work_dir, cmd,
            on_output=lambda d: _emit(socketio, sid, "tool_output", d),
            timeout=600,
        )
        _log(socketio, sid, f"httpx 完成 (返回码: {returncode})")

        # 解析 httpx JSON 结果
        result_file = os.path.join(httpx_work_dir, "httpx_result.json")
        if os.path.exists(result_file):
            try:
                with open(result_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content.startswith("["):
                    httpx_results = json.loads(content)
                else:
                    httpx_results = [json.loads(line) for line in content.splitlines() if line.strip()]

                for r in httpx_results:
                    url = r.get("url") or r.get("input") or ""
                    status_code = str(r.get("status_code") or r.get("status-code") or "")
                    title = r.get("title") or ""
                    tech_list = r.get("tech") or r.get("technologies") or []
                    tech = ", ".join(tech_list) if isinstance(tech_list, list) else str(tech_list)
                    if url:
                        url_status[url] = {"statusCode": status_code, "title": title, "tech": tech}
                _log(socketio, sid, f"httpx 探测到 {len(url_status)} 个存活URL")
            except Exception as e:
                _log(socketio, sid, f"httpx 结果解析失败: {e}", "stderr")
    else:
        _log(socketio, sid, f"httpx.exe 不存在({httpx_exe})，跳过", "stderr")

    # ===== Step 2: ehole 指纹识别 =====
    ehole_fingerprints = {}
    if os.path.exists(ehole_exe) and urls:
        _log(socketio, sid, "--- Step 2/2: ehole 指纹识别 ---")
        ehole_url_file = os.path.join(httpx_work_dir, "_ehole_urls.txt")
        with open(ehole_url_file, "w", encoding="utf-8") as f:
            for u in urls:
                f.write(u + "\n")

        # 复制 finger.json 和 config.ini
        for fname in ["finger.json", "config.ini"]:
            src = os.path.join(ehole_work_dir, fname)
            dst = os.path.join(httpx_work_dir, fname)
            if os.path.exists(src) and not os.path.exists(dst):
                try: shutil.copy2(src, dst)
                except: pass

        cmd = f'"{ehole_exe}" finger -l "_ehole_urls.txt" -o "ehole_result.xlsx"'
        _log(socketio, sid, f"执行: ehole finger -l _ehole_urls.txt -o ehole_result.xlsx")

        returncode, _ = _runner.run(
            httpx_work_dir, cmd,
            on_output=lambda d: _emit(socketio, sid, "tool_output", d),
            timeout=600,
        )
        _log(socketio, sid, f"ehole 完成 (返回码: {returncode})")

        # 解析 ehole Excel
        out_file = os.path.join(httpx_work_dir, "ehole_result.xlsx")
        if os.path.exists(out_file):
            try:
                import pandas as pd
                df = pd.read_excel(out_file)
                for _, row in df.iterrows():
                    url = str(row.iloc[0]) if len(row) > 0 else ""
                    fp = str(row.iloc[2]) if len(row) > 2 else ""
                    title = str(row.iloc[1]) if len(row) > 1 else ""
                    if url and url != "nan":
                        ehole_fingerprints[url] = {
                            "fingerprint": fp if fp != "nan" else "",
                            "title": title if title != "nan" else "",
                        }
                _log(socketio, sid, f"ehole 识别 {len(ehole_fingerprints)} 条指纹")
            except Exception as e:
                _log(socketio, sid, f"ehole 结果解析: {e}", "stderr")

    # ===== Step 3: 合并结果 — 只更新选中的资产 =====
    _log(socketio, sid, "--- 合并结果并更新资产库 ---")
    from core.data_manager import _load_json, _save_json, ASSETS_FILE

    def _hostname(u):
        if not u:
            return ""
        h = u.split("://")[-1].split("/")[0] if "://" in u else u.split("/")[0]
        return h.lower().rstrip(".")

    # 构建选中资产 hostname → asset 映射（只包含选中的资产）
    selected_by_host = {}  # hostname → asset
    for a in selected_assets:
        aid = a.get("id")
        if aid is None:
            continue
        hosts = set()
        u = (a.get("url") or "").strip()
        sd = (a.get("subDomain") or "").strip()
        ip_val = (a.get("ip") or "").strip()
        if u:
            hosts.add(_hostname(u))
        if sd:
            hosts.add(sd.lower())
        if ip_val:
            hosts.add(ip_val.lower())
            if ":" in ip_val:
                hosts.add(ip_val.split(":")[0].lower())
        for h in hosts:
            if h and h not in selected_by_host:
                selected_by_host[h] = a

    # 全量加载资产库，仅通过 id 精准更新
    assets = _load_json(ASSETS_FILE)
    id_to_idx = {a.get("id"): i for i, a in enumerate(assets) if a.get("id") is not None}
    updated = 0

    def _apply(asset, info):
        """将 httpx/ehole 信息写入资产，有变化才计数"""
        changed = False
        sc = info.get("statusCode") or info.get("status_code") or ""
        title = info.get("title") or ""
        fp = info.get("tech") or info.get("fingerprint") or ""
        if sc and str(asset.get("statusCode", "")) != str(sc):
            asset["statusCode"] = str(sc)
            changed = True
        if title and asset.get("title", "") != title:
            asset["title"] = title
            changed = True
        if fp and asset.get("fingerprint", "") != fp:
            asset["fingerprint"] = fp
            changed = True
        return changed

    # httpx 结果回写
    for url, info in url_status.items():
        h = _hostname(url)
        # hostname 匹配 + 端口变体
        candidates = [h]
        if h.endswith(":80"):
            candidates.append(h[:-3])
        if h.endswith(":443"):
            candidates.append(h[:-4])
        # 无端口时也尝试加端口匹配
        if ":" not in h:
            candidates.extend([h + ":80", h + ":443"])

        matched = False
        for c in candidates:
            if c in selected_by_host:
                asset = selected_by_host[c]
                aid = asset.get("id")
                if aid is not None and aid in id_to_idx:
                    if _apply(assets[id_to_idx[aid]], info):
                        updated += 1
                matched = True
                break

        if not matched:
            # 选中资产中未匹配 → 新建
            hostname = _hostname(url)
            new_id = max((a.get("id", 0) for a in assets), default=0) + 1
            assets.append({
                "id": new_id,
                "companyId": selected_assets[0].get("companyId", 1) if selected_assets else 1,
                "companyName": selected_assets[0].get("companyName", "默认公司") if selected_assets else "默认公司",
                "rootDomain": selected_assets[0].get("rootDomain", "") if selected_assets else "",
                "subDomain": hostname,
                "url": url, "ip": None,
                "statusCode": info.get("statusCode", ""),
                "title": info.get("title", ""),
                "fingerprint": info.get("tech", ""),
                "dnsStatus": "pending", "cdn": None,
                "timestamp": datetime.now().isoformat(),
            })
            updated += 1

    # ehole 指纹补充
    for url, fp_info in ehole_fingerprints.items():
        h = _hostname(url)
        candidates = [h]
        if h.endswith(":80"):
            candidates.append(h[:-3])
        if h.endswith(":443"):
            candidates.append(h[:-4])
        if ":" not in h:
            candidates.extend([h + ":80", h + ":443"])
        for c in candidates:
            if c in selected_by_host:
                asset = selected_by_host[c]
                aid = asset.get("id")
                if aid is not None and aid in id_to_idx:
                    info = {
                        "title": fp_info.get("title", ""),
                        "fingerprint": fp_info.get("fingerprint", ""),
                    }
                    if _apply(assets[id_to_idx[aid]], info):
                        updated += 1
                break

    _save_json(ASSETS_FILE, assets)
    _log(socketio, sid, f"存活探测完成: 更新 {updated} 条资产")

    return {"module": "survive_probe", "total": len(urls), "updated": updated, "http_results": list(url_status.values())[:500]}


def stop():
    _runner.stop()
