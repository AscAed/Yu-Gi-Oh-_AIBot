# 首批基线审计：暂停断点与接续说明

## 暂停边界

2026-10-19用户因Codex额度明确要求在合适位置暂停并准备接续。本记录是暂停时点的交接快照，不是第二份实时任务表；当前状态仍以[TASKS](../../../TASKS.md)和[TESTING](../../TESTING.md)顶部为准。没有后台原生实验或子agent继续运行。不要自行唤醒或推进，等待用户明确恢复。

原批准范围为[首批计划](2026-10-19-baseline-audit.md)的A–E，后续P1–P8只保留门禁导航。当前代码基线HEAD为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，分支`codex/combo-mvp`；本轮修改及新增文件均未提交，不可reset/clean或只按HEAD重建。所有外网终端命令仍须同次注入7897代理。

## 已保存实现与测试

- Rust `engine identity --config ... [--output ...]`：双采样实际资产、脚本清单差异、逻辑角色哈希；Windows规范路径可读，逐祖先拒绝链接/reparse。输出独占创建，不能覆盖已有文件、创建缺失资产或写入脚本树；Windows大小写变体也在回归内。
- Python `ygo_data.identity capture/build-record`：工作区/双配置/产物身份、观察构建记录，输出仅忽略目录且不覆写；既有构建来源未验证，不能声称可复现。
- Python `ygo_data.coverage`、`language`：只读清点、39卡发行依据转换、固定版本中文来源及字段核验；source_verified/complete/语言qualified保持false。
- Python `ygo_eval.research`和Rust独立oracle/ResearchBatch/example：10类canonical响应、案例结构与实际CDB/禁限/资源校验、同一持久总账本、原始证据恢复、独占输出。proof_ready/完整动作/最优性保持false。
- 新增8个独立schema。用法与具体边界见[BASELINE_AUDIT](../../BASELINE_AUDIT.md)、[RESEARCH_AUDIT](../../RESEARCH_AUDIT.md)、[DATA_SOURCES](../../DATA_SOURCES.md)。

最后一轮`cargo fmt --all -- --check`和Clippy通过；`cargo test --workspace --offline --locked`为**237 passed、0 failed、36 ignored**；Python全套61项，**54 passed、7 skipped**，其后没有Python行为修改。最终日志分别为忽略目录下的`clippy-delivery.log`、`rust-delivery.log`、`python-full-final.log`。另有example安全测试1项已通过；恢复后最终构建前可单独重跑。

独立审查发现并已修复：数据输出覆盖输入、无效来源hash/宽松schema、alias错误复用脚本、原生零消费失败覆盖旧证据、单条runs索引panic、后置身份失败丢失case摘要、同请求重复不可覆盖绑定误拒绝、identity写入缺失资产及大小写绕过。均有聚焦负例；不得把旧review最终消息中已修复的问题当作仍待实现。

## 原生7次消费：必须保留的事实

所有真实消费在`data/runtime/baseline-2026-10-19/research/calls.jsonl`及其`.blobs/`，scope=`research-first-batch-v1`，context=`4ea4d6cb6aa9b1eac4d9ca724ebe451be620ea7fa4d42473fa0f86b9511f17db`，总上限4096。

1. 第1/2次：Rabbit执行/重放，一致，27提示canonical对照。
2. 第3/4次：Phantom初始提示前缀/重放，一致；不是完整终场成功。
3. 第5/6次：赛事执行/重放，一致，64提示；后置身份采集遇到与debug worker并发构建的真实冲突，未授予资产一致性。已离线恢复，0新增调用，原失败保留。
4. 第7次：最终补验的执行成功、资产前后一致、64提示；第二次调用在收费前因重复写immutable checkpoint被拒，未执行重放，故replay_matches=false。随后修复为先读绑定、同hash复用、异hash拒绝。新增回归覆盖执行+重放消费2、重开再重放消费3、改请求拒绝且仍3。修复后尚未新增原生。

目前账本7 begin/7 complete、unknown=0、reserved=0。complete只表示回包已保存，不代表每例达到终场。暂停时账本最后记录hash=`9f0a3685575fe149c5b7ea46d95c743ca31d4372c352541693b93d19e45c3f91`。禁止清零、删blob、丢弃失败或换账本绕过消费。

关键证据均在同一research目录：`frozen-cases.json`，`initial-batch-capture-failure.json`；`evidence/rabbit-2.json`、`phantom-4.json`、`tournament-6-1792382565073757500-0.json`、`tournament-7-1792383041824358400-0.json`、`tournament-existing-context.json`；最后一次原生输出见`native-final.log`。

**时间窗不能在暂停后偷偷重置。**原start为1792381989（北京时间2026-10-19 11:53:09）；为30秒worker留余量，13:52:39起拒绝新调用，原两小时截止13:53:09。恢复若已过期，先继续离线/身份工作；额外原生需用户明确新的时间窗口安排，并保留原7次累计费用。不得改research/start或通过新建账本变相突破上限。

## 数据证据：只采用当前v3

`data/runtime/baseline-2026-10-19/data/`：

| 当前文件 | SHA-256 | 范围 |
|---|---|---|
| ordinary-inventory-v3.json | 308ab87c823c21c754dda6634fbc38c46c1d347ab6a62a142fc4b0883047d8db | 13728行；发行依据30卡；脚本12582匹配、2缺失、185未知 |
| tournament-inventory-v3.json | 3e0b488e6052299a6ea882335995b2c994bcc202ba342abdf3fe9bb60139ae35 | 14759行；发行依据39卡；脚本13455匹配、2缺失、314未知 |
| language-audit-final.json | 9bcd2615280f33ee37f4b99fabc60f551f351841ab87b65d86a62a252fa8b71d | 39卡zh-Hans候选；未人工核对/许可未知，qualified=false |

普通/赛事分别另有959/988项不需专用脚本；未知主要含alias脚本复用未认证。两项缺失卡号为88264978/88264979，发行身份亦未确认，不能称正式OCG缺失两张。清点行数不同于普通目录13665张的过滤后快照计数。旧报告含中间实现误判；旧`tournament-inventory.json`还存在重复尾部，不作为当前验收输入，但保留历史。

`data-evidence-summary-v3.json`登记上游差集；普通库比固定Babel数据少1031行、赛事相同，仅为数据差集，不证明正式发行分母。中文源固定commit和hash在`configs/language-sources-2026-10-19.json`，原文/数据库只在忽略目录，不能提交。

## 恢复顺序：不要重做整个任务

1. 阅读索引/TASKS/本页/TESTING；核对HEAD、Git差异、暂停清单和source快照。保留用户或其他会话在暂停后新增的修改，不直接覆盖恢复。
2. 仅当源码变化时按受影响范围复验；不因续接就重复全部原生实验。最后一轮237/54等计数已保存。
3. 重新用`ygo_data.identity build-record`包装最终离线构建，产物应包括CLI、worker及research example。现存`build-before-native.json`早于最后安全/重复绑定修复，不能作为最终构建关联；原始普通dist不刷新。最终可用命令：

```powershell
$env:PYTHONPATH='python'
py -m ygo_data.identity build-record --repo . --artifact cli=target/debug/ygo-cli.exe --artifact worker=target/debug/ygo-engine-worker.exe --artifact audit=target/debug/examples/research-audit.exe --output data/runtime/baseline-2026-10-19/build-resumed.json -- cargo build --workspace --all-targets --offline --locked
```

4. 先检查上述原生时间窗门禁。允许恢复时，仅补赛事执行/重放两次；使用同一context/账本的既有低层输入`tournament-existing-context.json`，原请求来源已由Python冻结校验。正常运行不带`--recover`；预计累计9次。运行前后不得编译、更新worker或资产。失败保留原费用，不能无限重跑。低层恢复`--recover 5`只读原5/6结果，不代替新验收。
5. 所有源码/文档稳定、无编译和资产更新后，运行`ygo_data.identity capture --repo . --cli target/debug/ygo-cli.exe --ordinary-config configs/engine.toml --tournament-config data/runtime/tournament-2026/engine-development.toml --output data/runtime/baseline-2026-10-19/workspace-resumed.json`。逐文件多次散列会耗时数分钟，不在采集中改源码；验证schema、稳定身份、build.source_after与capture.source、CLI/产物hash关联及无个人绝对路径。该双配置实采尚未执行。
6. 完成最终JSON/schema/相对链接/差异检查，更新TESTING/TASKS并报告首批范围。即使通过也不提升全卡/正式v6/最优性资格。不自动提交、推送或刷新dist。

暂停附加清单和源码备份在忽略目录`data/runtime/baseline-2026-10-19/pause/`。它不包含外部数据库、脚本、DLL或Git元数据；原生账本及运行数据仍须保留原目录。恢复时先核对清单，再决定是否需要源码备份，不能盲目覆盖现工作区。
