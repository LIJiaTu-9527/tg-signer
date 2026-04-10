# Docker 部署文档

本文档介绍如何在 Linux 服务器上使用 Docker 部署 TG Signer WebUI。

## 适用场景

适合以下情况：

- 想把 WebUI 部署到 VPS、云服务器或 NAS
- 不想手动装 Python 运行环境
- 希望把 session、配置和日志持久化

## 仓库内已提供的文件

- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `docker-entrypoint.sh`

这些文件已经按 WebUI 场景配置好。

## 目录说明

容器内使用这些路径：

- `/data/.signer`
- `/data/sessions`
- `/data/logs`

宿主机会把它们映射到项目目录下的：

- `./data/.signer`
- `./data/sessions`
- `./data/logs`

这意味着：

- 重建容器不会丢配置
- 不会丢 Telegram 登录状态
- 日志也会保存在宿主机

## 第一步：准备服务器

确保服务器已安装：

- Docker
- Docker Compose

然后把项目上传到服务器，例如：

```bash
git clone <your-repo-url> tg-signer
cd tg-signer
```

## 第二步：配置环境变量

复制示例文件：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
TZ=Asia/Shanghai
TG_SIGNER_PORT=8080
TG_PROXY=
TG_SIGNER_GUI_AUTHCODE=change-this-auth-code
TG_SIGNER_GUI_STORAGE_SECRET=change-this-storage-secret
```

字段说明：

- `TZ`：时区
- `TG_SIGNER_PORT`：宿主机映射端口
- `TG_PROXY`：Telegram 代理，可留空
- `TG_SIGNER_GUI_AUTHCODE`：WebUI 访问码，公网部署强烈建议设置
- `TG_SIGNER_GUI_STORAGE_SECRET`：NiceGUI 存储密钥，建议设置成固定随机串

## 第三步：启动

```bash
docker compose up -d --build
```

启动完成后访问：

```text
http://<你的服务器IP>:<TG_SIGNER_PORT>
```

例如：

```text
http://1.2.3.4:8080
```

## 第四步：首次登录

打开 WebUI 后：

1. 输入访问码
2. 进入 `登录` 页面
3. 用 Telegram 账号完成登录
4. 在 `配置` 中创建 signer / monitor 配置
5. 在 `运行配置` 中选择账号和配置并启动

## 常用运维命令

查看日志：

```bash
docker compose logs -f
```

重启：

```bash
docker compose restart
```

停止并删除容器：

```bash
docker compose down
```

重新构建：

```bash
docker compose up -d --build
```

## 反向代理建议

如果你打算公网开放，建议再加一层 Nginx / Caddy：

- 用域名访问
- 配 HTTPS
- 只暴露 80/443
- 后端转发到容器 `8080`

## 安全建议

- 一定设置 `TG_SIGNER_GUI_AUTHCODE`
- 建议不要直接裸奔暴露 8080 到公网
- 建议配合 Nginx / Caddy + HTTPS
- 不要把 `data/`、`.env`、`*.session` 提交到 GitHub

## 升级方式

项目更新后：

```bash
git pull
docker compose up -d --build
```
