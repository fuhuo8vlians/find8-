import os
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

DEFAULT_CONFIG = {
    "tools": {
        "python": "python",
        "oneforall": {
            "work_dir": "../子域名收集/OneForAll-0.4.5",
            "command": "python oneforall.py --targets url.txt run",
            "result_pattern": "results/*.csv",
        },
        "subfinder": {
            "work_dir": "../子域名收集/subfinder",
            "command": "subfinder.exe -dL url.txt -o out.txt",
            "result_pattern": "out.txt",
        },
        "tscan_domain": {
            "work_dir": "../端口扫描/tscan2.9.5",
            "command": "TscanClient_windows_386_v2.9.5.exe -m domain -df url.txt -time 10 -t 600",
            "result_pattern": "TscanClient.txt",
        },
        "ts": {
            "work_dir": "../端口扫描/tscan2.9.5",
            "command": "TscanClient_windows_386_v2.9.5.exe -m port,url -hf ip.txt -np -t 600 -time 3",
        },
        "ehole": {
            "work_dir": "../其他工具/ehloe_Des方案",
            "command": "ehole finger -l url.txt -o res.xlsx",
        },
        "spray": {
            "work_dir": "../其他工具/spray",
            "command_large": "spray.exe -l url.txt -D -f res.json",
            "command_small": "spray.exe -l url.txt -d dirv2.txt -f res.json",
        },
        "brute": {
            "work_dir": "../目录爆破/Brute",
            "dict_small": "dirv2.txt",
            "dict_large": "(use -D flag)",
            "dict_backup": "bak.txt",
            "dict_deep": "dirv3.txt",
        },
        "dirsearch": {
            "work_dir": "../目录爆破/dirsearch_bypass403-0.2",
            "command": "python dirsearch.py",
        },
        "httpx": {
            "work_dir": "../其他工具",
            "command": "httpx.exe -l urls.txt -sc -title -tech-detect -json -o httpx_result.json",
        },
    },
    "proxy": {
        "enabled": False,
        "socks5": "socks5://127.0.0.1:1080",
        "pool": {"test_url": "http://httpbin.org/ip", "test_timeout": 10, "sources": []},
    },
    "server": {"host": "0.0.0.0", "port": 5500},
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    merged = DEFAULT_CONFIG.copy()
    _deep_merge(merged, config)
    return merged


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def resolve_path(relative_path):
    return os.path.normpath(os.path.join(BASE_DIR, relative_path))


def _deep_merge(base, override):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
