# 发布到 GitHub

本文档说明如何把当前项目发布到你自己的 GitHub 仓库。

## 0. 发布前检查

确认以下内容不要提交：

- `.signer/`
- `data/`
- `logs/`
- `*.session`
- `*.session_string`
- `.env`
- `.venv/`

这些路径已经在 `.gitignore` 中忽略。

## 1. 初始化本地 Git 仓库

如果当前目录还不是 git 仓库：

```bash
git init -b main
```

## 2. 配置 Git 身份

如果这台机器还没配过 Git 用户信息：

```bash
git config --global user.name "你的GitHub用户名或昵称"
git config --global user.email "你的GitHub邮箱"
```

如果你只想对当前仓库设置：

```bash
git config user.name "你的GitHub用户名或昵称"
git config user.email "你的GitHub邮箱"
```

## 3. 提交代码

```bash
git add .
git commit -m "Initial open source release"
```

## 4. 在 GitHub 网站创建新仓库

打开：

```text
https://github.com/new
```

建议：

- 仓库名：`tg-signer-webui` 或你喜欢的名字
- 可见性：`Public`
- 不要勾选自动生成 README、`.gitignore`、License

创建后，GitHub 会给你一段远程仓库地址，例如：

```bash
https://github.com/<your-name>/<your-repo>.git
```

## 5. 关联远程仓库并推送

```bash
git remote add origin https://github.com/<your-name>/<your-repo>.git
git push -u origin main
```

如果已经有 `origin`：

```bash
git remote set-url origin https://github.com/<your-name>/<your-repo>.git
git push -u origin main
```

## 6. 推荐仓库设置

推送完成后，建议在 GitHub 仓库页面补充：

- 项目描述
- Topics，例如 `telegram`, `automation`, `python`, `webui`
- 社交预览图
- Releases

## 7. 后续更新

以后每次更新发布：

```bash
git add .
git commit -m "your update message"
git push
```
