# fnOS Native Packaging Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** 在 meng201457/magpie-fpk 构建和发布 amd64、arm64 原生安装包，飞牛桌面图标打开网页。
**Architecture:** 独立打包仓库固定上游提交；Python 构建脚本准备原生包、官方 fnpack 打包。Bash 生命周期管理 Web 服务，GitHub Actions 双架构构建后发布。
**Tech Stack:** Python 标准库、Bash、Go nogui、fnpack 1.2.3、GitHub Actions。
**Spec:** docs/superpowers/specs/2026-10-31-fnos-native-design.md（用户于 2026-10-31 确认执行）。

## Global Constraints

- 原生运行，无 Docker；分别生成 platform=x86 和 platform=arm。
- Web 3430、网关初始仅本地 3425，使用包用户。
- 密钥最少 16 位，不进入桌面 URL；配置和数据使用 TRIM 持久目录。
- 官方 fnpack 构建；两种架构全部成功后才发布 fpk-v* 标签 Release。

## Review Focus

- 无效密钥与 shell 特殊字符：拒绝并保持已有配置。
- 重复启动和过期 PID：不重复启动、不误杀无关进程。
- 上游自行更新：构建必须禁止替换包管理二进制。
- 版本与架构输入：拒绝无效版本、未知架构及标签不匹配。
- 第一次无 Cookie 访问：显示密钥登录页面，重启后原密钥继续有效。

### Task 1: 可复现构建与飞牛包模板

Files: upstream.lock.json, packaging/magpie/**, scripts/build.py, tests/test_build.py。
Interfaces: `python scripts/build.py --arch {amd64,arm64} --version X.Y.Z` 输出 dist/magpie-X.Y.Z-{x86,arm64}.fpk。

- [ ] 先写版本/架构拒绝、包结构准备与更新保护补丁的行为测试并确认缺少实现时失败。
- [ ] 固定上游提交和 fnpack SHA256；准备包模板、图标与许可；实现下载、校验、构建和打包。
- [ ] 运行 `python -m unittest discover -s tests -v`，预期全部通过。

### Task 2: 生命周期与首次访问

Files: packaging/magpie/cmd/*, packaging/magpie/wizard/install, tests/test_lifecycle.py。
Interfaces: 飞牛调用 cmd/main start|stop|status；install_callback 保存向导管理密钥。

- [ ] 写无效密钥、重复启动、停止、过期 PID、重启保持密钥的集成测试；先观察失败。
- [ ] 实现私有持久化配置和服务管理，以测试服务验证生命周期，CI 再验证真实 Magpie。
- [ ] Linux 上执行生命周期测试；本地 Windows 无 /proc 时明确跳过并由 Linux CI 补齐。

### Task 3: 工作流、文档与交付

Files: .github/workflows/build.yml, scripts/smoke.sh, README.md, .gitignore, .gitattributes, LICENSE。
Interfaces: push/PR/manual -> artifacts；fpk-v* -> 所有包成功后发布 Release。

- [ ] 配置 matrix、版本校验、只读构建权限和独立写权限发布任务。
- [ ] 文档说明首次密钥登录、LAN 使用、版本更新和设备验收限制。
- [ ] 运行静态检查与测试，再由独立审阅代理检查完整改动。
- [ ] 推送用户已授权的新仓库，检查实际 GitHub Actions；修复发现的问题，生成首版双架构包。

## Execution record

- 用户明确说“执行吧”，已授权实现并接入新建仓库，无需再次询问执行方式。
- 当前工作目录是空项目，无现有分支和待保留修改；就地初始化独立仓库。
- Ruling: 用户随后要求“不执行不必要的测试，跟着开发文档走”。按最新要求取消测试套件与测试文件，仅保留必要语法、编译、fnpack 和包校验；上文测试步骤被本项覆盖。
- Ruling: 官方 fnpack 1.2.3 Linux ARM 下载链接实际返回 404，因此两个目标均在 x86_64 runner 交叉编译并用已校验的官方 amd64 fnpack 打包。
- 构建、模板、生命周期、双架构工作流及 README 已实现；必要静态检查通过。等待仓库实际编译及发布。
