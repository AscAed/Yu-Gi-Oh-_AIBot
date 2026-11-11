# 历史证据保留与迁移清单

## 目的与边界

该清单登记被Markdown相对链接引用、但不属于Git跟踪内容的运行证据。证据可能包含收费账本、冻结输入、部署身份、构建和验证日志；它们的保留用途不同，不能作为普通缓存批量清除。

## 当前处置（2026-11-02；更新2026-10-28决定）

在用户授权下，下方目录表格列出的54个唯一源文件中，51个非空文件共750,733字节已上传至Google Drive专用私有归档。上传后逐个回读并核对字节数和SHA-256，校验通过后删除对应本机源文件；3个零字节日志保留本机。2026-11-02再次列出归档目录并逐个回读当前云端对象：索引中的51个对象全部存在，字节数与SHA-256均匹配，合计750,733字节；云端目录及文件权限均为仅所有者可访问。5份重试产生的重复副本已删除。对回读内容作凭证/私钥模式检查未发现匹配项。一次Drive对象标题与索引显示名差异已在本机忽略索引中更正，文件ID、字节数和哈希未变。文件ID、源路径、哈希及校验结果只记录在被Git忽略的`data/runtime/cleanup-audit/drive-archive-index.json`。普通克隆无法访问该私有归档；表格路径表示归档时的源位置。

2026-11-11只读复核：Drive连接器再次列出51个目录子项，文件索引数量一致；目录权限元数据仅列所有者，子项未标记为共享。读取一份文本日志正文成功，证明当前连接可访问归档内容；本次没有下载或重算全部对象内容哈希。逐文件SHA-256完整性结论仍以2026-11-02全量回读记录和本机忽略索引为准。

2026-11-11前三批清理五个隔离Cargo构建缓存子树：`target/w1c-ffi-journal/debug`、`target/w1c-process-observation/debug`、`target/w1c-attempt-journal/debug`、`target/w1c-ffi-final/debug`和`target/h3-time-budget-recovery/debug`，不删除父目录日志或合成状态数据。共删除67,957个文件、43,479,517,473字节逻辑大小；63个mtime变化但SHA一致的`.rmeta`保留。逐文件SHA清单、操作日志和分批对账摘要位于忽略目录`data/runtime/cleanup-audit/`；五个子树合并统计见`target-isolated-debug-cache-20261111-final-reconciliation.json`，残余metadata及父目录测试日志SHA复核见`target-isolated-debug-cache-retained-rmeta-20261111-reconciliation.json`。引用到的workspace/Clippy日志哈希均复核匹配；幂等重试未额外删除。只删隔离Cargo debug编译缓存，不触及默认/发布构建目录、W1-C执行器候选、报告、账本或运行资产。

同日第四批逐项清理`target/h3-2b-2-cargo/debug`、`target/audit-20261109/rust/debug`和`target/audit-20261105/rust/debug`，删除37,916个文件、24,425,236,725字节逻辑大小；27个mtime变化但SHA与manifest匹配的`.rmeta`文件保留。其37,943项manifest、操作日志及reconciled summary均保留在忽略目录。四批共覆盖八个明确指定的debug子树，删除105,873个文件、67,904,754,198字节逻辑内容，保留90个哈希匹配但mtime变化的`.rmeta`；八树汇总见`target-isolated-debug-cache-20261111-all-batches-reconciliation.json`。没有删除父目录日志、测试状态、默认/发布构建目录、W1-C执行器候选、报告、账本或运行资产。操作日志中的失败尝试与后续成功清理均保留；只读回算确认本批删除37,916项、错误0、剩余27项哈希一致。

下方表格是归档前的路径与引用盘点，不表示每个列出的目标都在上述54个源文件中或已上传。归档范围仅由忽略索引中的51个对象确认；尤其是2026-11-03生成的三份当前Ground报告晚于该次归档，未包含在该归档操作中。

2026-11-03为Ground Collapse固定来源离线准备，从该私有归档恢复13份文件到原有忽略路径，合计141,493字节。每份恢复字节数和SHA-256均与索引中的上传源及回读值匹配；归档副本未修改。恢复项为Curry revalidation交付；Curry recovery v1、v2、v3报告及v3交付；Curry ledger handoff v3审计报告、v4审计报告及交付；consumption reservation v3 acceptance；V5 saved-input审计的JSON/stderr/stdout三件记录；以及V5测试`audit-command.log`。这些文件目前在本机原路径可用。Ground 2026-10-27历史`preparation.json`仍缺失；2026-11-03新准备报告单独保存在`data/runtime/p1-ground-collapse-preparation-current-2026-11-03-archive-recovered-2/`。

2026-11-03源码绑定复核产生两份不可变报告快照。前一版`driver-review-1/`报告SHA-256为`ab19a8467ccfd0242216818eaa1305670c6457979b5568319ffd340a1307cea2`，工具包ZIP和文件清单哈希分别为`40e236ad9ab020c88ee3ebecd58299102d3ddf9ec4e994327165afc2d0fceeb3`与`8a9d3573a1ac4377a686aab59a38dd35232099c03a66a34f9560f81e105c6710`；该快照使用将当前成员数写成schema常量的版本，现保留作历史审计。

当前报告保存在被Git忽略的`data/runtime/p1-ground-collapse-preparation-current-2026-11-03-driver-review-2/`：`preparation.json`为25,131字节、SHA-256 `a238a2f114c7cb26b6f1e79d6ca34b3e5f01f33bdb57eab0b6d2f650c2bb8c99`；`source-native-file-list.json`为2,392字节、SHA-256 `9e844de98ab205f2243c706aa6b368d2b68a81af65e9c70472d47f8f9689f746`；`source-native.zip`为95,895字节、SHA-256 `8fd8bb6ad057f6b83507b28a33adc6281c049974cac5d3e49db723df96515dbc`。工具包固定19个文件；schema保留正整数结构兼容，运行时仍按profile核对当前精确成员。报告六项来源检查和只读verify-only均通过，`execution_ready=false`。两份报告、此前归档恢复材料和缺失历史报告的记录均保留。

随后交付的Ground阶段驱动和合成测试属于跟踪源码及测试，不生成或替代`data/runtime/`中的原生研究证据。本批未创建scope、窗口、账本或原生收据；未来执行应在固定专用输出根写入，并保留其manifest、阶段输入/收据、调用账本和汇总报告。

2026-10-28扫描了112篇跟踪Markdown。隔离worktree中68条目标路径不存在，映射到原D盘工作区后均存在；去重为46个目标。目录链接只验证目录存在，不代表其全部内容已盘点。原工作区检查显示这些目标都被Git忽略；初始扫描没有复制或计算内容哈希。

随后对原D盘工作区中的46个目标做了只读复核：全部仍存在且被Git忽略。展开3个目录目标并按相对路径去重，共盘点54个文件、750,733字节（19个JSON、32个日志、1个文本和2个二进制文件）。逐文件SHA-256与字节数保存在隔离worktree的忽略文件`target/evidence-retention-source-20261028.json`；两个`.bin`文件只记录路径、大小和哈希，未读取内容。该清单用于后续迁移时校验源文件，不是归档副本、许可审查或恢复演练；原文件未修改。

## Ignored evidence links (checked 2026-11-03)

本次只读检查发现46个Markdown本机证据链接在当前checkout中没有目标：43个指向被忽略的`target/`日志或报告，另3个指向2026-10-27 Ground preparation报告。原链接文字中的路径已保留；为避免点入不存在的文件，链接现在指向本节。缺失项分布于`docs/EVIDENCE_CONTRACTS.md`、`docs/TESTING.md`、`docs/TESTING_HISTORY.md`、Ground交接计划和根目录`TASKS_HISTORY.md`。

缺失目标说明当前checkout中无法读取该路径；它不证明文件已删除、已上传或在其他工作区不存在。当前找到的Ground preparation报告仍使用独立2026-11-03路径，不能替代缺失的历史报告。任何恢复或归档结论都需要单独的字节数、SHA-256及来源链核验。此次没有移动、删除或恢复这些目标。

## 历史处置决定（2026-10-28；已由上方有限归档更新）

用户决定暂不迁移历史证据，只保留上述本机忽略目录中的哈希清单。此次不复制或移动源文件，不指定新的备份位置或保留期限，也不据哈希清单声称证据已有备份；源证据与清单均留在当前各自位置。若未来要迁移，需重新确认目标位置、备份策略和保留期限，并在复制后复算哈希。

## 保留分级

| 类别 | 内容 | 处置规则 |
|---|---|---|
| R1：运行时来源证据 | `data/runtime/`中的报告、账本和交付清单 | 保持原字节和路径身份；归档时附带SHA-256、字节数、来源scope/输入绑定。不可重建时不得用后续报告替换。 |
| R2：验证与交付记录 | `target/`中的测试、审计、清理和部署日志及manifest | 先核对报告引用和对应源码身份；可重建日志仍要保留被正式报告引用的历史版本。 |
| R3：目录级证据 | `process-diagnostics/`、`logs/`目录 | 逐文件列出内容、哈希和引用；本清单没有检查目录递归内容。 |
| R4：本机临时产物 | 不被任何跟踪文档或报告引用的临时缓存 | 先查消费者、身份和是否为唯一证据，再按清理流程删除；本清单没有授权删除。 |

## 已发现目标

路径相对于仓库根目录。`被引用文档`列出当前已知消费者；相同产物可能还有未扫描的代码、报告或本地消费者。

### `data/runtime/`：15个目标

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
| `data/runtime/p1-ground-collapse-preparation-current-2026-11-03-archive-recovered-2/preparation.json` | `TASKS.md`, `docs/TESTING.md` |
| `data/runtime/p1-ground-collapse-preparation-current-2026-11-03-driver-review-1/preparation.json` | `TASKS.md`, `docs/TESTING.md` |
| `data/runtime/p1-ground-collapse-preparation-current-2026-11-03-driver-review-2/preparation.json` | `TASKS.md`, `docs/TESTING.md` |
| `data/runtime/p4-r1b3/p4-r1b3-1793625696606077800-54284/read-only-journal-audit.json` | `TASKS.md` |

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

- 本清单对Markdown引用目标的原始盘点发生于2026-10-28；当时没有对原D盘工作区写入。2026-11-03另做的构建缓存清理仅删除本清单未列出的11个精确`target/**/debug`目录，清理前逐项确认其中没有证据类文件；没有修改本清单登记的证据。该操作的边界和结果记录于[本机环境审计](ENVIRONMENT_AUDIT.md)及忽略审计文件`data/runtime/cleanup-audit/target-build-cache-cleanup-20261103-220156.json`。
- 哈希清单已记录文件身份；尚未完成许可/隐私审查、备份和恢复演练。按用户决定当前不迁移，不代表历史证据已备份。
- 本次没有证据支持删除旧协议路径、历史文档、不可重建研究证据或剩余本机运行资产；仅已清理上文列出的可重建构建缓存。模块清理仍须依据代码消费者与兼容合同逐项审计。
