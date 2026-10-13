# 实施任务与验收状态

## 2026-10-14 语义规划交付

- [x] 本地源码基线 1db8cd8；外部资产保持忽略。
- [x] Python 3.14 全量 Schema/契约检查恢复。
- [x] 十二卡知识来源与测试引用校验，逐效果声明支持范围。
- [x] 预先生成目标方案，次数/资源/触发限制，原始提示位置与效果绑定。
- [x] 四个新 CLI、独立 v1 规划报告与旧 v2 兼容重放。
- [x] 真实引擎目标终场与独立重放，决策前缀局面见证。
- [x] 预算失败、解释改写和手牌洗牌实例回归。
- [ ] 单次手坑及恢复、多起手评估、残缺构筑、HTTP/UI。

当前说明见 docs/SEMANTIC_PLANNING.md；下文保留 2026-10-07 验收历史。

状态审查：2026-10-07。M0–M4 本机首版已实现并在本机复验；细节见 docs/TESTING.md、docs/DEPLOYMENT.md。本文件区分已交付能力和仍待完成的工程工作。

## 已交付：M0–M4

- [x] M0 固定 Project Ignis core/Lua commit，构建 x64 Release DLL，ABI 11.0 布局探针和 SHA-256 manifest；独立本机配置与 engine doctor。
- [x] M1 只读导入本机官方 cards.cdb 并生成内容寻址快照；固定 OCG 列表及生效日期；未知卡、别名、规则区域和起手校验。
- [x] M2 真实决斗生命周期与回调、协议 v2 长度分帧、类型化提示响应、决策记录、End Phase 终场处理及隔离超时/崩溃回收。
- [x] M3 预算 beam search、完整前缀缓存、启发式终场评分与覆盖说明、稳定线路排序、候选独立重放。
- [x] M4 导入/状态/牌组/搜索/重放 CLI、中文摘要、本机部署脚本和 CI 合同检查。

## 当前验证状态

- [x] cargo fmt --all -- --check。
- [x] cargo clippy --workspace --all-targets --offline -- -D warnings。
- [x] cargo test --workspace --offline：35 passed、0 failed、1 ignored。
- [x] opt-in live_engine 本机测试：1 passed。
- [x] 本地 engine doctor、catalog/banlist status、Rabbit 牌组校验、engine smoke、combo analyze 与 combo replay。
- [x] 本轮可运行的 Python focused tests：4 passed。
- [ ] Python unittest 全量发现及 JSON Schema 测试：本轮被缺少 jsonschema 和临时文件 PermissionDenied 阻断，需在可写测试环境复验。
- [ ] 从干净 checkout 执行完整本机重建/部署流程；本轮工作区没有做该操作。
- [ ] 审阅并建立源码 Git 基线。当前 HEAD 仍为 Initial commit，大量项目文件未跟踪；本审查没有暂存或提交。

## 待办：M4.1 可复现交付

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
