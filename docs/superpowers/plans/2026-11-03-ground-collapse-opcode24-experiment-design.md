# P1 Ground Collapse opcode24真实提示与响应接受实验设计

## 状态与问题

截至2026-11-03，本批完成只读输入与资产复核、实验设计、固定来源离线准备，以及Ground专用收费驱动的实现和合成验证。当前准备报告通过全部来源门禁和verify-only；`execution_ready=false`。未创建研究scope、窗口或消费账本；未运行runner、worker、引擎或FFI。scope `p1-ground-collapse-opcode24-reachability-v1`仍只是隔离实现绑定，不是已创建或已授权的执行范围。

本实验只回答一个有限问题：固定Ground Collapse候选在冻结场景中能否到达真实opcode24提示；使用既定公开选区提交一次后，引擎是否接受该响应并进入后续状态。实验不验证反序等价、完整动作覆盖、概率、隐藏状态策略或最优性。

## 当前可复核输入

固定候选来自[`prepared-cases.json`](../../../data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/prepared-cases.json)中的`prompt-24-collapse-v1`，目标卡号`90502999`。冻结案例为OCG、seed `1`、main/extra/side数量`40/3/0`、5张起手；起手为`[90502999,2964201,2964201,2964201,2971090]`。完整牌表、信息边界、目标和随机性定义以案例对象为准。

当前文件SHA-256与源码固定值相符：

| 输入 | SHA-256 | 字节 |
|---|---|---:|
| 旧提示接收记录 `acceptance.json` | `0e88c82501c4bbc229d6326b6b789411a93426f9474a02cd0e83e2c6cacbfcf7` | 17,612 |
| 旧提示准备 `report.json` | `22536f6031adc88eae4bb7e2ada4f9ff374a2d227e66927e084180552e12b073` | 1,356,028 |
| `prepared-cases.json` | `235d218426e9a14fdc000ca2e81a64b00cac394f247d0c53029dc1c2e4c2b022` | 21,242 |
| 冻结输入 `frozen-cases.json` | `de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879` | 36,137 |

候选案例按`ground_collapse_preparation.py`的`sha256(encode(case))`为`ccf3143c589472dc3ea48f2ef1fcf0216f64a55cd5365e2762a26745c036e52b`；同一案例按`ygo_data.identity.canonical`摘要为`e4bb568e30afc2f841916024c823c6e228a5c907b1d61369eba0d9b0382f0a6e`。从冻结Rabbit请求派生、尚未替换worker路径的候选请求canonical摘要为`8c9808b3fd9321db33d706fd092263553a0cdf8dc516bc5c155be2e558a43dbc`。正式scope必须绑定它实际使用的最终请求字节；隔离构建worker路径变化后要重新计算摘要。

原始[`p1-ground-collapse-preparation-offline-2026-10-27`](../../../data/runtime/p1-ground-collapse-preparation-offline-2026-10-27/)中的`preparation.json`仍缺失；旧记录的25,131字节及SHA-256 `5354438945079d9df4f2867e272e2420d71605909c772f0a874b6c21b8319d74`只是历史值，目录目前只保留source list与ZIP，因此旧报告所列37成员仍未作为一个整体复验。第一次独立重准备在`latest_curry_delivery`因精确交付文件缺失而失败，2,855字节失败报告及162项目录快照均保留。随后从被忽略的`data/runtime/cleanup-audit/drive-archive-index.json`逐项取回13份私有归档源文件；每份下载字节数、SHA-256均与上传索引相符，合计141,493字节，云端副本未修改。一次中间重跑据此通过Curry delivery检查，再于`historical_sources`停在缺失父链输入；补齐该父链材料后，当前准备报告[`preparation.json`](../../../data/runtime/p1-ground-collapse-preparation-current-2026-11-03-archive-recovered-2/preparation.json)通过全部六项检查，25,131字节，SHA-256 `0571114833868488b6213997ad085cb82acf6db3eac036fe9869808189f02278`。只读verify-only为`valid=true`，核验138个文件输入及5个目录输入。此报告绑定的是当前固定来源与当前工具包，不能替代缺失的2026-10-27历史报告。

## 资产身份基线

以下是2026-11-03对当前路径做的只读SHA-256采样，不表示已运行、已加载或获得执行资格。执行前须在scope起点重新采样，并以当前源码构建的隔离worker和build record为准；当前`dist/ygo-local/ygo-engine-worker.exe`只记录作现状，不能直接作为新scope的构建证明。

| 角色 | 当前SHA-256 |
|---|---|
| 当前旧路径worker `dist/ygo-local/ygo-engine-worker.exe` | `ad4a592981535144190ec44e0dd8c4aca951ec21c0206a1346961484f37fd11c` |
| `ocgcore.dll` | `446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9` |
| `cards.cdb` | `c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225` |
| `scripts.json` | `69bf6f9d3fe444fd53890c60bde877f97b753f8d3e218a6349615d09f6740d91` |
| `engine/manifest.json` | `3fadb68cd22e9e01d8083c581ffd442f64e6af65a6c2827544b19e5bab14aa00` |
| 目标卡脚本 `official/c90502999.lua` | `67d95d32e1b6023c41516b0f15657af60121aa5b072dc85bb273fc1280912497` |
| 禁限表 | `a6344cd77c4db6dcfab02d03110954fa1c2717422f71da302970f427564506c9` |
| 当前scripts目录树身份 | `0d956cc79d24cd2b44759c15cadf3efff717faaac296b7b8a2170ab2c43c6bdd` |

`data/tmp/ocgcore-source`中的六个源码文件当前均符合既有固定pin：

| 文件 | SHA-256 |
|---|---|
| `libduel.cpp` | `4b31e3247555b6548bcd2588e944a971d6f3032da0ed12f963235275aeef3e5a` |
| `processor.cpp` | `d051d6a006baa9ad4a590d4bcc185bff112e3ed7df256ff25cd8c0ff7beaf085` |
| `ocgapi_constants.h` | `191315f0c37bdc2fc086dee457bfc8ebb10b27cb1f063d26d5776465f9dbc4aa` |
| `effect_constants.h` | `6d14bc8ba1a1aa955815266fcb3db8b49ebf8174385bfd885a881f899c7041c6` |
| `playerop.cpp` | `a9ff2c499476f70afb4afa9d3880a0070bcd54f4baf9f116cd9e79f7107c9e97` |
| `field.cpp` | `9b6aa4916a8e2f7e95cab570be886e22751c197b320f15acdf1fa7de3c5dadfd` |

## 执行前实现与准入

现有[`native_prompt_probe.py`](../../../python/ygo_eval/native_prompt_probe.py)是Tenki专用六阶段工具，绑定自己的scope和预算；不得改用该scope执行Ground案例。本批新增独立的Rust `GroundCollapseProbeBatch`、单阶段runner和Python阶段协调器。它固定最多5次收费请求、每次30秒engine timeout、单scope 1,800秒窗口及专用输出根；每个runner进程最多运行一个阶段，不重试。阶段派生只接受固定Ground激活、可选opcode18单区动作、opcode24指定两区响应及一次完全相同的独立重放。提示、原始帧、已解析菜单、响应、事件顺序和decision前缀分别由Rust校验并由Python协调器复核；资格标记始终为false。

合成覆盖包括直接opcode24的4请求路线、经opcode18的5请求路线、唯一动作/提示绑定、响应消费、异常提示停止、回放比较和账本预算隔离。所有测试都使用合成adapter或假runner，没有加载或启动引擎。Python协调器执行前核对不可变manifest、阶段请求、构建与资产摘要及冻结输入；外层runner超时60秒，出现无法认证的收据或账本时停止且不重试。只有收据和runner输出共同绑定完整账本、并确认`consumed==completed==stage`且`unknown==0`时，才把计数标为已知。

真实执行前仍需用当前driver/runner/worker/build身份重新准备和审查最终scope manifest，绑定HEAD与工作区差异、案例及最终请求摘要、DLL/CDB/脚本/禁限/core身份、输出路径、窗口起点、预算及停止规则。当前固定来源准备报告`execution_ready=false`，不能为本批创建scope或运行；即使后续准备通过，也需要独立scope授权。建议输出根为`data/runtime/p1-ground-collapse-opcode24-native-2026-11-03/research/`；旧Tenki、Ground准备和其他研究账本均不复用。

2026-11-03独立源码复核已将阶段Rust模块、runner、Python协调器及测试纳入19成员固定工具包，并重新生成当前来源报告；当前报告SHA-256为`a238a2f114c7cb26b6f1e79d6ca34b3e5f01f33bdb57eab0b6d2f650c2bb8c99`，六项来源检查和只读verify-only通过。v1 schema允许正整数成员数以保留历史结构兼容，当前profile和ZIP校验仍绑定19个精确成员。报告仍`execution_ready=false`，所以这只确认离线准备材料与当前工具源码绑定，不授权创建scope或运行真实提示实验。

## 建议的单次窗口

- 一个新scope、一个固定案例，最多5个计费native请求；scope总墙钟上限1,800秒，包含首次实时资产扫描和收尾。每次worker请求超时设为30,000毫秒；外层驱动需另设有界超时并把超时后的消费记录为unknown。
- 第1次请求以空decision前缀取得起始公开提示。后续每次都从同一固定输入重放，并只追加上一步已认证的唯一公开动作。
- 只接受候选牌唯一的player-0 command-5激活。若下一提示为opcode18，只接受唯一`player=0/location=8/sequence=0`动作及响应`[0,8,0]`；若直接出现opcode24，记录opcode18未出现并继续。预期动作缺失或重复、或出现其他未知提示时立即停止。
- opcode24必须来自实际引擎帧；记录原始字节、事件序号、prompt ID、player、count、mask及完整解析菜单。准入条件为`player=0`、`count=2`，且固定选区`player1/location4/sequence0`与`player1/location4/sequence1`在实际菜单中唯一存在。实际mask不要求等于合成夹具的`0xffe0ffe0`。
- 追加唯一匹配的opcode24响应，固定编码为`[1,4,0,1,4,1]`。引擎结果须为无错误的干净结果、完整消费该prompt ID/Choice，并出现后继事件或终态。第5次请求只对该响应请求做一次完全相同的独立重放；比较raw提示、prompt ID、resolved decisions、响应审计及后继结果。
- 以上流程需要4至5次预算请求：opcode18若出现则使用额外阶段；总量绝不超过5。每个native请求、runner启动、worker启动、FFI和耗时分别记账。`native_calls`按预算请求计数；FFI未单独计量时保持“未独立计量”。旧历史实际累计继续为`null`。
- 任一固定身份漂移、提示不匹配、激活或选区缺失/重复、额外消息、解析失败、响应被拒、重放差异、日志/账本写入不确定、消费未知或窗口到期时，立即停止并保存已收费前缀；不重试、不续开、不改变seed/手牌/牌组/选区。

## 结果判定与资格边界

成功只支持此固定输入下“opcode24可达”和“指定响应被该冻结引擎接受并可重放”两项局部结论。必须保留原始帧、解析菜单、实际响应字节、请求与资产身份、每阶段收据、账本统计及重放比较。若opcode24未出现、动作不能唯一匹配或响应未被接受，结果为该scope下失败/未知，不做替代选区。

即使实验成功，`complete_action_coverage`、`native_probability_verified`、`proof_ready`、`global_optimality`仍为false；不判断反序响应、其他mask、其他场景或卡片效果的一般合法性。`FIELD_DISABLED`静态解析及合成oracle结果仍与本实验的原生证据分开。

## 本批只读核验

使用Python只读读取并计算上述输入、运行时资产及core源码SHA-256；与准备器中的候选、禁限表和core pins比对一致。冻结候选牌组SHA、输入文件SHA、目标脚本SHA、CDB、DLL和scripts manifest均吻合。当前准备报告的verify-only重新计算并比对成功，复核138个固定文件输入与5个目录输入。旧Ground准备报告仍缺失，故没有认证那份旧报告或其37成员历史绑定。当前路径中的worker仅取哈希，未启动。

本批`native_calls=0`、runner进程`0`、worker进程`0`、FFI调用`0`；未创建scope/窗口/账本。这里的0只描述本批执行动作，不改变任何历史消费的未知值。

下一批做独立源码审阅与固定来源复验，并重新生成绑定当前driver/runner的离线准备材料。真实scope只有在执行门禁通过且用户为该固定输入、5请求/1,800秒窗口明确授权后才能建立并运行。计划与历史状态见[当前路线](2026-11-01-post-w1h322b1-project-route.md)、[TASKS](../../../TASKS.md)、[研究运行规范](../../RESEARCH_OPERATIONS.md)和[证据合同](../../EVIDENCE_CONTRACTS.md)。
