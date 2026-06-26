"""
端口扫描模块 — ts.exe(端口) → ehole.exe(指纹) → spray.exe(存活探测)
ehole 使用 ehloe_Des方案 路径下的 exe/finger.json/config.ini
spray 使用 spray 路径下的 exe/dirv2.txt，支持大字典(-D)和小字典(-d)两种模式
"""
import glob
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


def _write_targets(filepath, targets):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for t in targets:
            d = t.strip()
            if "://" in d:
                d = d.split("://")[-1].split("/")[0]
            f.write(d + "\n")


def _parse_port_txt(work_dir):
    results = []
    port_file = os.path.join(work_dir, "port.txt")
    if not os.path.exists(port_file):
        return results
    host_re = r'([^\s:,]+)'  # IP or hostname
    url_re = r'(https?://[^\s,]+)'
    with open(port_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if not line:
                continue
            m = re.match(r'^' + host_re + r':(\d+)\s+(\w+)$', line)
            if m:
                results.append({"ip": m.group(1), "port": m.group(2), "status": m.group(3)})
                continue
            m = re.match(r'^([A-Z/]+),\s*,\s*\[(.*?)\],\s*' + host_re + r':(\d+),\s*\[(.*?)\],?$', line)
            if m:
                fp = f"{m.group(2)} ({m.group(5)})" if m.group(5) else m.group(2)
                results.append({"ip": m.group(3), "port": m.group(4), "protocol": m.group(1), "fingerprint": fp, "status": "open"})
                continue
            # Fingerprint line with URL instead of host:port (e.g. TLS/HTTPS, , [Nginx], https://x.x.x.x:443, [None],)
            m = re.match(r'^([A-Z/]+),\s*,\s*\[(.*?)\],\s*' + url_re + r',\s*\[(.*?)\],?$', line)
            if m:
                p_url = m.group(3)
                try:
                    parsed = __import__("urllib").parse.urlparse(p_url)
                    host = parsed.hostname or ""
                    port = str(parsed.port) if parsed.port else ""
                except Exception:
                    host, port = "", ""
                if host and port:
                    fp = f"{m.group(2)} ({m.group(4)})" if m.group(4) and m.group(4) != "None" else m.group(2)
                    results.append({"ip": host, "port": port, "protocol": m.group(1), "fingerprint": fp, "status": "open"})
                continue
            m = re.match(r'^([A-Z/]+),\s*,\s*,\s*' + host_re + r':(\d+),\s*\[.*\],?$', line)
            if m:
                results.append({"ip": m.group(2), "port": m.group(3), "protocol": m.group(1), "status": "open"})
    return results


def _parse_url_txt(work_dir):
    results = []
    url_file = os.path.join(work_dir, "url.txt")
    if not os.path.exists(url_file):
        return results
    url_re = r'(https?://[^\s,]+)'  # exclude commas from URL to avoid capturing field separator
    with open(url_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if not line:
                continue
            m = re.match(r'^(\w+/\w+),\s*\[(\d+)\],\s*\[(.*?)\],\s*' + url_re + r',\s*\[(.*?)\],?$', line)
            if m:
                results.append({"protocol": m.group(1), "statusCode": m.group(2), "tech": m.group(3), "url": m.group(4), "title": m.group(5)})
                continue
            m = re.match(r'^(\w+/\w+),\s*\[(\d+)\],\s*\[(.*?)\],\s*' + url_re + r',?\s*$', line)
            if m:
                results.append({"protocol": m.group(1), "statusCode": m.group(2), "tech": m.group(3), "url": m.group(4), "title": ""})
                continue
            m = re.match(r'^' + url_re + r'$', line)
            if m:
                results.append({"url": m.group(1), "statusCode": "", "title": ""})
    return results


def _run_ehole(work_dir, ehole_cfg, socketio, sid):
    """运行 ehole 指纹识别(使用 ehloe_Des方案 路径下的 exe/finger.json/config.ini)，返回 {url: {title, tech}} 映射"""
    ehole_work_dir = resolve_path(ehole_cfg.get("work_dir", "../其他工具/ehloe_Des方案"))
    ehole_exe = os.path.join(ehole_work_dir, "ehole.exe")

    url_file = os.path.join(work_dir, "url.txt")
    if not os.path.exists(url_file):
        return {}
    if not os.path.exists(ehole_exe):
        _log(socketio, sid, f"ehole.exe 不存在({ehole_exe})，跳过指纹识别")
        return {}

    # 复制 finger.json 和 config.ini 到 tscan 工作目录(如果不存在)
    for fname in ["finger.json", "config.ini"]:
        src = os.path.join(ehole_work_dir, fname)
        dst = os.path.join(work_dir, fname)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass

    # 读取 URL 列表
    with open(url_file, "r", encoding="utf-8", errors="replace") as f:
        urls = [l.strip().rstrip(",") for l in f if l.strip()]

    if not urls:
        return {}

    _log(socketio, sid, "--- ehole 指纹识别 (ehloe_Des方案) ---")
    # 提取纯 URL 写入文件供 ehole 使用
    url_list_file = os.path.join(work_dir, "_ehole_urls.txt")
    url_pattern = re.compile(r'(https?://[^\s,]+)')
    with open(url_list_file, "w", encoding="utf-8") as f:
        for line in urls:
            m = url_pattern.search(line)
            if m:
                f.write(m.group(1) + "\n")

    out_xlsx = os.path.join(work_dir, "ehole_result.xlsx")
    # 使用 bat 中的命令格式: ehole finger -l url.txt -o res.xlsx
    cmd = f'"{ehole_exe}" finger -l "_ehole_urls.txt" -o "ehole_result.xlsx"'
    _log(socketio, sid, f"执行: ehole finger -l _ehole_urls.txt -o ehole_result.xlsx")

    returncode, output = _runner.run(
        work_dir, cmd,
        on_output=lambda d: _emit(socketio, sid, "tool_output", d),
        timeout=600,
    )
    _log(socketio, sid, f"ehole 完成 (返回码: {returncode})")

    # 尝试解析 ehole Excel 结果
    result = {}
    try:
        import pandas as pd
        if os.path.exists(out_xlsx):
            df = pd.read_excel(out_xlsx)
            for _, row in df.iterrows():
                url = str(row.iloc[0]) if len(row) > 0 else ""
                title = str(row.iloc[1]) if len(row) > 1 else ""
                tech = str(row.iloc[2]) if len(row) > 2 else ""
                if url and url != "nan":
                    result[url] = {"title": title if title != "nan" else "", "tech": tech if tech != "nan" else ""}
            _log(socketio, sid, f"ehole 识别 {len(result)} 条指纹")
    except Exception as e:
        _log(socketio, sid, f"ehole 结果解析: {len(result)} 条 (Excel解析: {e})")

    return result


def _run_spray(work_dir, spray_cfg, spray_dict, socketio, sid):
    """运行 spray 存活探测(使用 spray 路径下的 exe/dirv2.txt)，支持大字典-小字典模式，返回新增URL列表 [{url, statusCode, title}]"""
    spray_work_dir = resolve_path(spray_cfg.get("work_dir", "../其他工具/spray"))
    spray_exe = os.path.join(spray_work_dir, "spray.exe")

    url_file = os.path.join(work_dir, "url.txt")
    if not os.path.exists(url_file) or not os.path.exists(spray_exe):
        return []

    # 复制字典文件到 tscan 工作目录
    if spray_dict == "small":
        dict_src = os.path.join(spray_work_dir, "dirv2.txt")
        if not os.path.exists(dict_src):
            _log(socketio, sid, f"dirv2.txt 不存在({dict_src})，跳过存活探测")
            return []
        dict_dst = os.path.join(work_dir, "dirv2.txt")
        if not os.path.exists(dict_dst):
            try:
                shutil.copy2(dict_src, dict_dst)
            except Exception:
                pass

    # 复制 process_data.py 用于后处理
    process_py_src = os.path.join(spray_work_dir, "process_data.py")
    process_py_dst = os.path.join(work_dir, "process_data.py")
    if os.path.exists(process_py_src):
        try:
            shutil.copy2(process_py_src, process_py_dst)
        except Exception:
            pass

    dict_label = "小字典(dirv2.txt)" if spray_dict == "small" else "大字典(-D)"
    _log(socketio, sid, f"--- spray 存活探测 ({dict_label}) ---")

    # 清理旧结果
    for f in ["res.json", "res_processed.xlsx"]:
        fp = os.path.join(work_dir, f)
        if os.path.exists(fp):
            try: os.remove(fp)
            except: pass

    # 根据字典类型选择命令: -D 大字典 / -d dirv2.txt 小字典
    if spray_dict == "small":
        cmd_key = "command_small"
        fallback_cmd = f'"{spray_exe}" -l url.txt -d dirv2.txt -f res.json'
    else:
        cmd_key = "command_large"
        fallback_cmd = f'"{spray_exe}" -l url.txt -D -f res.json'

    cmd = spray_cfg.get(cmd_key, fallback_cmd)
    # 如果 cmd 中没有完整路径，用 spray_exe 替换 spray.exe
    if "spray.exe" in cmd and spray_exe not in cmd:
        cmd = cmd.replace("spray.exe", f'"{spray_exe}"')

    _log(socketio, sid, f"执行: {cmd}")

    returncode, output = _runner.run(
        work_dir, cmd,
        on_output=lambda d: _emit(socketio, sid, "tool_output", d),
        timeout=1200,
    )
    _log(socketio, sid, f"spray 完成 (返回码: {returncode})")

    # 解析 spray JSON 结果
    results = []
    res_json = os.path.join(work_dir, "res.json")
    if os.path.exists(res_json):
        try:
            with open(res_json, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        url = obj.get("url", "")
                        status_code = str(obj.get("status", ""))
                        title = obj.get("title", "")
                        if url:
                            results.append({"url": url, "statusCode": status_code, "title": title})
                    except json.JSONDecodeError:
                        pass
            _log(socketio, sid, f"spray 发现 {len(results)} 个存活路径")
        except Exception as e:
            _log(socketio, sid, f"spray 结果解析失败: {e}")

    # 运行 process_data.py 生成美化后的 Excel
    if os.path.exists(process_py_dst) and os.path.exists(res_json):
        try:
            proc_cmd = f'python "{process_py_dst}" "res.json" "res_processed.xlsx"'
            _log(socketio, sid, "运行 process_data.py 处理 spray 结果...")
            proc_rc, _ = _runner.run(
                work_dir, proc_cmd,
                on_output=lambda d: _emit(socketio, sid, "tool_output", d),
                timeout=120,
            )
            _log(socketio, sid, f"process_data.py 完成 (返回码: {proc_rc})")
        except Exception as e:
            _log(socketio, sid, f"process_data.py 执行失败: {e}")

    return results


def run(targets, config, socketio, sid):
    spray_dict = config.get("sprayDict", "small")
    tscan_opts = config.get("tscanOpts", {})
    return run_port_scan(targets, config.get("portStrategy", "top100"), spray_dict, tscan_opts, socketio, sid)


def run_port_scan(targets, strategy, spray_dict, tscan_opts, socketio, sid):
    config = load_config()
    ts_cfg = config["tools"].get("ts", {})
    ehole_cfg = config["tools"].get("ehole", {})
    spray_cfg = config["tools"].get("spray", {})
    work_dir = resolve_path(ts_cfg.get("work_dir", "../端口扫描/tscan2.9.5"))

    dict_label = "大字典" if spray_dict == "large" else "小字典"
    _log(socketio, sid, f"目标: {', '.join(targets[:10])}{'...' if len(targets) > 10 else ''}")
    _log(socketio, sid, f"端口策略: {strategy} | spray字典: {dict_label}")

    # 清理旧文件
    for fname in ["port.txt", "url.txt", "ip.txt", "res.json", "ehole_result.xlsx", "_ehole_urls.txt"]:
        fp = os.path.join(work_dir, fname)
        if os.path.exists(fp):
            try: os.remove(fp)
            except: pass

    # === Step 1: ts 端口扫描 ===
    ip_file = os.path.join(work_dir, "ip.txt")
    _write_targets(ip_file, targets)
    _log(socketio, sid, f"Step 1/3: ts 端口扫描 ({len(targets)} 个目标)")

    ts_exe = os.path.join(work_dir, "TscanClient_windows_386_v2.9.5.exe")

    # 组装 tscan 命令
    np = tscan_opts.get("np", True)
    nosmart = tscan_opts.get("nosmart", False)
    threads = tscan_opts.get("threads", 600)
    timeout = tscan_opts.get("timeout", 3)

    if strategy == "top100":
        port_args = ""
    elif strategy == "top1000":
        port_args = " -portf ports.txt"
    elif strategy == "all":
        port_args = " -p 1-65535"
    else:
        port_args = ""

    flags = f'-m port,url -hf ip.txt{port_args} -t {threads} -time {timeout}'
    if np:
        flags += " -np"
    if nosmart:
        flags += " -nosmart"

    cmd = f'"{ts_exe}" {flags}'
    _log(socketio, sid, f"执行: {cmd}")

    returncode, _ = _runner.run(work_dir, cmd,
                                on_output=lambda d: _emit(socketio, sid, "tool_output", d),
                                timeout=7200)

    port_results = _parse_port_txt(work_dir)
    http_results = _parse_url_txt(work_dir)
    _log(socketio, sid, f"ts 完成: {len(port_results)} 端口 | {len(http_results)} HTTP")

    # === Step 2: ehole 指纹识别 (使用 ehloe_Des方案 路径) ===
    ehole_fingerprints = _run_ehole(work_dir, ehole_cfg, socketio, sid)

    # 合并 ehole 结果到 http_results
    for h in http_results:
        url = h.get("url", "")
        if url in ehole_fingerprints:
            fp = ehole_fingerprints[url]
            if fp.get("title") and not h.get("title"):
                h["title"] = fp["title"]
            if fp.get("tech"):
                h["tech"] = fp["tech"]

    # === Step 3: spray 存活探测 (使用 spray 路径) ===
    spray_results = _run_spray(work_dir, spray_cfg, spray_dict, socketio, sid)

    _log(socketio, sid, f"全部完成: {len(port_results)} 端口 + {len(http_results)} HTTP + {len(spray_results)} 存活路径")

    return {
        "total_ports": len(port_results),
        "total_http": len(http_results),
        "total_spray": len(spray_results),
        "ports": port_results[:500],
        "http_results": http_results[:500],
        "spray_results": spray_results[:500],
    }


def stop():
    _runner.stop()