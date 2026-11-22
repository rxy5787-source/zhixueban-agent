# 知学伴离线学习版

在项目的 `web-prototype` 目录运行以下命令。离线版构建到 `dist-offline`，部署时从站点根目录提供该目录的静态文件。

```powershell
npm run build:offline
npm run preview -- --outDir dist-offline --port 4180
```

打开终端给出的地址。正式浏览器需先通过 HTTPS 加载一次，等离线缓存完成后才能断网刷新。回环地址可用于本机调试。离线缓存只保存应用静态资源，原始资料和作答数据保存在当前站点的 IndexedDB 中。不同设备、浏览器、站点或浏览器配置文件各自保存数据。清除站点数据与浏览器存储回收可能移除本地内容，重要资料应下载留存。

从首页点击「开始学习」进入学习对话。离线时可以输入学习要求，点击「记在本轮」保留在当前对话中。页面会明确显示未提交 AI 任务。点击「添加资料」可将原文件保存到本机知识库，再从「练习已有题库」打开四道预置示例题。作答会立即显示判题、正确答案和解析，随后保存记录。保存遇到问题时可以重试。

知识库支持新建、改名、删除。导入支持 PDF、DOC、DOCX、TXT 原文件，每份不超过 20 MiB。导入后可下载和移除。删除知识库会一并移除该库导入的文件，作答记录独立保留。

资料内容解析、AI 出题和 BKT 掌握度由后端提供。本地版的 IndexedDB 数据没有自动写入 FastAPI 或 SQLite。跨设备账号同步尚未接入。

现有 Pages 展示版使用 `dist-pages`。已在 Pages 上使用离线版时，可向同一个离线版项目上传新 `dist-offline`，联网重新打开并刷新。保留该网址和浏览器站点数据，现有知识库和练习记录才能继续从原站点读取。可用「开始学习」是否打开对话页来确认版本更新。[Cloudflare Pages 上传说明](https://developers.cloudflare.com/pages/get-started/direct-upload/)

连接本机 FastAPI 和 Ollama 时，在仓库根目录运行 `.\tools\start-web-study-preview.ps1 -Port 8095` 并打开 `http://127.0.0.1:8095/#home`。这个构建走现有在线学习对话、生成任务、知识库和 BKT 接口。

## 给现有 Pages 加上在线入口

可选的在线入口需要一个实际运行的 HTTPS 知学伴服务。入口只查询服务与模型是否就绪。点击进入后，上传、生成、答题和 BKT 均在服务自己的网页和认证会话内完成。在 Pages 保存过的文件需在在线网页重新选择。两处学习数据分别保存在浏览器与后端。

有现成 `cloudflared` 时可用免费临时隧道测试。在第一窗口将一个空闲的专用端口转发给 FastAPI，例如 `cloudflared tunnel --url http://127.0.0.1:8096`。保留窗口，记下输出的 HTTPS 地址。第二个 PowerShell 窗口切换到仓库根目录，把下列示例域名换成实际域名。访问码只在服务窗口输入。

```powershell
$backendOrigin = 'https://你的临时域名.trycloudflare.com'
$pagesOrigin = 'https://你的项目.pages.dev'
$env:TRIAL_ACCESS_CODE = Read-Host '输入新的试用访问码（12–128字符）' -MaskInput
try {
    .\tools\start-web-study-preview.ps1 -Port 8096 -PublicOrigin $backendOrigin -LandingOrigin $pagesOrigin
} finally {
    Remove-Item Env:TRIAL_ACCESS_CODE -ErrorAction SilentlyContinue
}
```

第三个窗口在同一仓库根目录构建 Pages 文件。变量只存放公开 HTTPS 地址。

```powershell
$env:VITE_STUDY_ONLINE_ORIGIN = 'https://你的临时域名.trycloudflare.com'
try {
    npm.cmd --prefix web-prototype run build:offline
} finally {
    Remove-Item Env:VITE_STUDY_ONLINE_ORIGIN -ErrorAction SilentlyContinue
}
```

上传构建出的 `dist-offline` 到原 Pages 项目，保持原域名。手机联网刷新后点击「开始学习」。在线项出现连接就绪后点击「进入在线学习」，输入访问码，再进入学习对话。选一份非敏感 TXT，要求生成两道中等难度选择题，检查原文依据、答题反馈、解析及知识库记录。关掉测试用隧道后，回到 Pages 再点入口，应提示连接失败；本地资料与练习仍可打开。

临时隧道需要电脑和进程保持运行，重启后地址通常会变化，届时需重新配置和构建。在线浏览器会话跟随服务域名。重要的在线学习记录需要一个稳定域名和持久存储。[Quick Tunnels 官方说明](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
