# 贡献指南

欢迎为 TG Signer 提交 Issue 和 Pull Request。

## 提交前建议

- 先阅读 [README](./README.md)
- 先检查是否已有相同 Issue
- 提交前确认不要包含任何本地账号数据或 session 文件

## 本地开发环境

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[gui,speedup]"
```

Windows：

```cmd
py -3.11 -m venv .venv
.\.venv\Scripts\activate.bat
pip install -U pip
pip install -e ".[gui,speedup]"
```

开发依赖：

```bash
pip install -e ".[gui,speedup]"
pip install ruff tox pytest pytest-asyncio
```

## 代码风格

- 优先保持现有项目结构和命名风格
- 尽量写清晰、直接的实现
- 新增功能时同步更新文档

## 测试与检查

常用检查：

```bash
python -m compileall tg_signer
ruff check .
pytest
```

## Pull Request 建议

PR 描述最好包含：

- 变更目的
- 主要改动
- 是否影响 CLI / WebUI / Docker
- 是否需要迁移旧配置
- 是否补充了文档

## 不要提交这些文件

- `.signer/`
- `data/`
- `logs/`
- `*.session`
- `*.session_string`
- `.env`

这些通常包含本地账号、代理或运行数据。
