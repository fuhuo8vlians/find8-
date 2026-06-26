"""
目录爆破模块 — Brute(spray多字典) / dirsearch_bypass403(403绕过+JS提取+指纹)
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


def _write_urls(filepath, urls):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for u in urls:
            u = u.strip()
            if u and not u.startswith("#"):
                if not u.startswith("http"):
                    u = "http://" + u
                f.write(u + "\n")


def _run_brute(targets, brute_cfg, dict_choice, socketio, sid):
    """Brute 模式: 使用 spray 进行目录爆破，支持4种字典"""
    work_dir = resolve_path(brute_cfg.get("work_dir", "../目录爆破/Brute"))
    spray_exe = os.path.join(work_dir, "spray.exe")

    if not os.path.exists(spray_exe):
        _log(socketio, sid, f"spray.exe 不存在({spray_exe})，跳过 Brute", "stderr")
        return []

    # 准备 URL 文件
    url_file = os.path.join(work_dir, "url.txt")
    _write_urls(url_file, targets)
    _log(socketio, sid, f"已写入 {len(targets)} 个URL到: {url_file}")

    # 验证 url.txt 写入成功
    if os.path.exists(url_file):
        with open(url_file, "r", encoding="utf-8") as f:
            url_content = f.read().strip()
        _log(socketio, sid, f"url.txt 内容预览: {url_content[:200]}")
    else:
        _log(socketio, sid, f"url.txt 写入失败！", "stderr")
        return []

    # 清理旧结果
    for fname in ["res.json", "res_processed.xlsx"]:
        fp = os.path.join(work_dir, fname)
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception:
                pass

    # 构造命令 — 直接用 spray.exe(不写全路径避免 Windows shell 中文编码问题)
    if dict_choice == "large":
        cmd = f'spray.exe -l url.txt -D -f res.json'
        label = "大字典(-D)"
    elif dict_choice == "backup":
        dict_file = brute_cfg.get("dict_backup", "bak.txt")
        cmd = f'spray.exe -l url.txt -d {dict_file} -f res.json'
        label = f"备份文件({dict_file})"
    elif dict_choice == "deep":
        dict_file = brute_cfg.get("dict_deep", "dirv3.txt")
        cmd = f'spray.exe -l url.txt -d {dict_file} -f res.json'
        label = f"深度字典({dict_file})"
    else:  # small (default)
        dict_file = brute_cfg.get("dict_small", "dirv2.txt")
        cmd = f'spray.exe -l url.txt -d {dict_file} -f res.json'
        label = f"小字典({dict_file})"

    # 验证字典文件存在
    if dict_choice != "large":
        dict_path = os.path.join(work_dir, dict_file)
        if not os.path.exists(dict_path):
            _log(socketio, sid, f"字典文件不存在: {dict_path}", "stderr")
            return []
        _log(socketio, sid, f"字典文件: {dict_path} ({os.path.getsize(dict_path)} bytes)")

    _log(socketio, sid, f"--- Brute 目录爆破 ({label}) ---")
    _log(socketio, sid, f"工作目录: {work_dir}")
    _log(socketio, sid, f"执行: {cmd}")

    returncode, output = _runner.run(
        work_dir, cmd,
        on_output=lambda d: _emit(socketio, sid, "tool_output", d),
        timeout=3600,
    )
    _log(socketio, sid, f"Brute spray 完成 (返回码: {returncode})")

    # 诊断: 输出 spray stderr/stdout
    if output:
        # 只打印最后20行避免刷屏
        stderr_lines = [l for l in output if l]
        if stderr_lines:
            for line in stderr_lines[-20:]:
                _log(socketio, sid, f"[spray] {line[:200]}")

    # 解析结果
    results = []
    res_json = os.path.join(work_dir, "res.json")
    if not os.path.exists(res_json):
        _log(socketio, sid, f"res.json 未生成，spray 可能未正常运行", "stderr")
        return results

    res_size = os.path.getsize(res_json)
    _log(socketio, sid, f"res.json 大小: {res_size} bytes")
    if res_size == 0:
        _log(socketio, sid, f"res.json 为空，目标未返回可访问路径")
        return results

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
        _log(socketio, sid, f"Brute 解析出 {len(results)} 个路径")
    except Exception as e:
        _log(socketio, sid, f"Brute 结果解析失败: {e}", "stderr")

    # 运行 process_data.py 后处理
    process_py = os.path.join(work_dir, "process_data.py")
    if os.path.exists(process_py) and os.path.exists(res_json) and res_size > 0:
        try:
            proc_cmd = f'python process_data.py res.json res_processed.xlsx'
            _log(socketio, sid, "运行 process_data.py 处理结果...")
            _runner.run(work_dir, proc_cmd,
                        on_output=lambda d: _emit(socketio, sid, "tool_output", d),
                        timeout=120)
        except Exception:
            pass

    return results


def _run_dirsearch(targets, ds_cfg, ds_opts, socketio, sid):
    """dirsearch 模式: 使用 dirsearch_bypass403 进行目录扫描"""
    work_dir = resolve_path(ds_cfg.get("work_dir", "../目录爆破/dirsearch_bypass403-0.2"))
    dirsearch_py = os.path.join(work_dir, "dirsearch.py")

    if not os.path.exists(dirsearch_py):
        _log(socketio, sid, f"dirsearch.py 不存在({dirsearch_py})，跳过 dirsearch")
        return []

    bypass = ds_opts.get("bypass403", False)
    jsfind = ds_opts.get("jsfind", False)
    fingerprint = ds_opts.get("fingerprint", False)
    threads = ds_opts.get("threads", 25)
    recursive = ds_opts.get("recursive", False)

    flags = f"-t {threads}"
    if bypass:
        flags += " -b yes"
    if jsfind:
        flags += " -j yes"
    if fingerprint:
        flags += " -z yes"
    if recursive:
        flags += " -r"

    opts_desc = []
    if bypass: opts_desc.append("403绕过")
    if jsfind: opts_desc.append("JS提取")
    if fingerprint: opts_desc.append("指纹识别")
    if recursive: opts_desc.append("递归扫描")
    _log(socketio, sid, f"--- dirsearch 目录扫描 (线程:{threads}" + (f" | {','.join(opts_desc)}" if opts_desc else "") + ") ---")

    all_results = []

    # 清理403缓存
    for fname in ["403list.txt", "jsfind403list.txt"]:
        fp = os.path.join(work_dir, fname)
        try:
            open(fp, "w").close()
        except Exception:
            pass

    # 逐个 URL 扫描
    for i, target in enumerate(targets):
        url = target.strip()
        if not url.startswith("http"):
            url = "http://" + url

        _log(socketio, sid, f"扫描 [{i+1}/{len(targets)}]: {url}")
        # 用相对路径避免 Windows shell 中文编码问题
        cmd = f'python dirsearch.py -u "{url}" {flags}'
        _log(socketio, sid, f"执行: {cmd}")

        returncode, output = _runner.run(
            work_dir, cmd,
            on_output=lambda d: _emit(socketio, sid, "tool_output", d),
            timeout=3600,
        )
        _log(socketio, sid, f"dirsearch [{i+1}/{len(targets)}] 完成 (返回码: {returncode})")

        # 解析 reports 目录中最新的报告
        report_dir = os.path.join(work_dir, "reports")
        if os.path.isdir(report_dir):
            report_files = sorted(
                glob.glob(os.path.join(report_dir, "*.json")),
                key=os.path.getmtime, reverse=True,
            )
            if report_files:
                try:
                    with open(report_files[0], "r", encoding="utf-8") as f:
                        report = json.load(f)
                    for r in report.get("results", []):
                        all_results.append({
                            "url": r.get("url", ""),
                            "statusCode": str(r.get("status", "")),
                            "title": "",
                            "contentLength": r.get("content-length", ""),
                        })
                    _log(socketio, sid, f"  解析到 {len(report.get('results', []))} 条结果")
                except Exception as e:
                    _log(socketio, sid, f"  报告解析失败: {e}")

    _log(socketio, sid, f"dirsearch 总计发现 {len(all_results)} 个路径")
    return all_results


def run(targets, config, socketio, sid):
    """目录爆破入口"""
    cfg = load_config()
    tool = config.get("dirTool", "brute")
    brute_cfg = cfg["tools"].get("brute", {})
    ds_cfg = cfg["tools"].get("dirsearch", {})

    _log(socketio, sid, f"目录爆破目标: {', '.join(targets[:10])}{'...' if len(targets) > 10 else ''}")
    _log(socketio, sid, f"选用工具: {'Brute(spray)' if tool == 'brute' else 'dirsearch_bypass403'}")

    if tool == "brute":
        dict_choice = config.get("bruteDict", "small")
        results = _run_brute(targets, brute_cfg, dict_choice, socketio, sid)
    elif tool == "dirsearch":
        ds_opts = config.get("dirsearchOpts", {})
        results = _run_dirsearch(targets, ds_cfg, ds_opts, socketio, sid)
    else:
        results = []

    _log(socketio, sid, f"全部完成: 共发现 {len(results)} 个路径")

    return {
        "total": len(results),
        "results": results[:1000],
    }


def stop():
    _runner.stop()
