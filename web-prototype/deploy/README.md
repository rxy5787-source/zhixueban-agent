# 知学伴在线试用部署

这个部署包包含 Web 源码、Python 出题服务和 Docker Compose 配置。云服务器负责网页、文件解析、千问推理与学习数据存储。手机通过同一个 HTTPS 地址访问。默认使用单机 CPU 模式，推理按任务顺序执行，实际出题时间取决于资料、服务器性能和排队情况。

## 准备环境

- 一台 Linux x86_64 云服务器，安装 Docker Engine 和 Docker Compose 插件，并可访问 Docker 镜像仓库、npm、PyPI 和 Ollama 模型仓库。可先以 4 vCPU、8 GB 内存和 30 GB 磁盘作为少量试用的估算起点，实际容量与耗时需要压测。
- 一个域名或子域名，DNS 指向该服务器。防火墙开放 TCP 80 和 443，由 Caddy 提供 HTTPS。应用和 Ollama 的端口留在容器网络中。
- 用非敏感资料试用。上传原件、题目和作答记录会保存在服务器数据卷内。运营者应安排访问权限、备份与数据清理周期。

## 启动

把部署包上传到服务器，解压后进入包含 `compose.yaml` 的目录。把下面第一行的 `trial.example.com` 换成自己的域名。

```sh
trial_host=trial.example.com
umask 077
printf 'TRIAL_HOST=%s\nTRIAL_SECRET=%s\n' "$trial_host" "$(openssl rand -hex 32)" > .env
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
docker compose logs --tail=80 models app caddy
```

首次启动会下载 `qwen3:1.7b` 和 `qwen3-vl:2b-instruct`。`models` 容器下载成功后退出，状态 `Exited (0)` 表示成功。`app` 健康后 Caddy 会启动。后续更新应保留原 `.env`，更换 `TRIAL_SECRET` 会使旧浏览器无法访问原试用空间。`docker compose stop` 可暂停服务并保留数据卷。`trial_data` 存放浏览器试用数据，`ollama_data` 存放模型，`caddy_data` 与 `caddy_config` 存放 Caddy 状态。备份学习数据时也需备份 `.env`。

## 用手机验收

1. 手机关闭 Wi-Fi，用移动网络打开配置的 HTTPS 域名。另一部手机或无痕窗口打开相同地址。
2. 用第一部手机上传短 TXT 或 Word 文档，生成一道单选题。切换到知识库，再从「出题任务」返回，确认后台进度继续更新。
3. 等题目通过初筛，确认它出现在目标知识库。完成练习，核对答案解析、练习记录与知识点分析。
4. 在第二个浏览器确认看不到第一个浏览器上传的资料、题目或历史。刷新第一个浏览器确认原记录仍在。
5. 关闭开发电脑，再通过手机用移动网络提交一次短资料，确认实际请求由云服务器处理。

## 试用范围

- 每个浏览器使用独立试用空间。会话由 HTTPS Cookie 保存，在成功打开首页时续期 30 天。清除 Cookie、换浏览器或过期会创建新空间，已有记录仍在服务器卷中，需由运营者处理。
- 默认上限为 32 个空间，同一来源地址每小时可新建 6 个。每个空间最多 8 次出题（包括重试），同一时间可提交 1 个生成任务，最多创建 50 个知识库。单文件上限 20 MB，单次请求含表单开销上限 25 MiB。名额占满或试用期结束后，由运营者处理数据。
- 等待中的任务重启后可以继续排队。正在执行的任务会标记为中断，可从原任务重试。已归档数据存放在持久卷中。
- 试用版按浏览器隔离，适合有限人数的试用。跨设备同步依赖正式账号系统。图片、扫描件和图表题继续受现有 OCR、视觉模型和初筛能力限制。

## 从开发目录重新打包

在项目根目录运行 `pwsh -File web-prototype/deploy/prepare.ps1`。默认读取与 `web-prototype` 同属当前项目的 `python-ai` 目录。可用 `-PythonProject` 指向其他副本，用 `-OutputZip` 指定新的 ZIP 路径。打包脚本按清单复制源码，并只在导出的 Python 副本上应用试用补丁。学习数据库、已上传资料、模型缓存和密钥都由服务器单独创建。

[Docker Compose 启动顺序](https://docs.docker.com/compose/how-tos/startup-order/) · [Ollama 容器说明](https://docs.ollama.com/docker) · [Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https)
