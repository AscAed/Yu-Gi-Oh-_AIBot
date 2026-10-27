# 天玑opcode 13批：额度暂停断点（2026-10-22）

用户明确要求因Codex五小时额度不足5%暂停。原生已经按[实施计划](2026-10-21-tenki-prompt-probe.md)在第二槽停止；恢复先完成下述离线收尾，不新增原生请求、不复用剩余额度。

## 当前真实结果

本批目录保持`data/runtime/p1-tenki-probe-native-2026-10-21`，跨日不换目录、scope或窗口。新scope为tenki-prompt-probe-v1，上限6，实际2次均完成、未知0；旧五账本24未变，累计26。新账本SHA256为`5337352e249a13eb51a5a6dd124bc2397c4402a68e99cd77c2bffc7da22392b6`。余4槽位封存，禁止调整线路重试。

- stage1成功：己方idle prompt7，唯一command5/index0发动57103969，字节[5,0,0,0]；消费前缀1。
- stage2调用完成但目标验证失败：按stage1菜单发动后，停在己方区域选择opcode18、prompt9，共5个区域动作；未到13，diagnostic=unexpected_intermediate_prompt。消费前缀2；资产前后相同。
- 未执行false、true或任何原生重放，13可达/响应接受未获验证。不要把两个发现调用称为重放。
- Rust保存的两份收据均已由原生时点runner带--verify-recorded零调用验证；新账本、原收据字节未变，stage1保留消费1前缀而当前账本为2。旧366保护文件及manifest静态核心来源未变。

## 已交付实现及验证

新增PromptProbeBatch、独立prompt-probe单阶段runner、native-prompt-probe CLI和独立manifest/stage/summary/prepared合同。固定牌组/版本哈希、阶段顺序/用途/父收据、严格原始13/15、自动单动作、输出路径及重复键、消费恢复均有合成测试。Python与Rust实现agent均已停止编辑。

原生前Rust格式及全目标Clippy通过；workspace串行288通过/36忽略（187.353秒），examples21通过（5.494秒）；Python214项、207通过/7跳过（墙钟104.657秒），独立聚焦32项通过。逐项跳过在python-counts.json/rust-counts.json。真实资产opt-in、doctor、48手未跑。测试/构建时点源码`6a838b72d583eb9c5bd3a5ff13c140c3a1782cfc19dc84562624c4a3c0a3da76`、388份文件，原生完整归档native-source.zip及build-native.json保留。候选worker/runner/CLI副本在native-artifacts，仅候选配置替换worker；原部署不切换。

双资产重复身份采集383.016秒，窗口在首次候选扫描之前独占保存；prepare-only通过且当时无收费账本。窗口及源码在原生阶段冻结，跨日没有重置。

## 尚未完成的离线修复（恢复入口）

原生编排已正确停门并保存summary；外层run-native.py在随后验证stage1合同时报错，因此没有生成原预期native-end.json。不要重跑run-native.py；它包含首次窗口创建和原生执行流程。真实结束改存native-end-paused.json、pause-verification.json，原始收据和账本不得修改。

明确根因：native-prompt-probe.schema.json的成功阶段versions规则对catalog/banlist统一要求minLength1，但冻结旧RuntimeVersions合法使用空字符串；请求及结果中的这两个标签均为空，资产另有固定内容哈希。schema错误不是执行错误，不能把stage1原生结果改写为失败，也不能把stage2改写为通过。

恢复步骤：

1. 先核对delivery-checkpoint.json、pause-acceptance.json、paused-source.json及完整归档、上面的账本哈希、两份收据及366保护文件。保留当前未提交工作，不从HEAD恢复。
2. 新增聚焦失败测试，使用实际旧版本标签catalog=''、banlist=''的完整合成成功stage；保持规则/核心/资产哈希等必要约束。仅放宽这两个已存在且有独立内容哈希绑定的元数据标签，不整体放宽成功合同。
3. 修复schema；用修复后的独立合同只读验证原manifest、stage1成功、stage2失败、summary。补缺字段/伪造成功负例回归，实际原始材料仍在忽略目录；不编辑原报告或账本。
4. 跑Python全套及聚焦合同测试，保存新的测试源码身份及日志。Rust生产代码未改时不重复已通过Rust总检。保留本批原生时点的旧schema及归档作为失败证据。
5. 仅使用原生时点runner的--verify-recorded/--stats核验已有收据，禁止普通执行模式、禁止给区域18响应。完成最终文档、构建关联、双身份引用、完整源码归档、验收清单与断点；本批始终按实际2次收尾。

后续若要回答区域18并到达13，必须另定新预算和公开区域选择规则，冻结新scope/请求及父证据。不得消耗当前剩余4槽位，不得根据隐藏牌序或seed选动作。

## 资格与保存约束

本批尚未完成最终交付验收，暂停清单明确status=paused_incomplete，不当作全部通过。proof_ready、complete_action_coverage、global_optimality和native_probability_verified均false。内部FFI/legacy查询总数未统计，保持未知。无部署切换、新规则资格、Git提交或推送。恢复后先做离线收尾，原生阶段不自动恢复。
