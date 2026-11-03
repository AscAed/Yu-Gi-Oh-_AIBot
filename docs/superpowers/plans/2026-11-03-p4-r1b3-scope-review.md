# P4-R1b-3 scope 只读复核

日期：2026-11-03。本记录只核验既有设计、旧run审计和固定输入/资产哈希；未创建scope、运行worker、调用引擎或写入旧run。

## 结论

既有[实验设计](2026-11-02-p4-r1b3-native-resume-experiment-design.md)已经把一个固定双动作路线的恢复、独立连续执行与原生查询重放分成两个新`CallJournal`账本，并定义64次请求/账本、30秒worker超时、7200秒共用窗口、暂停marker和停止条件。它仍是合适的设计基线；文档明确规定实时执行需另行授权。

旧run `p4-r1b3-1793625696606077800-54284`仍不可续跑。其只读审计确认账本为1097字节、3行，1次已完成Execution，0 Witness；没有暂停marker、协调器终止记录、恢复重开或replay。旧manifest把对手牌组/手牌计数记为0/0，固定trace为39/1；保存的输入、计划、source和driver身份均不匹配当前修正版。具体证据见[追加账本审计](../../../data/runtime/p4-r1b3/p4-r1b3-1793625696606077800-54284/read-only-journal-audit.json)。该1次Execution继续只属于旧scope，不得与后续新scope合并或当作恢复/replay通过。

## 固定输入与资产哈希复核

下列SHA-256于2026-11-03只读重算，并与2026-11-02实验设计中的基线相同。该核对确认字节身份，不调用engine，也不验证当前ABI、源码构建关系或资产采样后的稳定性。

| 固定材料 | SHA-256 |
|---|---|
| `configs/tournament-2026.assets.json` | `25ac37254b4f04336320f621d8f010e4a7cbfa90026407b1a376718e15ea05ad` |
| `configs/tournament-2026.source.json` | `d458804dce80c01fc27f5863c0b0ec821624627a61c0fd982dded04f41bc6aff` |
| `tests/fixtures/tournament-2026.rules-resource.contract.json` | `db79e2f51a7c724bc3c72a78e96e0c7f6f544ceb59ffbd61a4a6ef9084ec5a87` |
| `tests/fixtures/tournament-2026.trace-resource.json` | `cc98145d68dd560863c40b4ac218220ebb0ee4e5069c26e91a572beee1d3032d` |
| `data/runtime/tournament-2026/frozen/manifest.json` | `2131d85669dc307a2cb0a82096b6460acba3ecbd63eca3852bf0158f450d1a2c` |
| frozen `cards.cdb` | `3530f406ba92b0f8d5699aa107e95158a1f1b4816f8f5ca2dd82c490301ef632` |
| frozen `engine/ocgcore.dll` | `446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9` |
| frozen `engine/manifest.json` | `2028d6b7d5bf6878c11107760e73f33cf8dcfcf977d312c86ff98640c736e457` |
| frozen `scripts.json` | `26c44946c7aba56900ededc5358e163fce71d5b99182f0d0fa910739bc3d9c94` |

2026-11-03当前HEAD为`672e5a823fcad60e9413d79cac810b68a2bb003c`，工作区含未提交改动和未跟踪的R1b-3示例/测试源码。原隔离worker（`6c557416206a3eda6e4f4e012eb39ffa2cda7313a90174290295ba0f31be2d89`）和驱动（`aea5a819c5f16f66be5e74e4908f87eb1c0499fae05541b2590b4e836c0d267e`）未绑定当前工作树。

第一次新target `prepare-only`进一步发现驱动仍硬编码旧worker路径。该次退出码为0，但身份绑定失败；它没有创建scope、worker进程或native调用。观察保存在`target/p4-r1b3-current-20261103/preflight-attempt-01-mismatch.json`。随后`harness.rs`改为从`current_exe()`的Cargo profile目录定位worker，并沿用仓库路径与符号链接检查；manifest创建和重开验证均绑定当前`current_exe()`。聚焦测试添加了worker路径断言。

修正后在隔离target `target/p4-r1b3-current-20261103/cargo`离线重建。HEAD为`672e5a823fcad60e9413d79cac810b68a2bb003c`，当前worker SHA-256为`d50ac8ae796380e29d79f796170efea772cc2dad907923b499af5a47513c2cc1`，driver为`076d2a2ebf6b252688d687e2194829c0ed21e93b039ec4eb8df69bba4724d11c`。参与源码、Cargo.lock、tracked diff、工具链和完整状态清单见`target/p4-r1b3-current-20261103/source-identity.json`。该清单在本文完成后重新生成，以覆盖最终tracked diff。

新零调用预检run `p4-r1b3-1793644408613378500-32336`确认当前worker存在且路径位于本轮隔离target，固定两动作路线正确；输出根目录和scope均未创建，worker进程数、native调用数均为0。完整结果见`target/p4-r1b3-current-20261103/preflight-result.json`。R1b-3 harness 5项、格式、workspace全目标Clippy及默认串行workspace测试通过；明确opt-in原生/冻结资产测试未运行。

## 后续真实执行前置条件

1. 旧run、旧账本和历史诊断全部保持原位；后续若继续，必须用新`run_id`和两个全新scope，不能从旧账本续跑或抵扣其消费。
2. 每次执行前都在新隔离target按届时完整工作树重建worker和实验驱动，并固化HEAD、tracked diff、参与构建的untracked源码、`Cargo.lock`及两个产物哈希。源码身份缺失、资产漂移、计划路线不匹配或构建失败时停止。
3. 本轮`prepare-only`零调用预检只验证了固定输入、当前worker路径和零调用边界；不得据此跳过届时的资产/身份复核，也不得复用本轮run ID创建scope。
4. 只有恢复scope达到设计中的安全暂停状态并通过真实账本认证，才可启动独立replay scope；任何unknown、未决调用、marker不完整、预算或窗口到限均停止，不新建scope续跑。

本批完成当前源码/产物身份快照及零调用预检，没有改变R1b-3真实恢复与独立replay门禁，也没有授权实时scope。任何后续原生执行继续遵循原设计的独立授权边界。
