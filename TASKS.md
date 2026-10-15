# 实施任务与验收状态

## 2026-10-16 单次灰流丽中断与恢复

- [x] 固定对方灰流丽资源、唯一响应点、双方完整决策与运行协议v4。
- [x] 无干扰、原方案受阻、实际锚点恢复三组；目标保持Rusty＋Fog。
- [x] 从原始事件恢复费用、次数、通常召唤机会与实例；既有历史进入恢复预测。
- [x] v4规划/分析、来源知识身份、每组512次账本及独立前缀见证。
- [x] 修复手牌发动源CHAINING后费用MOVE绑定；独立审查三项合同问题与回归。
- [ ] 最终全量回归、旧报告兼容、重复身份和干净checkout部署验收。

范围与使用见 docs/RECOVERY_PLANNING.md；最终结果以 docs/TESTING.md 为准。后续先比较同一手坑的响应时点与展开顺序，再进行固定样本评估和构筑诊断。


## 2026-10-15 通用目标与有界收益（已完成本轮验收）

- [x] ygo-goal：三值布尔、数量/等级/阶级/素材/历史、发动窗口和有界收益目标。
- [x] 规划v3、事前目标预测、原始提示/响应绑定、实际逐节点评估及辅助分支证据。
- [x] 共享调用账本、独立见证及外部重放预留，失败/未知与已有推荐保留。
- [x] v2/v3评分参数生效、旧版本分派与重放路径保留。
- [x] 修复批量召唤实例、历史素材时点和否定条件披露；升级 phantom-goal-v2。
- [x] 按原始事件核对 CHAINING/CHAINED 顺序；费用后源快照及同名复活定向真实断言通过。
- [x] 默认Rust98项、opt-in13项、Python全量11项；审查修复、干净checkout与部署验收完成。
- [ ] 后续：单次指定手坑与恢复 → 固定样本起手评估 → 构筑诊断。

范围和示例见 docs/GOAL_PLANNING.md；最终数据以 docs/TESTING.md 为准。


## 2026-10-14 Break Sword v2 与效果验真

- [x] 16个效果的人工真实操作案例、符号资源预测、结算后反例及独立前缀见证。
- [x] 协议v3、规划v2/分析v3及固定对方 Ryu-Ran 合成场景，保留旧版读取和重放。
- [x] 超量素材/取除/破坏事件、复活等级变化、召唤历史和暗属性限制。
- [x] 8个人工基准正例、4个资源受限、4个覆盖/预算降级固定起手回归。
- [x] 类型化失败、v2预测/素材/检查点/场景 Schema、伪造证据拒绝。
- [x] 独立审查三项重要问题回归修复；67项默认、9项真实引擎、Python9项全量通过。
- [x] 干净 checkout 重新构建部署、冻结哈希/线路 ID 一致、旧 Rabbit/v1 Phantom 重放通过。
- [ ] 可配置目标及第二目标；随后单次手坑、起手样本评估与构筑诊断。

说明见 docs/BREAK_SWORD_VERIFICATION.md；完整本轮验收状态见 docs/TESTING.md。

## 2026-10-14 语义规划首版交付（历史）

- [x] 本地源码基线 1db8cd8；外部资产保持忽略。
- [x] Python 3.14 全量 Schema/契约检查恢复。
- [x] 十二卡知识来源与测试引用校验，逐效果声明支持范围。
- [x] 预先生成目标方案，次数/资源/触发限制，原始提示位置与效果绑定。
- [x] 四个新 CLI、独立 v1 规划报告与旧 v2 兼容重放。
- [x] 真实引擎目标终场与独立重放，决策前缀局面见证。
- [x] 预算失败、解释改写和手牌洗牌实例回归。
- [x] 独立干净 checkout 离线构建/部署、冻结资产校验、doctor、固定节点分析与重放。
- [x] 固定输入/512 节点对照及线路 ID 一致性；验证记录见 docs/TESTING.md。
- [ ] 完善逐效果真实回归；补充当前 unsupported 的超量/破坏、保护和对手回合效果。
- [ ] 收紧部分嵌套观察消息及继承 v2 的 JSON Schema。
- [ ] 单次手坑及恢复、多起手评估、残缺构筑、HTTP/UI。

当前说明见 docs/SEMANTIC_PLANNING.md；下文保留 2026-10-07 验收历史。

状态审查：2026-10-07。M0–M4 本机首版已实现并在本机复验；细节见 docs/TESTING.md、docs/DEPLOYMENT.md。本文件区分已交付能力和仍待完成的工程工作。

## 已交付：M0–M4

- [x] M0 固定 Project Ignis core/Lua commit，构建 x64 Release DLL，ABI 11.0 布局探针和 SHA-256 manifest；独立本机配置与 engine doctor。
- [x] M1 只读导入本机官方 cards.cdb 并生成内容寻址快照；固定 OCG 列表及生效日期；未知卡、别名、规则区域和起手校验。
- [x] M2 真实决斗生命周期与回调、协议 v2 长度分帧、类型化提示响应、决策记录、End Phase 终场处理及隔离超时/崩溃回收。
- [x] M3 预算 beam search、完整前缀缓存、启发式终场评分与覆盖说明、稳定线路排序、候选独立重放。
- [x] M4 导入/状态/牌组/搜索/重放 CLI、中文摘要、本机部署脚本和 CI 合同检查。

## 历史验证状态（2026-10-07）

- [x] cargo fmt --all -- --check。
- [x] cargo clippy --workspace --all-targets --offline -- -D warnings。
- [x] cargo test --workspace --offline：35 passed、0 failed、1 ignored。
- [x] opt-in live_engine 本机测试：1 passed。
- [x] 本地 engine doctor、catalog/banlist status、Rabbit 牌组校验、engine smoke、combo analyze 与 combo replay。
- [x] 本轮可运行的 Python focused tests：4 passed。
- [ ] Python unittest 全量发现及 JSON Schema 测试：本轮被缺少 jsonschema 和临时文件 PermissionDenied 阻断，需在可写测试环境复验。
- [ ] 从干净 checkout 执行完整本机重建/部署流程；本轮工作区没有做该操作。
- [ ] 审阅并建立源码 Git 基线。当前 HEAD 仍为 Initial commit，大量项目文件未跟踪；本审查没有暂存或提交。

## 历史待办：M4.1 可复现交付（已由本轮完成）

- [ ] 维护者审阅 Git 跟踪范围；纳入实现源文件、脚本、文档、schema、CI 和可分发 fixture。
- [ ] 排除本机引擎二进制、卡库/卡图、个人配置、运行数据与报告。
- [ ] 解决 Python test extra 安装限制并通过完整 Schema/契约测试。
- [ ] 确保报告能记录请求、搜索预算、引擎/API、catalog、banlist 和评分规则版本。

## 待办：后续产品能力

- [ ] M5 扩大正式卡组、消息/提示解析、效果和评分覆盖；所有支持范围有真实引擎回归。
- [ ] M6 指定手坑、先后攻、对手响应与后攻解场；输出中断和恢复线路。
- [ ] M7 固定 seed 的随机起手统计、终场分布、失败原因和不确定性评估。
- [ ] M8 字段检索、用户约束、合法候选生成与不完整卡组补全。
- [ ] M9 HTTP/API、网页任务体验；基于已验证轨迹评估学习型排序。

原型静态排序和 ApiService 类型仍在仓库中作为兼容代码；当前产品入口是 CLI，不提供 HTTP 服务。启发式评分不代表胜率或已证明最优。
