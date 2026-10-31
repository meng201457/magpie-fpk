# Magpie 飞牛原生应用与 GitHub 自动打包方案

状态：用户于 2026-10-31 确认执行，并指定仓库 `meng201457/magpie-fpk`。设备兼容性仍需实装验证。

## 需求与目标

用户希望将 https://github.com/yetone/magpie 打包成飞牛原生应用，并通过 GitHub 仓库自动构建。
安装后飞牛桌面显示 Magpie 图标，点击在浏览器打开 Web 管理界面。
应用在 NAS 后台直接运行 Magpie Linux 二进制，由飞牛应用中心管理启动、停止和升级。

首版交付独立打包仓库的文件、GitHub Actions、构建脚本、飞牛包目录、使用和验证说明。
本地工作目录目前为空，没有待保留的现有代码。

## 方案比较与选择

1. **原生二进制 + 上游 Web UI（采用）**：沿用 Magpie 的 `nogui` 构建，不依赖 GTK、桌面会话或 Docker。保留上游界面，维护成本较低，符合原生应用需求。
2. **Docker + 飞牛入口**：部署成熟，但依赖容器运行环境，不符合本次原生运行目标。
3. **移植桌面 GUI**：需要 NAS 桌面环境、GTK/WebKit，不适合浏览器访问。

用户已确认桌面图标跳转网页、独立仓库及双架构打包方案。

## 应用结构与桌面入口

- 应用 ID：`magpie`；显示名：`Magpie`。
- 按架构分别生成 `platform=x86`（amd64）、`platform=arm`（arm64）的 `.fpk`，不将二进制包声明为 `platform=all`。
- 根目录包含 `manifest`、64/256 像素图标、`config/privilege`、`config/resource`、`cmd/` 和 `wizard/`。
- `app/` 包含编译好的 Magpie、许可声明、`ui/config` 和入口图标。
- `desktop_uidir=ui`，入口 ID 为 `magpie.main`，`desktop_applaunchname` 指向同一 ID。
- 桌面入口采用 `type=url`、`protocol=http`、端口 `3430`、路径 `/`。
- 默认仅管理员可见：`allUsers=false`、`control.accessPerm=readonly`。
- 使用上游已有图标，保留 MIT LICENSE 及随发行文件要求的第三方许可声明。

## 服务与持久化

- 使用 `CGO_ENABLED=0`、`-tags nogui` 从固定上游源码提交构建；Web UI 已包含在此构建模式中。
- 以前台 Web 模式运行 Magpie，由飞牛生命周期脚本管理实际服务进程，不调用上游的 systemd 安装命令。
- Web 管理服务监听 `0.0.0.0:3430`；模型网关默认仅监听 `127.0.0.1:3425`。通过 Magpie 自带网关配置启用 LAN 分享和网关密钥，再供其他设备使用。
- `cmd/main` 实现幂等的 start/stop/status；记录 PID 并核对实际进程身份，避免误杀其他进程；status 未运行返回 3。
- 启动后等待有限时间验证服务就绪；失败通过 `TRIM_TEMP_LOGFILE` 显示可执行的错误说明。
- 使用 `run-as=package` 的专用应用用户，不请求 root 或宿主目录访问权限。
- 使用 `TRIM_PKGETC` 保存私有配置，`TRIM_PKGVAR` 保存运行数据和日志，`TRIM_PKGHOME` 保存 HOME；XDG 目录也指向应用持久化位置。
- 更新替换应用二进制，不主动删除配置、订阅凭据或使用数据。卸载默认不通过自定义脚本递归清理持久化数据；平台的保留行为列入设备验证。
- 禁止上游自动更新替换受飞牛包管理的二进制。实施时确认上游提供的更新开关；如果缺少受支持开关，应使用最小且可检查的构建补丁或包管理标记，并增加验证。

## 首次访问

- 安装向导设置 Web 管理密钥，至少 16 位，仅允许上游支持的字母、数字和 `-._~`。
- 密钥通过 `MAGPIE_WEB_KEY` 传入进程，并保存于仅应用用户可读的配置文件；不拼接 shell 命令、不输出到构建日志、不写入桌面入口 URL。
- 点击图标后出现上游登录页面，首次输入安装时设置的密钥，浏览器保留登录状态。
- 桌面入口的可见性不是 Web 服务鉴权；Web 页面仍由 Magpie 自身验证密钥。
- 首版采用端口直连，适用可直达 NAS 服务端口的网络。通过 FN Connect 或反向代理访问、复用飞牛登录态的统一网关集成不在首版范围内。
- 本需求不读取用户文件，不需要调用开放 API 或申请文件授权 scope。

## GitHub 自动构建与发布

- 仓库固定记录上游源码提交、上游版本、打包工具版本及校验值。手动更新这些记录后进入下一次构建，不静默跟随 main。
- push/PR：检查脚本及包结构，构建 amd64/arm64 安装包，上传 Actions artifacts，不发布 Release。
- `fpk-v*` 标签：执行相同检查与构建，两种架构均成功后上传 `.fpk`、SHA256 校验文件和构建来源记录到 GitHub Release。
- `workflow_dispatch`：手动触发构建，默认仅上传 artifacts。
- 区分上游 Magpie 版本与飞牛包版本；飞牛包版本由发布标签决定。
- 采用官方 `fnpack build`，不自行伪造 `.fpk` 归档格式。
- 当前官方工具版本为 `1.2.3`；Linux amd64 下载地址为 `https://static2.fnnas.com/fnpack/fnpack-1.2.3-linux-amd64`，实施时计算并记录 SHA256。
- 编译和 PR 检查仅需只读权限；发布任务单独授予 `contents:write`，默认 GITHUB_TOKEN 即可，不要求用户设置 PAT。
- 不自动发布到飞牛官方应用商店，不自动安装到 NAS，不将当前源码仓库地址冒充用户有写权限的发布仓库。

## 验证与验收

按用户后续要求，仅执行必要的 JSON/语法、架构、图标、真实编译和官方 fnpack 打包检查；不再运行额外单元测试或集成测试。
使用真实上游源码交叉编译两种 Linux 架构，并由官方 fnpack 生成安装包。
GitHub Actions 的实际成功与否以仓库运行结果为准，不将本地静态检查冒充线上构建。

设备验收：安装包可安装、桌面图标正确、点击能打开网页、首次登录成功、服务控制正常、重启后数据保留、同应用升级保留凭据和数据。
目标 fnOS 版本与架构需实际设备验证，构建成功不代表所有版本兼容；首版不声明未经测试的支持范围。

## 官方参考

- https://developer.fnnas.com/docs/guide/
- https://developer.fnnas.com/docs/core-concepts/framework/
- https://developer.fnnas.com/docs/core-concepts/manifest/
- https://developer.fnnas.com/docs/core-concepts/app-entry/
- https://developer.fnnas.com/docs/core-concepts/environment-variables/
- https://developer.fnnas.com/docs/core-concepts/privilege/
- https://developer.fnnas.com/docs/core-concepts/wizard/
- https://developer.fnnas.com/docs/cli/fnpack/
- https://developer.fnnas.com/api/overview/
- https://github.com/yetone/magpie/blob/main/Makefile
- https://github.com/yetone/magpie/blob/main/internal/gui/web.go
- https://github.com/yetone/magpie/blob/main/docs/reference.md
