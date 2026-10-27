# 2026-10-23 天玑placement validation六阶段验真断点

## 状态

本批已经完成并暂停。新scope `tenki-placement-validation-v1` 的六个固定阶段均成功，实际消费6/6、未决0；历史消费26，累计32。原生前缀只覆盖区域选择、opcode13 false/true及各分支重放，不包含检索对象选择或终场。旧scope、旧预算和其余历史证据不变；不得将旧窗口或额度转入其他实验。

## 固定输入、构建和窗口

- 基线交付：`data/runtime/p1-tenki-runner-repair-offline-2026-10-23/final-build/delivery.json`，锚点SHA256 `84a3fc887e967f45c2c807d104450b41fbb31c038e93132b30b6bebadc669e22`。
- 新证据根：`data/runtime/p1-tenki-placement-validation-native-2026-10-23/`。
- 窗口：`started_at=1792739271`（2026-10-23 15:07:51 +08:00），7200秒，6次；全部消费完成。创建至stage6进程诊断保存时约22分18秒，包含准备与身份/预检耗时。
- context：`307ab5c44bb5fc6231757a79625eeeafd1717e074f31a100ec6d56835c23a541`。
- stage1请求SHA256 `cbd0a1223e8e63db6c0901f63076871f1c7a5c5f551c81b0b59692f6fa9a2baf`；prepare-only新增原生调用0，预检通过。
- 原生源码身份`e9538276391f0e08bfa707534aeab6c8e663784da8fcd9a97dc5ea0e9eb6e8f0`、683文件；构建记录identity `00109bb132b00a61ff4330db8d950bb9b395ef82e94f89d53a27d6f3b2401886`，构建关联已记录，但可复现构建未证明。
- runner SHA256 `60fb6b9b531d1f1166fbb51a009a507f61c06534cf90a14d308607e8a5dcc035`；worker `905ec0d590755565c74b7c8bd60919474174e0614e96b81b4880555f57a5fb03`；CLI `ef663c1ea863f22bdb11e0b1c1a9157f750eb3021b2fc27dc1e3769ece2b9796`。源码归档SHA256 `8c8c5d676d34ae03161491cd0a6dcedd5cc7c47d5ed2ecabdfbf4231c6e34e7e`；文件清单SHA256 `fd02e8e722ac1fdb0fdfc0058c9d4007f1059edfe3c641c8b4a2774a00939653`。
- 普通与赛事资产身份均绑定于manifest；原生阶段使用普通资产，赛事身份只作为冻结来源核对。本机资产路径保留在忽略证据中，不复制到版本控制文档。

## 六阶段结果

| 阶段 | 结果 | 收据SHA256 | 备注 |
|---|---|---|---|
| 1 Probe | 通过 | `064fac05682b1974e3c93499df5542503d0b10913091861c734ae4b4f3cb6f9d` | 己方prompt9 opcode18；原始帧 `[18,0,1,255,224,255,255]`、掩码`0xffffe0ff`；五项响应`[0,8,0..4]` |
| 2 Probe | 通过 | `63558fa16fd9d5c07b9c8475960b1018992fc788a60e72a173bb0d7981c45374` | 按坐标`player0/location8/sequence0`发送`[0,8,0]`；prompt16 opcode13，描述重算为`59877851398144` |
| 3 Execution | 通过 | `0d077d70a00877c462ab60accc5092d95a722aa015104d5b3d2ea806f344eb17` | false响应`[0,0,0,0]`，到达己方opcode11/prompt21下一idle |
| 4 Replay | 通过 | `aa15c7e6166c60bad762d3705cb71c2d7afd6679057ecfbd7855c0e1571368db` | stage3请求独立重放一致；归一化哈希一致 |
| 5 Execution | 通过 | `405a1ed9cb12778ad70afbeeb336ae983531a6e114ecdb9a34f2ed5e4216cd00` | true响应`[1,0,0,0]`，停在opcode15/prompt18；两个`69247929`对应Choice index 0/1、实例sequence 15/0，未合并且未选检索对象 |
| 6 Replay | 通过 | `074de016f0eb0a70d56cf4cbb6fcf2c535330050eb00b8cd3bca4764e08849f1` | stage5请求独立重放一致；归一化哈希一致 |

六阶段均通过目标匹配、响应oracle、自动响应单动作、资产稳定和窗口结果时点检查；每阶段消费前缀依次为1至6。原生summary为`successful=true`，SHA256 `9b250b347a9f05c3eef8d321f6eba259d389d0cb1a9f4c1db0a84b205b8eee49`。保存runner随后执行只读`--verify-only`，结果`valid=true,native_calls=0`，SHA256 `836ef6447087290496ec9ef1a6e6f6492b1859b526099f3cc45b83bddfafd669`。账本SHA256 `4244d92bd17413861bc92d4618803bc647dd05cab074189e678be8429f89971c`，32行、12,968字节；结构为header1/checkpoint19/begin6/complete6，无未决/放弃项。独立重算新账本32条链哈希、29个blob和31个引用的内容哈希均匹配。本批6个请求全部完整，未知0。

旧confirmation的`runner_timeout`及更早placement尝试的历史结论保留原样，不因本批的新scope而改写。成功只绑定本scope的隔离worker与固定请求；不转移到普通部署、active资产、旧原生证据或其他构建。

## 验证和未完成资格

- Python：收集顶层`tests/test_*.py`运行pytest，319通过、7跳过、71个子测试通过，156.69秒。跳过项为v3报告、v4报告、本机引擎ABI、快照/报告、本机v2报告、完整策略报告、赛事2026独立资产配置（均opt-in）。递归收集碰到ACL拒绝目录的失败尝试没有计入通过；没有修改ACL或清理受限临时材料。
- Rust：`cargo fmt --all -- --check`通过；workspace全目标Clippy通过；串行workspace all-targets测试342通过、0失败、36忽略，84个目标；独立workspace examples测试33通过、0失败、0忽略。Cargo使用隔离target目录并以offline/locked运行。ignored用例原因见本批`target/rust-ignored-tests.txt`。
- prepare-only前后冻结输入与两套身份相符；normal六次进程均退出0，单JSON stdout及stderr阶段追踪原始字节保存在`process-diagnostics/`。最终零调用verification未补发请求。
- 本批整体局部验真成功；`proof_ready=false`、`complete_action_coverage=false`、`global_optimality=false`、`native_probability_verified=false`。不声称opcode14/24、命令6、检索、终场、完整动作、完整规则或全局最优已验证。

## 交接约束

本scope已经用满，窗口和6个槽位封存。续接时先以保存runner运行只读`--verify-only`并核对原收据；不要运行normal、不要重放stage1–6、不要重新prepare或重建窗口。任何opcode14/24、命令6、后续检索、概率/信息或终场研究都必须先制定新范围与独立预算。普通`dist`、active快照与debug worker未切换；未执行doctor或48手评估；Git未提交或推送。

实跑时点产物、完整输入、账本、stage收据和原始进程sidecar保存在上述忽略目录。文档收尾后的独立`final-build/`及最终验收由该目录中的交付记录绑定；证据体积记录若遇ACL访问拒绝，应保留不完整标志并记录相对路径，不调整权限、不删除材料。
