# Magpie for 飞牛 fnOS

将 [Magpie](https://github.com/yetone/magpie) 打包成飞牛原生应用。后台直接运行 Linux 二进制，无需 Docker；安装后飞牛桌面显示 **Magpie** 图标，点击在浏览器打开 Web 管理界面。

## 下载和安装

从本仓库 [Releases](https://github.com/meng201457/magpie-fpk/releases) 下载：

| 包名 | NAS 架构 |
| --- | --- |
| `magpie-<版本>-x86.fpk` | Intel / AMD x86_64 |
| `magpie-<版本>-arm64.fpk` | ARM64 / aarch64 |

1. 在飞牛应用中心选择手动安装，上传对应架构的 `.fpk`。
2. 安装向导设置 **Web 管理密钥**：16–128 位字母、数字或 `- . _ ~`，请妥善保存。
3. 启动应用，点击飞牛桌面的 Magpie 图标，或访问 `http://NAS地址:3430/`。
4. 首次打开输入安装时设置的管理密钥；随后在 Magpie 中添加模型提供商。

图标默认对管理员可见。Web 服务使用自己的管理密钥鉴权，飞牛登录状态不会替代它。入口不携带密钥。

Web 端口 `3430` 必须可由浏览器访问；首版采用端口直连，未适配 FN Connect 的系统域名转发。跨网络访问请自行配置 HTTPS 反向代理或 VPN。

## 给其他电脑使用网关

模型网关初始地址是 NAS 本机的 `127.0.0.1:3425`。在 Magpie 的网关设置中开启局域网分享、创建客户端网关密钥后，再让其他电脑连接 NAS。也可以使用上游支持的 Web 同端口 `/v1` 路由，访问权限仍由 Magpie 网关设置控制。

NAS 上的 Magpie 负责共享网关；不会自动修改其他电脑上的 Codex、Claude Code 配置。远程客户端需要自行填写相应的 base URL 与网关密钥。Web 管理密钥和客户端网关密钥用途不同。

## GitHub 自动打包

工作流位于 [`.github/workflows/build.yml`](.github/workflows/build.yml)。

- 推送 `main`、提交 PR 或在 Actions 手动运行：构建两种 `.fpk`，在运行页面下载 artifacts。
- 推送 `fpk-v<版本>` 标签：两种架构构建全部成功后，自动发布 GitHub Release。
- **每小时第 17 分钟**自动检查 `yetone/magpie` 的最新正式 Release；发现新版后固定其标签对应的提交，将安装包版本的补丁号加一（例如 `1.0.0` → `1.0.1`），构建 x86 / ARM64 安装包。两种架构全部成功并通过包校验后，提交 `upstream.lock.json`、创建 `fpk-v<版本>` 标签并发布 Release。
- 没有新版且对应 Release 的两种安装包、校验文件和构建来源文件均完整时跳过构建。构建失败不更新仓库版本；发布缺失或附件不完整时下次检查重试，已创建标签的版本从该标签固定的打包源码重建。草稿和预发布版本不跟进，也不会自动降级；同版本上游标签改指其他提交时停止并要求人工检查。
- 立即检查更新：在 `main` 分支运行 Actions 的 **Build fnOS packages**，勾选 **update_upstream**。不勾选时仍只构建当前固定版本。
- 默认 `GITHUB_TOKEN` 即可，不需要设置个人访问令牌。工作流仅在发布任务申请 `contents: write`；仓库规则需允许该任务向 `main` 提交版本锁文件和创建标签。

定时任务在工作流进入默认分支后生效，GitHub 调度可能延迟。外部仓库的 Release 不会直接触发本仓库，因此通过定时查询检测更新。自动提交标签后在同一次工作流继续发布，避免依赖 `GITHUB_TOKEN` 推送触发另一轮工作流。参阅 GitHub 官方说明：[定时事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)、[令牌触发限制](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow)。

首版包版本为 `1.0.0`。发布命令：

```bash
git tag fpk-v1.0.0
git push origin fpk-v1.0.0
```

自动更新会维护 `upstream.lock.json` 中的版本和提交。手动重打包时先递增 `package_version`，再推送同版本标签；手动更换上游源码时同时更新 `commit` 和 `version`。上游更新保护补丁的上下文不匹配时构建会停止，需检查新版本实现后再更新补丁。

两种包均由 Linux x86_64 runner 交叉编译，分别声明飞牛 `platform=x86` / `platform=arm`，使用官方 `fnpack 1.2.3` 打包。ARM 包包含 ARM64 二进制，并非 ARM32。官方工具下载按记录的 SHA256 校验。

## 本地打包

在 Linux x86_64 上准备 Python 3.11+、与上游 `go.mod` 匹配的 Go 工具链，以及 Bash、flock。构建命令：

```bash
python3 scripts/build.py --arch amd64 --version 1.0.0
python3 scripts/build.py --arch arm64 --version 1.0.0
```

输出位于 `dist/`，包含安装包、校验文件和构建来源 JSON。应用源码与工具放在 `build/`，无需手动下载。重新打包同版本时请使用新的工作目录，避免复用旧打包目录。

## 数据、服务与升级

- 飞牛应用中心负责启动、停止和运行状态；应用以专用包用户运行。
- `TRIM_PKGETC/web.key` 保存管理密钥，文件权限为 `600`。
- Magpie 配置位于 `TRIM_PKGETC/magpie/`；HOME 位于 `TRIM_PKGHOME`。
- 缓存、数据、状态、`magpie.log` 和 PID 记录位于 `TRIM_PKGVAR`。
- 升级保留应用配置和凭据；包内关闭了上游的二进制自更新，请通过新 `.fpk` 升级。
- 如忘记管理密钥，可在停止应用后，由 NAS 管理员将 `TRIM_PKGETC/web.key` 改为符合上述规则的新密钥并保持专用应用用户可读及 `600` 权限，然后重新启动。不要将密钥提交至仓库。
- 卸载后的数据保留由飞牛应用中心处理，本项目不会额外递归删除用户数据。

## 验证范围

自动化流程进行脚本语法检查、上游版本解析与发布完整性测试、真实 Go 编译、官方 fnpack 检查和发布前包校验。本地可运行 `python -m unittest discover -s tests -v` 检查更新解析逻辑。

构建成功代表两种安装包已生成，不等于已在所有飞牛版本和硬件上完成设备验证。安装后请确认图标跳转、密钥登录、启动停止和升级后数据保留。首次发布尚需飞牛设备实装确认。

## 来源与许可

当前固定的 Magpie 上游版本及提交见 [`upstream.lock.json`](upstream.lock.json)；每个发布包的 `.build-info.json` 也记录实际来源。上游采用 MIT 许可，原始 LICENSE 和 THIRD_PARTY_NOTICES 随包提供。本仓库打包代码也采用 MIT 许可。

实现依据飞牛官方文档：[应用框架](https://developer.fnnas.com/docs/core-concepts/framework/)、[应用入口](https://developer.fnnas.com/docs/core-concepts/app-entry/)、[应用权限](https://developer.fnnas.com/docs/core-concepts/privilege/)、[用户向导](https://developer.fnnas.com/docs/core-concepts/wizard/)、[fnpack](https://developer.fnnas.com/docs/cli/fnpack/)。仅注册入口和运行独立 Web 服务，无需申请开放 API 权限。
