# 天玑实验合同兼容修复与离线收尾（2026-10-22）

## 结果

本交接完成的是离线合同修复和交付，不改变原生实验结论。源码恢复起点为`8ad8afa9a5994d0290d904ae0d069301b052ed821f1d110daa9d9aeadb624ef0`，389份文件。暂停验收SHA为`d73bdbdf1cdd9e8202ef7e3f88faf9de6b121e8c0aba2729c79e25e006e286a7`；61份暂停证据、暂停源码归档及366个历史保护文件复核一致。

原生事实保持：stage1成功发现prompt7的唯一天玑激活项；stage2到达opcode18区域选择、prompt9，未到opcode13。两个分支执行和原生重放均未发生。六份账本累计26次、未知0；本次恢复新增原生调用0，六槽scope余下4槽封存。

## 合同修复和验证

`schemas/native-prompt-probe.schema.json`仍是schema v1。仅移除`$defs.versions.properties.catalog`与`banlist`的`minLength:1`；两个字段仍为必填字符串。成功结果、资产SHA、核心/初始化器及资格字段约束不变。测试保留冻结旧请求的空标签，检查空/非空组合、缺失/null/非字符串、损坏哈希、空成功、伪造资格和错误阶段。

先执行的红测试确认完整成功报告因空标签被现schema拒绝；修复后3项聚焦测试通过。Python全套为214项，207通过、7跳过，耗时约102.04秒。跳过项是v3报告、v4报告、本机引擎ABI、本机快照、实际v2报告、完整策略报告及赛事本机资产独立重放；均需显式本机资产或opt-in。Rust生产代码未改，不重复Rust总检；引用原批288通过/36忽略、examples21通过。

修复后的schema验证原manifest、stage1成功收据、stage2失败收据和summary。已保存的原生时点runner仅用于两阶段`--verify-recorded`和`--stats`，共4次零调用检查；账本、收据和全部原暂停证据字节保持不变。stage1收据消费前缀1，stage2前缀2，当前消费2、未知0。没有运行普通runner、worker或doctor，也没有创建窗口/账本或回答区域18。

## 证据目录

新恢复证据保存在忽略目录`data/runtime/p1-tenki-probe-native-2026-10-21/recovery-2026-10-22/`。其中`recovery-start.json`记录暂停材料校验；`artifact-revalidation.json`记录schema和原产物SHA及零调用复核；`python-full.log`与`python-full-summary.json`记录测试；`contract-review.json`记录变更范围审阅。原批的`pause-acceptance.json`、`delivery-checkpoint.json`、stage收据、manifest、summary、账本和原生二进制均保留原样。

最终构建关联、最终源码归档及验收文件在本交接生成后另行写入同目录；以`recovery-acceptance.json`与`recovery-checkpoint.json`为最终状态事实源。构建记录只表示该命令/工具链/产物关联已记录，不证明可复现构建。

## 后续门禁

合同修复和离线交付可以完成，但本批原生目标仍未通过。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均为false。后续如继续，须为公开的区域选择规则、新scope和预算另立计划；不得消费当前封存4槽或根据隐藏牌序/seed选择响应。普通部署、active资产及原worker未切换；Git未提交、未推送。
