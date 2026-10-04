# cj-agent-platform

CJ Agent Platform —— 基于 Python 的 Agent 平台项目。

> 项目处于初始化阶段，以下内容会随开发进展更新。

## 环境要求

- Python 3.10 及以上

## 目录结构

```
cj-agent-platform/
├── src/                  # 业务源码
│   ├── __init__.py
│   └── main.py           # 程序入口
├── tests/                # 测试用例
│   └── test_main.py
├── docker/
│   ├── docker-compose.yml # MySQL、Redis、MinIO 编排配置
│   └── init/mysql/        # MySQL 首次启动初始化脚本
├── .env.example          # 环境变量模板
├── .editorconfig
├── .gitattributes
├── .gitignore
└── .ignore
```

## 快速开始

1. 创建并激活虚拟环境

   ```powershell
   # 创建并激活虚拟环境
   conda create -n cj python=3.10
   conda activate cj
   ```

2. 安装依赖

   ```powershell
   pip install -r requirements.txt
   ```

3. 配置环境变量：复制 `.env.example` 为 `.env`，按需填写（`.env` 不会被提交到仓库）

   ```powershell
   Copy-Item .env.example .env
   ```

4. 运行

   ```powershell
   python -m src.main
   ```

## 本地依赖服务

以下命令均在项目根目录执行。

后台启动 MySQL、Redis 和 MinIO：

```powershell
docker compose -f docker/docker-compose.yml up -d
```

停止并删除容器和网络，但保留本地数据：

```powershell
docker compose -f docker/docker-compose.yml down
```

- MySQL：`127.0.0.1:3307`
- Redis：`127.0.0.1:6379`
- MinIO S3 API：`http://127.0.0.1:9000`
- MinIO 管理控制台：`http://127.0.0.1:9001`

本地开发账号和密码见 `.env`；可复制 `.env.example` 作为初始配置。

## 测试

```powershell
pytest
```

## 开发约定

- 源码放在 `src/`，测试放在与 `src/` 平级的 `tests/`，测试文件名以 `test_` 开头。
- 统一使用 UTF-8 编码、LF 换行，缩进与格式见 `.editorconfig`。
- 敏感配置写入 `.env`，不要提交到仓库。
