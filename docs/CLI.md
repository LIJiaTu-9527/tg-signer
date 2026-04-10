# CLI 使用文档

本文档介绍 `tg-signer` 的命令行用法，适合希望直接通过终端完成登录、配置、运行和排查问题的用户。

## 全局参数

```bash
tg-signer [OPTIONS] COMMAND [ARGS]...
```

常用全局参数：

- `-a, --account`：账号名称，对应 `<account>.session`
- `--session_dir`：session 文件目录
- `-w, --workdir`：工作目录，默认 `.signer`
- `-p, --proxy`：Telegram 代理
- `--session-string`：Telegram session string
- `-l, --log-level`：日志等级
- `--log-dir`：日志目录
- `--log-file`：日志文件
- `--in-memory`：将 session 保存在内存中

示例：

```bash
tg-signer -a my_account --session_dir . --workdir .signer login
```

## 账号登录

```bash
tg-signer login
```

用途：

- 登录 Telegram 账号
- 生成 session 文件
- 缓存用户信息和最近聊天列表

退出登录：

```bash
tg-signer logout
```

## 签到配置与运行

### 创建或编辑配置

```bash
tg-signer run my_sign
```

如果配置不存在，会进入交互式配置流程。

### 持续运行签到

```bash
tg-signer run my_sign
```

### 只运行一次

```bash
tg-signer run-once my_sign
```

### 多个签到配置一起运行

```bash
tg-signer run task_a task_b
```

## 监控配置与运行

### 创建或编辑监控配置

```bash
tg-signer monitor run my_monitor
```

### 持续运行监控

```bash
tg-signer monitor run my_monitor
```

## 多账号运行

```bash
tg-signer multi-run -a account_a -a account_b same_task
```

用途：

- 用一套 signer 配置同时跑多个 Telegram 账号

## 即时消息相关命令

### 发送文本

```bash
tg-signer send-text me hello
tg-signer send-text @someuser hello
tg-signer send-text -- -1001234567890 hello
```

延时删除：

```bash
tg-signer send-text --delete-after 5 me hello
```

### 发送 Dice

```bash
tg-signer send-dice me
tg-signer send-dice -- -1001234567890
```

### 查询成员

```bash
tg-signer list-members --chat_id -1001234567890 --admin
```

## Telegram 定时消息

创建 Telegram 自带的定时消息：

```bash
tg-signer schedule-messages --crontab "0 9 * * *" --next-times 7 -- me good morning
```

查看已配置的定时消息：

```bash
tg-signer list-schedule-messages --chat_id me
```

## 配置导入导出

### 导出 signer 配置

```bash
tg-signer export my_sign > config.json
```

### 导入 signer 配置

```bash
tg-signer import my_sign < config.json
```

### monitor 配置同理

```bash
tg-signer monitor export my_monitor > monitor.json
tg-signer monitor import my_monitor < monitor.json
```

## LLM 配置

交互式配置 LLM：

```bash
tg-signer llm-config
```

说明：

- LLM 是可选的
- 只有图片识别、计算题回复等 AI 动作才依赖 LLM

## WebUI

```bash
tg-signer webgui -H 127.0.0.1 -P 8080
```

服务器部署推荐：

```bash
tg-signer webgui -H 0.0.0.0 -P 8080 --auth-code your-access-code
```

更多说明见 [WebUI 使用文档](./WEBUI.md)。

## 常见问题

### `PEER_ID_INVALID`

表示当前账号还没有“见过”这个会话。你可以：

- 先在 Telegram 客户端里打开这个聊天
- 用 `@username` 替代数字 ID
- 先发送到 `me` 验证账号发送是否正常

### 我应该把什么提交到仓库里

不要提交这些运行时数据：

- `.signer/`
- `*.session`
- `*.session_string`
- `data/`
- `logs/`
- `.env`
