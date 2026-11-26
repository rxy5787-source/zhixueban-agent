# Cloudflare Pages 静态演示版

## 构建

在 PowerShell 7 中运行。使用 Node.js 24 LTS 或符合项目要求的 Node.js 22.12 及以上版本。

```powershell
Set-Location 'D:\adaptivequizapp\artifacts\zhixueban-development\web-prototype'
npm ci
npm run build:demo
```

演示版输出到 `dist-pages`，入口是该目录下的 `index.html`。常规 `npm run build` 仍输出需要后端的 `dist`。

## 上传并获取 HTTPS 地址

1. 登录 Cloudflare，进入 **Workers & Pages**，选择 **Create application**，切换到 **Pages**，选用 **Direct Upload** 或 **Drag and drop your files**。
2. 为项目命名，例如 `zhixueban-demo`。将 `dist-pages` 文件夹拖到上传区，确认发布内容的根目录中直接包含 `index.html` 和 `assets`。上传范围只需要这一份构建产物。
3. 点击 **Deploy site**。发布完成后，在项目页复制生产环境的 `https://<项目名>.pages.dev` 地址。账号中显示的实际地址可能因项目名占用而不同。
4. 用电脑无痕窗口和关闭 Wi-Fi 的手机分别打开同一个地址。切换「首页」「知识库」「我的」，进入示例主题后刷新。点击「开始学习」应看到「在线服务尚未开放」，浏览器网络面板中应无 `/api/` 请求。

Direct Upload 项目之后可以继续手动发布新版构建产物。需要 Git 自动部署时，可以创建采用 Git 集成的 Pages 项目。[Cloudflare Pages Direct Upload 官方说明](https://developers.cloudflare.com/pages/get-started/direct-upload/)

## 演示范围

页面、示例书架和个人偏好可浏览。昵称和偏好只保存在当前浏览器。实际知识库管理、资料上传、AI 出题、答题记录和 BKT 学习分析依赖学习后端。演示包不需要设置云端环境变量，也不需要提供本地数据库或凭证。
