# 历史证据保留与迁移清单

## 目的与边界

该清单登记被Markdown相对链接引用、但不属于Git跟踪内容的运行证据。证据可能包含收费账本、冻结输入、部署身份、构建和验证日志；它们的保留用途不同，不能作为普通缓存批量清除。

2026-10-28扫描了112篇跟踪Markdown。隔离worktree中68条目标路径不存在，映射到原D盘工作区后均存在；去重为46个目标。目录链接只验证目录存在，不代表其全部内容已盘点。原工作区检查显示这些目标都被Git忽略；初始扫描没有复制或计算内容哈希。

随后对原D盘工作区中的46个目标做了只读复核：全部仍存在且被Git忽略。展开3个目录目标并按相对路径去重，共盘点54个文件、750,733字节（19个JSON、32个日志、1个文本和2个二进制文件）。逐文件SHA-256与字节数保存在隔离worktree的忽略文件`target/evidence-retention-source-20261028.json`；两个`.bin`文件只记录路径、大小和哈希，未读取内容。该清单用于后续迁移时校验源文件，不是归档副本、许可审查或恢复演练；原文件未修改。

## 保留分级

| 类别 | 内容 | 处置规则 |
|---|---|---|
| R1：运行时来源证据 | `data/runtime/`中的报告、账本和交付清单 | 保持原字节和路径身份；归档时附带SHA-256、字节数、来源scope/输入绑定。不可重建时不得用后续报告替换。 |
| R2：验证与交付记录 | `target/`中的测试、审计、清理和部署日志及manifest | 先核对报告引用和对应源码身份；可重建日志仍要保留被正式报告引用的历史版本。 |
| R3：目录级证据 | `process-diagnostics/`、`logs/`目录 | 逐文件列出内容、哈希和引用；本清单没有检查目录递归内容。 |
| R4：本机临时产物 | 不被任何跟踪文档或报告引用的临时缓存 | 先查消费者、身份和是否为唯一证据，再按清理流程删除；本清单没有授权删除。 |

## 已发现目标

路径相对于仓库根目录。`被引用文档`列出当前已知消费者；相同产物可能还有未扫描的代码、报告或本地消费者。

### `data/runtime/`：11个目标

| 目标 | 被引用文档 |
|---|---|
| `data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25/delivery/acceptance.json` | `docs/HISTORY_INDEX.md` |
| `data/runtime/p1-curry-ledger-handoff-recovery-offline-2026-10-26/recovery-report.json` | `TASKS_HISTORY.md` |
| `data/runtime/p1-curry-ledger-handoff-recovery-v2-offline-2026-10-26/recovery-report.json` | `TASKS_HISTORY.md` |
| `data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26/recovery-report.json` | `TASKS_HISTORY.md` |
| `data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26/final-build/delivery-final.json` | `TASKS_HISTORY.md`, `docs/HISTORY_INDEX.md`, `docs/TESTING_HISTORY.md` |
| `data/runtime/p1-curry-ledger-handoff-v3-offline-2026-10-25/audit-report.json` | `docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v3-handoff.md` |
| `data/runtime/p1-curry-ledger-handoff-v4-offline-2026-10-26/audit-report.json` | `TASKS_HISTORY.md`, `docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v4-handoff.md` |
| `data/runtime/p1-curry-ledger-handoff-v4-offline-2026-10-26/final-build/delivery-final.json` | `TASKS_HISTORY.md` |
| `data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26/process-diagnostics/` | `docs/EVIDENCE_CONTRACTS.md` |
| `data/runtime/p1-curry-option-revalidation-native-2026-10-26/final-build/delivery-final.json` | `docs/EVIDENCE_CONTRACTS.md`, `docs/HISTORY_INDEX.md`, `docs/TESTING_HISTORY.md` |
| `data/runtime/p1-ground-collapse-preparation-offline-2026-10-27/preparation.json` | `TASKS_HISTORY.md`, `docs/INDEX.md`, `docs/TESTING.md`, `docs/TESTING_HISTORY.md` |

### `target/`：35个目标

| 目标 | 被引用文档 |
|---|---|
| `target/a1-b1-implementation/planner-tests.log` | `docs/TESTING.md` |
| `target/a1-b1-implementation/python-schema-tests.log` | `docs/TESTING.md` |
| `target/a1-b1-implementation/workspace-test.log` | `docs/TESTING.md` |
| `target/a3-resumable/logs/` | `docs/TESTING.md` |
| `target/a3-resumable/logs/workspace-test.log` | `docs/TESTING.md` |
| `target/b2-workbench-tests/clippy.log` | `docs/TESTING.md` |
| `target/b2-workbench-tests/fmt.log` | `docs/TESTING.md` |
| `target/b2-workbench-tests/workspace-serial.log` | `docs/TESTING.md` |
| `target/c1-language-review-tests/browser-smoke-summary.json` | `docs/TESTING.md` |
| `target/c1-language-review-tests/http-smoke-summary.json` | `docs/TESTING.md` |
| `target/c1-language-review-tests/python-full.log` | `docs/TESTING.md` |
| `target/c1-language-review-tests/rust-clippy.log` | `docs/TESTING.md` |
| `target/c1-language-review-tests/rust-fmt-check.log` | `docs/TESTING.md` |
| `target/c1-language-review-tests/rust-workspace.log` | `docs/TESTING.md` |
| `target/c1-language-review-tests/status-loader-red.log` | `docs/TESTING.md` |
| `target/c1-language-review-tests/workbench-http.log` | `docs/TESTING.md` |
| `target/curry-ledger-handoff-v5-tests/audit-command.log` | `docs/EVIDENCE_CONTRACTS.md` |
| `target/ground-collapse-preparation-tests/adapter-examples-tests.log` | `TASKS_HISTORY.md`, `docs/TESTING.md`, `docs/TESTING_HISTORY.md` |
| `target/ground-collapse-preparation-tests/final-release/delivery.json` | `TASKS_HISTORY.md`, `docs/EVIDENCE_CONTRACTS.md`, `docs/superpowers/plans/2026-10-27-ground-collapse-preparation-handoff.md` |
| `target/ground-collapse-preparation-tests/pytest-full-after-cache-tightening.log` | `TASKS_HISTORY.md`, `docs/TESTING.md`, `docs/TESTING_HISTORY.md` |
| `target/ground-collapse-preparation-tests/python-test-files-review-final.txt` | `docs/TESTING.md`, `docs/TESTING_HISTORY.md` |
| `target/ground-collapse-preparation-tests/test-exclusion-inventory.json` | `docs/TESTING.md`, `docs/TESTING_HISTORY.md` |
| `target/ground-collapse-preparation-tests/workspace-tests-serial.log` | `TASKS_HISTORY.md`, `docs/TESTING.md`, `docs/TESTING_HISTORY.md` |
| `target/p4-r1b/logs/` | `docs/TESTING.md`, `docs/superpowers/plans/2026-10-28-p4-r1b-resumable-execution-loop-handoff.md` |
| `target/workspace-audit-2026-10-27-codex/ci-current-review-python312.log` | `docs/TESTING.md` |
| `target/workspace-audit-2026-10-27-codex/final-review-rust-examples.log` | `docs/TESTING.md` |
| `target/workspace-audit-2026-10-27-codex/final-review-rust-workspace.log` | `docs/TESTING.md` |
| `target/workspace-audit-current-2026-10-28/clippy-after-temp-cleanup.log` | `docs/TESTING.md` |
| `target/workspace-audit-current-2026-10-28/doc-link-check-current-20261028-verified-final.json` | `docs/TESTING.md` |
| `target/workspace-audit-current-2026-10-28/fmt-after-temp-cleanup.log` | `docs/TESTING.md` |
| `target/workspace-audit-current-2026-10-28/python-schema.log` | `docs/TESTING.md` |
| `target/workspace-audit-current-2026-10-28/temp-guard-tests.log` | `docs/TESTING.md` |
| `target/workspace-audit-current-2026-10-28/temp-test-cleanup-before.json` | `docs/TESTING.md` |
| `target/workspace-audit-current-2026-10-28/temp-test-cleanup-result.json` | `docs/TESTING.md` |
| `target/workspace-audit-current-2026-10-28/workspace-tests.log` | `docs/TESTING.md` |

## 后续迁移步骤

1. 对每个R1/R3目标生成逐文件清单：相对路径、大小、SHA-256、报告/账本身份、scope、输入来源及引用关系；保留目录结构和原始字节。
2. 对R2日志关联对应源码提交/归档、命令、平台、退出码及跳过项。不能只凭日志文件名将其归并为当前测试结果。
3. 将不可重建证据复制到独立、受版本管理之外且有备份策略的归档位置；复制后逐项重算哈希，确认源与副本一致，再更新访问索引。不得把私有卡库、个人配置、引擎二进制或未许可内容提交入Git。
4. 在归档副本验证之前，不改写历史文档链接或删除原文件。完成迁移后，链接指向稳定的证据索引；普通克隆应清楚标注无法访问的本机档案，而不是把缺失目标伪装成可重建结果。

## 排除项与未完成项

- 本清单不覆盖未被Markdown链接引用的账本、报告、资产和源码归档，也没有对原D盘工作区执行写入。
- 尚未确认逐文件哈希、许可/隐私审查、备份位置、保留期限和恢复演练；不能据此宣布历史证据已迁移或安全备份。
- 尚无证据支持删除旧协议路径、历史文档或本机产物。模块清理须另做代码消费者与兼容合同审计。
