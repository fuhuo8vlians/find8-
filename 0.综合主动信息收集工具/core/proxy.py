"""
代理管理模块 — SOCKS5 代理开关 + 代理验证 + 代理池支持
"""
import os
import socket
import urllib.request

_proxy_enabled = False
_proxy_url = ""


def enable_proxy(socks5_url: str):
    global _proxy_enabled, _proxy_url
    _proxy_enabled = True
    _proxy_url = socks5_url
    os.environ["ALL_PROXY"] = socks5_url
    os.environ["HTTP_PROXY"] = socks5_url
    os.environ["HTTPS_PROXY"] = socks5_url


def disable_proxy():
    global _proxy_enabled, _proxy_url
    _proxy_enabled = False
    _proxy_url = ""
    for key in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(key, None)


def get_proxy_status():
    return {"enabled": _proxy_enabled, "url": _proxy_url}


def validate_proxy(socks5_url: str, test_url: str = "http://httpbin.org/ip", timeout: int = 10) -> dict:
    """验证代理是否可用。返回 {valid: bool, response_time: ms, error: str}"""
    import time

    start = time.time()
    try:
        req = urllib.request.Request(test_url)
        req.add_header("User-Agent", "Mozilla/5.0")
        # 使用 socks5 代理
        if socks5_url.startswith("socks5://"):
            host_port = socks5_url.replace("socks5://", "")
            host, port = host_port.split(":")
            port = int(port)

            # 通过 socks 握手测试连通性
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.close()
            elapsed = int((time.time() - start) * 1000)
            return {"valid": True, "response_time": elapsed, "error": None}

        # HTTP/HTTPS 代理测试
        proxy_handler = urllib.request.ProxyHandler({"http": socks5_url, "https": socks5_url})
        opener = urllib.request.build_opener(proxy_handler)
        urllib.request.install_opener(opener)
        urllib.request.urlopen(req, timeout=timeout)
        elapsed = int((time.time() - start) * 1000)
        return {"valid": True, "response_time": elapsed, "error": None}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return {"valid": False, "response_time": elapsed, "error": str(e)}


def load_proxy_list(filepath: str) -> list:
    """从文件加载代理列表（每行一个 socks5://host:port）"""
    if not os.path.exists(filepath):
        return []
    proxies = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                proxies.append(line)
    return proxies
