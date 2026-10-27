# 天玑公开区域选择、opcode13发现及两分支验真

## 目标与固定边界

目标是使用独立 `tenki-placement-probe-v1` scope（最多6次请求、2小时）验证冻结天玑线路：区域18选择公开坐标`player=0/location=8/sequence=0`，再分别测试opcode13的false/true响应及各自一次独立重放。旧scope剩余4槽保持封存；原stage2仍是opcode18失败证据，不重写为成功。

固定顺序为：stage1冻结激活前缀到区域18；stage2从公开菜单选择区域0到opcode13；stage3 false 到己方idle；stage4重放stage3；stage5 true 到两张`69247929`的opcode15菜单；stage6重放stage5。stage1/2只有提示发现，不赋予重放资格；stage5不选择检索对象。出现非预定提示、响应集变化、资产漂移、未决消费、超时或重放不一致即停止。

## 本轮交付

- Rust新增`TenkiPlacementBatch`专用收费封装及单阶段example runner；固定scope和六个用途槽位，按精确账本前缀、不可覆盖请求意图、父阶段收据及公开菜单派生门禁。旧预算实现未改。
- Rust oracle独立核对opcode18原始7字节帧、mask`0xffffe0ff`及五个己方魔陷区响应；opcode13原始帧、player和描述`59877851398144`以及false/true字节；后续opcode15保留两个同名卡实例的位置。
- Python新增`native-tenki-placement-probe`编排入口、输入派生、旧证据基线校验、窗口/资产检查和收据恢复。
- 新schema v1覆盖manifest、stage、summary和prepare收据；修复`Ok`/`Err`字段被`additionalProperties:false`误拒的问题，并约束成功结果、响应oracle字段、阶段/opcode对应关系与资格标志。失败和未知消费仍可表示。
- 新增合成测试，覆盖菜单顺序不影响坐标选择、响应字节、父请求派生、阶段汇总、schema成功/失败/未知及伪造资格拒绝。

## 实际执行状态

离线实现、独立审阅和默认总检完成。六份旧账本经只读基线审计仍累计26次、未知0；此前保存的runner以`--verify-recorded`与`--stats`复核旧stage1/2，共4个零调用检查，旧账本字节与哈希不变。stage1保持成功，stage2仍是`unexpected_intermediate_prompt`并停在opcode18；本轮新stage1–6均未执行。

原生门禁未通过，原因是366项保护清单中365项匹配，唯一差异为受保护的`target/debug/ygo-engine-worker.exe`：清单SHA256为`a384b35aff160049b3381f15bfc35e17cf373a1ada54986b8c884bde09c78c7e`，当前文件为`be6aae6ec2d03ae3293f2954fb84be211483bd9c5b57e4ac3b546b7239db9eba`。对工作区、关联checkout及保留运行时副本/源码包的只读搜寻没有发现该哈希原件。历史构建记录标注`source_changed`、`observed_command_only`及`reproducible_build_proven=false`，不能作为原件来源证明。

因此本轮没有创建`data/runtime/p1-tenki-placement-native-2026-10-22`、构建记录/源码归档/候选产物，没有扫描候选资产、创建窗口/manifest/请求/账本，也没有运行普通runner、worker或doctor。累计仍26次、未知0，本轮新增原生调用0。所有资格标志保持false。

## 恢复门禁

不要把不同哈希的worker复制到保护路径或从当前源码重建后冒充历史原件，也不要从保护清单删除该文件。只有找到与固定SHA完全一致且来源可核实的原件，或用户/权威基线明确批准重新锚定保护基线后，才可恢复原生准备。之后依序复核六账本及旧runner零调用收据，运行新的离线预检，冻结源码/产物，先持久化窗口起点，再采集普通/赛事身份、保存具体请求并运行prepare-only，最后按stage顺序串行执行。此前窗口和封存4槽均不得复用。

本轮验收及续接细节见[断点记录](2026-10-22-tenki-placement-native-handoff.md)。
