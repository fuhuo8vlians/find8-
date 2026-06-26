# find8威廉斯 v1.0 — 综合主动信息收集平台

面向渗透测试与红队场景的全流程信息收集工具，整合子域名收集、端口扫描、目录爆破、JS 分析四大模块，提供可视化 Web 界面，支持项目管理、资产管理和 SOCKS5 代理。

---

## 架构概览

```
┌──────────────────────────────────────────────────────┐
│             Web UI (白绿主题 SPA)                     │
│  仪表盘 │ 项目管理 │ 资产列表 │ 子域名 │ 端口 │ 目录 │ JS │
├──────────────────────────────────────────────────────┤
│           Flask + SocketIO API Server                 │
├──────────┬──────────┬──────────┬────────────────────┤
│ 子域名    │ 端口扫描  │ 目录爆破  │ JS分析              │
│ OneForAll│ ts.exe   │ 预留     │ 预留                │
│ Subfinder│ ehole    │          │                    │
│          │ spray    │          │                    │
├──────────┴──────────┴──────────┴────────────────────┤
│  核心层：项目管理 │ 资产管理 │ DNS解析 │ Excel导入导出  │
├──────────────────────────────────────────────────────┤
│  代理层：SOCKS5 代理 │ 代理验证 │ 代理池               │
├──────────────────────────────────────────────────────┤
│  数据层：JSON 文件存储 (data/assets.json)             │
└──────────────────────────────────────────────────────┘
```

---

## 目录结构

```
0.综合主动信息收集工具/
├── app.py                    # Flask 主入口，REST API + SocketIO 事件
├── config.yaml               # 工具路径/代理/服务器配置
├── requirements.txt          # Python 依赖
├── start.bat                 # 桌面模式启动（自动打开浏览器）
├── start_web.bat             # 纯 Web 服务模式（部署用）
│
├── core/                     # 核心模块
│   ├── config.py             # YAML 配置加载/保存/路径解析
│   ├── proxy.py              # SOCKS5 代理开关/验证/代理池
│   ├── tool_runner.py        # subprocess 实时输出流封装
│   └── data_manager.py       # 资产/公司/项目 CRUD + Excel + DNS + CDN检测
│
├── modules/                  # 扫描模块
│   ├── subdomain.py          # 子域名收集 (OneForAll + Subfinder)
│   ├── port_scan.py          # 端口扫描 (ts → ehole → spray)
│   ├── dir_brute.py          # 目录爆破 (预留)
│   └── js_analysis.py        # JS分析 (预留)
│
├── web/                      # 前端
│   ├── templates/index.html  # 单页应用 SPA
│   └── static/
│       ├── style.css         # 白绿清新主题
│       └── app.js            # 前端逻辑 + SocketIO
│
├── data/                     # 数据目录（自动创建）
│   ├── assets.json           # 资产数据
│   ├── companies.json        # 公司数据
│   └── projects.json         # 项目数据
│
└── results/                  # 扫描结果输出（按时间戳命名）
```

---

## 快速开始

### 环境要求

- Windows 10/11 或 Windows Server
- Python 3.8+
- 已安装的工具：OneForAll、Subfinder、ts.exe、ehole.exe、spray.exe

### 安装

```bash
cd 0.综合主动信息收集工具
pip install -r requirements.txt
```

### 启动

```bash
# 桌面模式（自动弹出浏览器）
start.bat

# 纯服务器模式（部署到 Windows Server）
start_web.bat
```

访问地址：`http://localhost:5500`

---

## 功能模块

### 1. 仪表盘

展示资产总数、项目数等统计概览，快速跳转到各功能模块。

### 2. 项目管理

- 创建/删除项目
- 项目关联公司
- 项目维度的资产隔离

### 3. 资产管理

#### 3.1 资产录入（三种方式）

| 方式 | 说明 |
|------|------|
| **单个录入** | 输入公司名称 + 根域名，手动添加 |
| **批量录入** | 文本框粘贴多行域名，自动提取根域名并分组 |
| **Excel 导入** | 上传 .xlsx/.xls 文件，自动解析域名列 |

#### 3.2 资产列表

- 多维筛选：项目、公司、根域名、子域名（通配符）、IP
- 单选/全选/反选，批量删除
- 导出 Excel
- DNS 解析查询（流式返回 A/CNAME 记录 + CDN 检测）
- 从资产列表直接发起扫描

### 4. 子域名收集（✅ 已实现）

**调用工具：**
- **OneForAll** — 综合子域名收集（API查询 + 证书透明 + DNS爆破 + 搜索引擎）
- **Subfinder** — 快速被动子域名发现

**工作流：**
1. 输入主域名 → 添加到目标列表
2. 勾选工具（可同时选两个）
3. 点击开始扫描 → 实时日志输出
4. 结果自动去重合并，标注每个子域名来源（OneForAll / Subfinder / 两者）
5. 结果保存到 `results/` 目录
6. 自动入库到资产管理系统

**调用方式：**
- OneForAll：写入 `url.txt` → 执行 `python oneforall.py --targets url.txt run` → 解析 `results/*.csv`
- Subfinder：写入 `url.txt` → 执行 `subfinder.exe -dL url.txt -o out.txt` → 解析 `out.txt`

### 5. 端口扫描（✅ 已实现）

**调用工具：**
- **ts.exe** — 端口扫描 + HTTP URL 提取
- **ehole.exe** — 指纹识别（标题/技术栈）
- **spray.exe** — HTTP 存活路径探测

**端口策略：**
| 策略 | 说明 |
|------|------|
| Top 100 | 常用 100 端口 |
| Top 1000 | 常用 1000 端口 |
| 全端口 | 1-65535 |

**工作流（三阶段串联）：**
1. `ts.exe` 端口扫描 → 生成 `port.txt` + `url.txt`
2. `ehole.exe` 指纹识别 → 识别 Web 标题和技术栈
3. `spray.exe` 存活探测 → 探测 HTTP 路径和状态码
4. 结果自动入库（URL/端口/状态码/标题）

### 6. 目录爆破（🚧 预留）

### 7. JS 分析（🚧 预留）

---

## SOCKS5 代理

### 配置

在设置面板（⚙ 按钮）中填写代理地址：

```
socks5://127.0.0.1:1080
```

点击「切换代理」开关，代理立即生效。

### 代理验证

设置面板内置代理连通性检测，测试代理是否可用及响应延迟。

### 实现方式

- Python 子进程：通过 `ALL_PROXY` / `HTTP_PROXY` / `HTTPS_PROXY` 环境变量注入
- 外部 exe 工具：由系统代理或 Proxifier 处理

---

## API 参考

### 公司 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/companies` | 获取公司列表 |
| POST | `/api/companies` | 新增公司 `{name}` |

### 项目 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects` | 获取项目列表 |
| POST | `/api/projects` | 新增项目 `{name, description}` |
| DELETE | `/api/projects/<id>` | 删除项目 |
| GET | `/api/projects/<id>/companies` | 项目关联公司 |
| POST | `/api/projects/<id>/companies` | 添加公司到项目 `{companyId}` |
| DELETE | `/api/projects/<id>/companies/<cid>` | 从项目移除公司 |

### 资产 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/assets` | 资产列表（支持 `?sort=&order=&company=`） |
| POST | `/api/assets` | 新增资产 `{companyName, rootDomain[], subDomain, url, projectId}` |
| POST | `/api/assets/batch` | 批量新增资产 |
| POST | `/api/assets/filter` | 多维筛选 `{projectIds, companyIds, rootDomains, subDomainPattern, ipPattern}` |
| DELETE | `/api/assets/<id>` | 删除资产 |
| POST | `/api/assets/batch-delete` | 批量删除 `{ids[]}` |
| PUT | `/api/assets/<id>/dns` | DNS 解析更新 |
| GET | `/api/assets/export` | 导出 Excel |
| GET | `/api/assets/unique-values?field=` | 获取筛选下拉值 |
| POST | `/api/dns-resolve` | 流式 DNS 解析 `{subdomain}` |

### Excel

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/excel/import` | 上传 Excel 导入资产（`multipart/form-data`, field: `file`） |

### 域名工具

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/domains/extract` | 从文本中提取域名 `{text}` |

### 代理验证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/proxy/validate` | 验证代理 `{url}` |

### WebSocket 事件

| 事件 | 方向 | 说明 |
|------|------|------|
| `connect` | C→S | 客户端连接 |
| `get_config` | C→S | 获取配置 |
| `save_config` | C→S | 保存配置 |
| `toggle_proxy` | C→S | 开关代理 `{enabled}` |
| `start_scan` | C→S | 开始扫描 `{module, targets[], tools{}, portStrategy?}` |
| `stop_scan` | C→S | 停止扫描 |
| `scan_log` | S→C | 实时日志推送 |
| `tool_output` | S→C | 工具 stdout/stderr 推送 |
| `scan_complete` | S→C | 扫描完成，附带结果数据 |
| `scan_error` | S→C | 扫描错误 |

---

## 配置说明

`config.yaml` 完整配置项：

```yaml
tools:
  python: python                              # Python 解释器
  oneforall:                                  # OneForAll 子域名工具
    work_dir: ../子域名收集/OneForAll-0.4.5
    command: python oneforall.py --targets url.txt run
    result_pattern: results/*.csv
  subfinder:                                  # Subfinder 子域名工具
    work_dir: ../子域名收集/subfinder
    command: subfinder.exe -dL url.txt -o out.txt
    result_pattern: out.txt
  ts:                                         # ts 端口扫描工具
    work_dir: ../端口扫描/ts
    command: ts.exe -m port,url -hf ip.txt -np -t 600 -time 3

proxy:                                        # SOCKS5 代理
  enabled: false                              # 是否启用
  socks5: socks5://127.0.0.1:1080            # 代理地址
  pool:                                       # 代理池
    sources: []                               # 代理列表文件路径
    test_timeout: 10                          # 验证超时(秒)
    test_url: http://httpbin.org/ip           # 验证目标

server:                                       # Web 服务
  host: 0.0.0.0                               # 监听地址
  port: 5500                                  # 监听端口
```

---

## 依赖

```
flask>=3.0                    # Web 框架
flask-socketio>=5.3           # WebSocket 实时通信
python-socks>=2.4             # SOCKS5 代理支持
pyyaml>=6.0                   # YAML 配置解析
pandas                        # Excel 处理
openpyxl                      # Excel 读写
dnspython                     # DNS 解析
```

---

## 文件路径约定

核心模块通过 `config.yaml` 中的相对路径定位工具目录：

```
0.综合主动信息收集工具/          ← BASE_DIR (app.py 所在)
├── core/
├── modules/
├── web/
├── data/
├── results/
├── ../子域名收集/               ← OneForAll / Subfinder 工作目录
├── ../端口扫描/ts/              ← ts / spray / ehole 工作目录
├── ../目录爆破/                 ← 预留
└── ../js/                       ← 预留
```

---

## License

内部使用工具，未开源。
