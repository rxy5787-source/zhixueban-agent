# Android 离机工程验收（不替代真机测试）

CI 文件：`.github/workflows/android-ci.yml`。本任务旨在你暂时无法使用电脑/手机时，先证明 Android 项目可以在干净的 GitHub Actions 环境构建，并通过纯 JVM 单元测试。

## 本阶段自动验收

- GitHub Actions 使用 JDK 21、Gradle Wrapper 9.3.1、Android SDK 36.1 和 Build Tools 36.0.0。
- 运行 `:app:assembleDebug :app:testDebugUnitTest`，验证编译、资源处理、打包及本地 JUnit（包括 BKT 算法等）。
- 验证 `app-debug.apk` 和 JUnit XML 报告实际存在；测试失败必须让 CI 失败。
- 成功时保存内部 Debug APK（保留7天），无论成功失败尽量保存单元测试报告（保留14天）。这是供后续本人安装验证的开发版，不是已发布或经过真机验收的安装包。

## 明确不在本阶段验收

- Android 真机安装、启动、页面点击、屏幕布局、摄像头/文件选择器、通知与系统权限。
- Android instrumented tests（`connectedAndroidTest` 等），它们需要真实设备或明确配置的模拟器。
- 手机与电脑网络互通、账号远程连接、Ollama/Qwen 实际生成题目。
- 设备兼容性、耗电、网络重连体验、生产安全配置、应用商店发版审核。

## 可复现本地命令

在仓库根目录、安装好 Android SDK 36.1 和 JDK 21 后：

```powershell
./gradlew.bat --no-daemon :app:assembleDebug :app:testDebugUnitTest
```

GitHub CI 可在PR下的 **Checks** 中查看，成功后可在Actions运行详情的 **Artifacts** 找到开发用Debug APK（到期会自动清理）。不能仅因发现APK文件就宣称安装和运行成功。

## 后续拿到电脑与手机后的真机验收清单

- 使用本人Android手机安装Debug APK，检查启动、登录退出、知识库与书架展示。
- 上传真实Word/PDF/TXT文件，确保界面状态、进度与失败重试一致。
- 使用真实本地Ollama/Qwen生成题目，并手工核对原文引用、答案正确性和题型。
- 完成答题，核对BKT记录、学习报告和多次答题结果。
- 测试断网、服务重启、APP重启、跨账号空间隔离及文件授权权限。
- 记录手机型号、Android版本、APK构建SHA、服务端SHA、实际模型和复现步骤。

这是离机CI与真机手工测试的边界说明，不是测试结果。
