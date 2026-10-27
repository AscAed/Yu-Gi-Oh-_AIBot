# 2026-10-27 环境自检与文档重整暂停交接

状态：用户因 Codex 额度不足要求暂停；整体目标未完成。恢复时先读 `docs/INDEX.md`、`TASKS.md`，重新检查工作区及活跃会话，不以此交接代替现行事实源。

## 已做及证据

- HEAD `8a6b2f6762131aebea6d8c0f5f61363d573f1b36`；工作区原有大量未提交及未跟踪内容，全部保留，未提交、推送或重建 `dist`。
- 两套现有配置各执行一次 doctor，均 ready/ABI/assets 成功；这是两次独立的本机 worker ABI 探针，不是决斗 smoke 或研究 scope 消费。现有普通发布包为 2026-10-19 构建，不等同当前源码。
- 原有 Ground 最终源码归档 603 项和 15 个交付引用核对通过；清理前另有 509 个非 Markdown 归档成员与工作区一致。之后六个非 Markdown 成员已更改，不能把旧归档身份用于当前工作区。保存的 Ground `--verify-only` 在后续文档拆分和 CI 修改前通过，零 native/runner/worker/FFI，原报告哈希未变。
- 逐项检查后移除 229 个空的受限临时目录，未更改 ACL；保留归档涉及的 61 个非空合成测试文件。清理后 Git 状态无访问警告；`.gitignore` 是 Ground 固定工具包成员，未改动。
- Rust fmt、offline/locked workspace 全目标 Clippy 通过；workspace 330 passed/36 ignored，adapter examples 52 passed/1 ignored。Python 缓存专项 8 passed；本次未重跑完整 Python 套件。日志和清理清单位于 `target/workspace-audit-2026-10-27-codex/`。
- 移除两个 crate 未使用的直接依赖，更新 Cargo.lock；pytest 缓存改到 `target/pytest-cache`，Windows 上先预建目录。
- `TASKS.md`、`docs/TESTING.md` 瘦身，原文完整保存在同目录 `TASKS_HISTORY.md`、`docs/TESTING_HISTORY.md`，原标题和历史锚点保留。独立审查核对标题顺序、历史跳转和快照哈希；详情见 `docs/TESTING.md` 和 `docs/HISTORY_INDEX.md`。部署脚本增加历史文件复制，但未实际重部署。
- CI 增加 pytest 测试依赖、顶层测试收集与 Rust examples；这是尚未经过干净 Python 3.12 CI 验证的修改。隔离安装依赖时长时间无输出，因暂停以 Ctrl-C 中止，不能把退出码 1 当作测试结果；详情 `target/workspace-audit-2026-10-27-codex/pip312.log`。未确认存在可用的 `python312-deps`。
- 本轮最新用户给出的五个引用聊天均已调用 `read_thread`，最近记录已读取；更早历史分页与信息提取尚待继续。聊天是历史上下文，当前状态须以仓库及实际部署核对。

## 接续顺序

1. 复核 Git 状态及现存运行进程，保留所有用户改动；确认当前依赖目录和 pip 日志，不假定中断的安装已成功。检查五个引用聊天的相关历史，提取需求和未决事项，与 `TASKS.md`、`docs/INDEX.md` 和当前实现核对。
2. 在隔离目标下准备 Python 3.12 环境，检查 CI 新收集方式的依赖及可复现性，执行完整的 Python 套件；网络命令必须在同一次 PowerShell 调用中注入 `http_proxy` 和 `https_proxy` 为 `http://127.0.0.1:7897`，以及 `all_proxy=socks5://127.0.0.1:7897`。不要将旧批次 734/9/200 作为本次新 CI 的结果。
3. 在安全的隔离目录验证部署脚本的历史文档复制和相对链接；正式重新部署及双资产验证仍未执行。核对其他组件和清理候选的消费者与保留用途，避免删除历史证据或兼容路径。
4. 源文件稳定后重新执行 Ground `--verify-only`（约 5–7 分钟，零原生研究调用），检查报告哈希未变；随后重跑 `target/workspace-audit-2026-10-27-codex/check-docs.py`、`git diff --check`，记录范围及结果。验证后更新文档状态；旧历史快照应保持原字节。
5. 继续整体自检和文档体系审查，厘清已实现、已验证、部署状态与未来目标，审视并补充人工决策/验收所需文档。未完成时保持目标未完成。

研究边界：Ground opcode 24 实际提示及响应尚未原生验证，已有 scope 已封存；新增原生研究实验需另定范围、预算和窗口，不因环境自检自动授权。


## 再次暂停检查点：2026-10-27

用户因5小时额度不足要求暂停；目标尚未完成。以下覆盖上方较早暂停后已变化的状态，恢复时仍先核对工作树、进程及现行事实源。

### 接续后已完成

- 基础安装此前缺少 `jsonschema` 导致研究入口 `--help` 失败；现已移到 `pyproject.toml` 基础依赖。独立Python 3.12无extras普通安装和editable安装、元数据、`pip check`、卡片样本及研究帮助均通过；模拟缺依赖的报告校验仍失败关闭。日志 `target/workspace-audit-2026-10-27-codex/base312-*.log`。
- `checked_output` 曾把Git跟踪检查的异常退出当作未跟踪，已改为两次检查仅接受0/1，其余失败关闭。Python 3.12聚焦11 passed/4 subtests；红绿日志在 `identity-git-exit-check/`，未新增原生研究调用。
- 发布脚本新增本机包文档入口；模板在构建和发布写入前校验改写。隔离成功路径和8个缺失/重复链接负例通过；部署不是事务，未重建旧dist。
- 限定目录、内容和reparse检查后移除本轮独立Cargo编译缓存，预估分配量约5.76 GiB；日志及历史证据保留。容量清点有85处访问错误、未去重硬链接，见 `capacity-inventory.json`；`.venv` 缺少pip及pytest。
- Ground保存报告在Git检查修复及依赖调整后再次只读verify通过，报告SHA-256始终为 `5354438945079d9df4f2867e272e2420d71605909c772f0a874b6c21b8319d74`，native/runner/worker/FFI均0；日志 `ground-verify-post-package.log`。后续测试文件已有更改，该结果验证保存报告及工具，不证明当前整个工作区等于旧归档。
- 阅读引用聊天并建立[工作区自检矩阵](WORKSPACE_REVIEW.md)，梳理部署、源码、测试、保留和产品能力之间的关系。

### 测试与待续

- Python 3.12短路径隔离快照全量结果 **717 passed、18 skipped、13 failed**，日志 `target/workspace-audit-2026-10-27-codex/ci-final-python312.log`，快照清单 `ci-final-snapshot-manifest.json` SHA-256 `bf6c7c73bc06b57bb84b794caedc12372efd2e78827c4d94a0ab3fc27b504614`；该结果不是当前修复后源码的全套结果。
- 13项失败已按根因进行聚焦修复和复验：两项本机历史清单与静态pins拆分、4项信息路线临时父目录创建、2项Curry测试基线处理、6项Tenki合成banlist/预检及历史证据条件（各组的测试数量见 `TESTING.md`）；后两组具体日志以 `ci-curry-tests-fixed.log`、`tenki-*.log` 为入口。注意数字分组重叠：两项清单检查中只有一项属于这13个失败，另一项在更早快照暴露。
- 独立复审发现Curry两处skip条件的权限异常边界；已改为仅捕获 `FileNotFoundError`，Python 3.12隔离6项检查通过（缺失、权限错误、其他OSError各覆盖两处），日志 `ci-curry-skip-boundary.log`。真实revalidation公共七阶段E2E在无历史baseline时跳过；其他合成测试不完全替代这一覆盖，不能称已在干净CI验收。
- **尚未对全部修复后的最新源码重新跑完整Python套件。** 先审查本轮测试修改（包括未跟踪文件）及各skip条件，建立短路径全新隔离快照并记录逐文件哈希；清除 `YGO_TOURNAMENT_ENGINE`、`YGO_LIVE_ENGINE`、`YGO_FIRST_TURN_REPORT`，完整运行CI顶层测试并保存skip/失败原因。不得改写旧日志、证据或复用封存的原生scope。历史账本正例需相应完整本机证据环境。
- 最后再次检查文档和链接、`git diff --check`，核对最新源码与快照差异、归档成员变化及静态/实际覆盖；按结果更新 `TASKS.md`、`TESTING.md` 和本交接。全部要求与证据核对完成前不得将目标标记为完成。

当前旧包、已有未提交/未跟踪工作以及历史数据均保留；没有提交、推送或部署。独立测试副本位于 `C:/ProjectIgnis/` 下 `codex-ci-*`、`codex-tenki-*` 等目录及审计target，删除前核对其日志和保留用途，不做宽泛递归清理。


## 恢复后自检收尾

上方暂停清单中的完整Python复验已执行：短路径隔离快照727 passed、24 skipped、0 failed。跳过项中14项历史材料及7项真实资产/报告检查已在本机单独完成；其中赛事开发配置固定案例与重放使用新的独立审计账本，两次实际worker请求，不复用研究账本。余下3项分别是两项Windows目录链接能力和一项会在旧历史目录写入文件的测试，未执行。普通2026-10-19部署包的预算受限smoke和单独replay通过，报告与具体调用记录见[TESTING](TESTING.md)。

工作区自检的覆盖矩阵见[WORKSPACE_REVIEW](WORKSPACE_REVIEW.md)，后续待办仍以[TASKS](../TASKS.md)为准。当前工作区与测试快照的最终差异及原归档身份分别核对，不把独立测试结果推广为全卡、全规则或最新源码正式双资产部署。
