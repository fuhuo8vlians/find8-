import csv
import glob
import os
import re
from datetime import datetime

from core.config import load_config, resolve_path
from core.tool_runner import ToolRunner

_runner = ToolRunner()


def _emit(socketio, sid, event, data):
    if socketio and sid:
        socketio.emit(event, data, to=sid)


def _log(socketio, sid, msg, level="info"):
    ts = datetime.now().strftime("%H:%M:%S")
    _emit(socketio, sid, "scan_log", {"time": ts, "msg": msg, "level": level})


def _write_targets(filepath, targets):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for t in targets:
            domain = t.strip()
            if "://" in domain:
                domain = domain.split("://")[-1].split("/")[0]
            f.write(domain + "\n")


def _parse_oneforall_results(work_dir, domain):
    """Parse OneForAll CSV results. Returns set of subdomains."""
    results_dir = os.path.join(work_dir, "results")
    subdomains = set()

    pattern = os.path.join(results_dir, "*.csv")
    for csv_file in glob.glob(pattern):
        try:
            with open(csv_file, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    continue
                # Priority: subdomain > domain > 子域名 > url (url may contain http://)
                sub_idx = None
                for priority_name in ("subdomain", "domain", "子域名", "url"):
                    for i, col in enumerate(header):
                        if col.strip().lower() == priority_name:
                            sub_idx = i
                            break
                    if sub_idx is not None:
                        break
                if sub_idx is None:
                    sub_idx = 0

                for row in reader:
                    if row and len(row) > sub_idx:
                        sub = row[sub_idx].strip().lower()
                        sub = sub.split("://")[-1].split("/")[0]  # strip proto & path
                        if sub and not sub.startswith("#"):
                            subdomains.add(sub)
        except Exception as e:
            pass
    return subdomains


def _parse_subfinder_results(work_dir):
    """Parse Subfinder out.txt. Returns set of subdomains."""
    subdomains = set()
    result_file = os.path.join(work_dir, "out.txt")
    if not os.path.exists(result_file):
        return subdomains

    with open(result_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            sub = line.strip().lower()
            if sub and not sub.startswith("#"):
                subdomains.add(sub)
    return subdomains


def _parse_tscan_results(work_dir):
    """Parse TscanClient domain results. Returns set of subdomains."""
    subdomains = set()

    # TscanClient saves domain results to domain_<target>.txt files
    domain_files = glob.glob(os.path.join(work_dir, "domain*.txt"))
    for df in domain_files:
        try:
            with open(df, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    sub = line.strip().lower()
                    if sub and not sub.startswith("#"):
                        # Strip protocol, path, port
                        sub = sub.split("://")[-1].split("/")[0].split(":")[0]
                        # Validate it looks like a domain
                        if "." in sub:
                            subdomains.add(sub)
        except Exception:
            pass

    # Fallback: parse from TscanClient.txt log
    if not subdomains:
        log_file = os.path.join(work_dir, "TscanClient.txt")
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    in_domain_section = False
                    for line in f:
                        line = line.strip()
                        if "域名枚举" in line or "domain" in line.lower():
                            in_domain_section = True
                            continue
                        if in_domain_section:
                            # Check for section boundary
                            if line.startswith("[") or line.startswith("=="):
                                break
                            sub = line.strip().lower()
                            sub = sub.split("://")[-1].split("/")[0].split(":")[0]
                            if "." in sub and len(sub) > 3:
                                subdomains.add(sub)
            except Exception:
                pass

    return subdomains


def run_subdomain_collection(targets, selected_tools, socketio, sid):
    """
    Args:
        targets: list of domain strings
        selected_tools: dict {"oneforall": bool, "subfinder": bool, "tscan": bool}
        socketio: Flask-SocketIO instance
        sid: client session ID
    Returns:
        dict with "all_subdomains", "sources", "result_file"
    """
    config = load_config()
    tools_config = config["tools"]

    all_subdomains = set()
    sources = {}  # subdomain -> source string

    _log(socketio, sid, f"目标域名: {', '.join(targets)}")
    _log(socketio, sid, f"选用工具: {[k for k, v in selected_tools.items() if v]}")

    # --- OneForAll ---
    if selected_tools.get("oneforall"):
        _log(socketio, sid, "--- 启动 OneForAll ---")
        of_work_dir = resolve_path(tools_config["oneforall"]["work_dir"])
        # 清理旧 CSV 结果，避免上次扫描残留混入
        of_results_dir = os.path.join(of_work_dir, "results")
        if os.path.isdir(of_results_dir):
            for old_csv in glob.glob(os.path.join(of_results_dir, "*.csv")):
                try:
                    os.remove(old_csv)
                except Exception:
                    pass
        of_url_file = os.path.join(of_work_dir, "url.txt")
        _write_targets(of_url_file, targets)
        _log(socketio, sid, f"已写入目标到: {of_url_file}")

        cmd = tools_config["oneforall"]["command"]
        _log(socketio, sid, f"执行: {cmd}")
        _log(socketio, sid, f"工作目录: {of_work_dir}")

        returncode, output = _runner.run(
            of_work_dir,
            cmd,
            on_output=lambda d: _emit(socketio, sid, "tool_output", d),
            timeout=1800,
        )

        _log(socketio, sid, f"OneForAll 完成 (返回码: {returncode})")
        of_results = _parse_oneforall_results(of_work_dir, targets[0])
        _log(socketio, sid, f"OneForAll 发现 {len(of_results)} 个子域名")

        for sub in of_results:
            sources[sub] = "OneForAll"
        all_subdomains.update(of_results)

    # --- Subfinder ---
    if selected_tools.get("subfinder"):
        _log(socketio, sid, "--- 启动 Subfinder ---")
        sf_work_dir = resolve_path(tools_config["subfinder"]["work_dir"])
        sf_url_file = os.path.join(sf_work_dir, "url.txt")
        _write_targets(sf_url_file, targets)
        _log(socketio, sid, f"已写入目标到: {sf_url_file}")

        cmd = tools_config["subfinder"]["command"]
        _log(socketio, sid, f"执行: {cmd}")
        _log(socketio, sid, f"工作目录: {sf_work_dir}")

        returncode, output = _runner.run(
            sf_work_dir,
            cmd,
            on_output=lambda d: _emit(socketio, sid, "tool_output", d),
            timeout=1800,
        )

        _log(socketio, sid, f"Subfinder 完成 (返回码: {returncode})")
        sf_results = _parse_subfinder_results(sf_work_dir)
        _log(socketio, sid, f"Subfinder 发现 {len(sf_results)} 个子域名")

        for sub in sf_results:
            if sub in sources:
                sources[sub] = "两者"
            else:
                sources[sub] = "Subfinder"
        all_subdomains.update(sf_results)

    # --- Tscan ---
    if selected_tools.get("tscan"):
        _log(socketio, sid, "--- 启动 Tscan 子域名枚举 ---")
        ts_work_dir = resolve_path(tools_config["tscan_domain"]["work_dir"])

        # 清理旧结果文件
        for old_df in glob.glob(os.path.join(ts_work_dir, "domain*.txt")):
            try:
                os.remove(old_df)
            except Exception:
                pass

        ts_url_file = os.path.join(ts_work_dir, "url.txt")
        _write_targets(ts_url_file, targets)
        _log(socketio, sid, f"已写入目标到: {ts_url_file}")

        cmd = tools_config["tscan_domain"]["command"]
        _log(socketio, sid, f"执行: {cmd}")
        _log(socketio, sid, f"工作目录: {ts_work_dir}")

        returncode, output = _runner.run(
            ts_work_dir,
            cmd,
            on_output=lambda d: _emit(socketio, sid, "tool_output", d),
            timeout=1800,
        )

        _log(socketio, sid, f"Tscan 完成 (返回码: {returncode})")
        ts_results = _parse_tscan_results(ts_work_dir)
        _log(socketio, sid, f"Tscan 发现 {len(ts_results)} 个子域名")

        for sub in ts_results:
            if sub in sources:
                # 追加来源
                existing = sources[sub]
                if "Tscan" not in existing:
                    sources[sub] = existing + "+Tscan"
            else:
                sources[sub] = "Tscan"
        all_subdomains.update(ts_results)

    # --- Dedup & Sort ---
    _log(socketio, sid, f"--- 去重合并 ---")
    _log(socketio, sid, f"合并去重后共 {len(all_subdomains)} 个唯一子域名")

    sorted_subdomains = sorted(all_subdomains)

    # --- Save Results ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"
    )
    os.makedirs(result_dir, exist_ok=True)

    safe_domain = targets[0].split("://")[-1].split("/")[0].replace(":", "_")
    result_file = os.path.join(result_dir, f"subdomains_{safe_domain}_{timestamp}.txt")

    with open(result_file, "w", encoding="utf-8") as f:
        for sub in sorted_subdomains:
            src = sources.get(sub, "未知")
            f.write(f"{sub}\t# {src}\n")

    _log(socketio, sid, f"结果已保存到: {result_file}")

    # Build result list for frontend
    result_list = [
        {"index": i + 1, "subdomain": sub, "source": sources.get(sub, "未知")}
        for i, sub in enumerate(sorted_subdomains)
    ]

    return {
        "total": len(sorted_subdomains),
        "subdomains": result_list,
        "result_file": result_file,
    }


def stop():
    _runner.stop()
