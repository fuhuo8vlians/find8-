# find8威廉斯 v1.0

面向渗透测试与红队场景的**全流程主动信息收集平台**，整合子域名收集、端口扫描、目录爆破、存活探测、指纹识别五大模块，提供可视化 Web 管理界面。

---

## 功能模块

| 模块 | 工具 | 说明 |
|------|------|------|
| **子域名收集** | OneForAll / Subfinder / Tscan | 三工具联动，去重合并，标记来源 |
| **端口扫描** | Tscan + ehole + spray | 端口探测→指纹识别→存活路径，双字典模式 |
| **目录爆破** | Brute(spray) / dirsearch_bypass403 | 多字典选择 / 403绕过+JS提取+指纹 |
| **存活探测** | httpx + ehole | 状态码/标题/技术栈检测，精准回写资产库 |
| **资产管理** | Web面板 | 公司/项目管理、批量导入导出、DNS解析、CDN检测 |

---

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/fuhuo8vlians/find8-.git
cd find8-/0.综合主动信息收集工具

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动
start.bat          # 桌面模式(自动打开浏览器)
start_web.bat      # 纯Web服务模式(无浏览器)
```

访问 `http://localhost:5500`

---

## 目录结构

```
信息收集/
├── 0.综合主动信息收集工具/     ← 主程序 (Web后端+前端)
│   ├── app.py                 ← Flask + SocketIO 入口
│   ├── core/                  ← 配置/数据/代理/工具运行器
│   ├── modules/               ← 扫描模块
│   │   ├── subdomain.py       ← 子域名收集
│   │   ├── port_scan.py       ← 端口扫描
│   │   ├── dir_brute.py       ← 目录爆破
│   │   └── survive_probe.py   ← 存活探测
│   ├── web/                   ← 前端 (SPA)
│   ├── data/                  ← 资产数据库 (JSON)
│   └── results/               ← 扫描结果
├── 子域名收集/
│   ├── OneForAll-0.4.5/
│   └── subfinder/
├── 端口扫描/
│   └── tscan2.9.5/
├── 其他工具/
│   ├── ehloe_Des方案/
│   ├── spray/
│   └── httpx.exe
└── 目录爆破/
    ├── Brute/
    └── dirsearch_bypass403-0.2/
```

---

## 使用流程

```
1. 新建项目 → 关联公司 → 录入根域名
2. 子域名收集 → 选择工具 → 自动入库
3. 资产列表 → 勾选目标 → 端口扫描/目录爆破/存活探测
4. 查看结果 → 导出Excel
```

---

## 配置

编辑 `config.yaml` 可调整：

- **代理**: SOCKS5 代理地址
- **工具路径**: 各外部工具相对路径（默认无需修改）
- **端口策略**: Top100 / Top1000 / 全端口
- **扫描参数**: 线程数、超时、存活探测开关等

---

## 依赖

```
flask>=3.0
flask-socketio>=5.3
python-socks>=2.4
pyyaml>=6.0
pandas>=2.0
openpyxl>=3.1
dnspython>=2.4
```

---

## 免责声明

本工具仅限**合法授权**的安全测试和研究用途。使用者应遵守当地法律法规，在获得目标系统所有者明确授权后方可使用。作者不对任何未授权或非法使用行为负责。

---

## License

MIT
