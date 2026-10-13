# 本机验证记录

最后复验：2026-10-07，Windows x64。引擎固定为 Project Ignis core API 11.0；数据快照为 OCG 2026-10-01；请求使用 initializer=fixed-hand-shuffle-v1。以下是本机证据，不代表远程 CI 已运行。

## 1. 源码与测试验证

| 命令/检查 | 本轮结果 | 说明 |
|---|---|---|
| cargo fmt --all -- --check | 通过 | Rust 格式一致 |
| cargo clippy --workspace --all-targets --offline -- -D warnings | 通过 | 无警告 |
| cargo test --workspace --offline | 35 通过、0 失败、1 ignored | ignored 是需要本机真实引擎资产的测试 |
| cargo test -p ygo-engine-adapter --test live_engine --offline -- --ignored --nocapture | 1 通过 | 显式启用真实引擎测试；约 2.19 秒 |
| Python focused suites | 4 通过 | 数据合同 2 项、源码适配守卫 1 项、固定运行时 manifest 1 项 |
| Python unittest 全量发现 | 未完成 | tests/test_schemas.py 导入失败：当前 Python 环境缺少 jsonschema |

尝试安装项目的 test extra 时，pip 以及 venv ensurepip 都在临时文件写入阶段收到 PermissionDenied；repo 内临时目录方案也未解决。因此本轮没有声称 Python Schema 校验通过。之前部署记录中曾有 6 项 Python 测试通过，那是另一运行环境的历史记录，不能替代本轮复验。

实际引擎用例覆盖固定 seed 重放、不同 seed 的牌库顺序变化、救援兔路线（通常召唤、超量/连接结果、结束阶段）、提示类型不匹配、错误资产哈希及缺脚本等边界。默认 workspace 测试会跳过它，复验需显式传 --ignored。

## 2. 部署包与数据检查

| 检查 | 本轮结果 |
|---|---|
| dist/ygo-local/ygo.cmd engine doctor | exit 0；assets_ok=true、abi_ok=true、issues=[]、ready=true；doctor 尚未执行 smoke，故 smoke_ok=null |
| catalog status | 13,665 张；snapshot ID catalog-1b0564fd61eec4730828fea1d48391aa1598bca3157c255454a8dcf487485d6d；本机 CDB SHA-256 c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225 |
| banlist status | 203 项；有效日期 2026-10-01；snapshot ID banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783 |
| Rabbit YDK/deck validate | legal=true；无违规；报告包含 catalog 与 banlist snapshot ID |
| engine smoke | 通过；3 条完整且可重放线路，368 节点，约 27.2 秒，终止原因 time_budget |

引擎构建 manifest 声明 x64、API 11.0 和 ABI probe 通过；运行 DLL 哈希匹配 manifest。dist 包中的 ygo.exe 与 worker 哈希也与 build-hashes.json 一致。注意 Project Ignis 安装根目录中已有的 stock ocgcore.dll 是 x86；运行时必须使用本地构建并部署的 x64 DLL。

## 3. Combo 搜索与独立重放

本轮从默认配置重新分析 tests/fixtures/rabbit.request.json，之后用 combo replay 对生成报告再执行独立验证。

| 指标 | 本轮结果 |
|---|---:|
| 完整前缀节点 | 721 |
| 引擎调用（含重放） | 726 |
| 已完成候选 | 69 |
| 输出且独立重放通过 | 5 |
| 总耗时 | 约 54,426 ms |
| 重放耗时 | 364 ms |
| 终止原因 | time_budget |

五条返回线路的 replay_verified 均为 true，verification 为 engine_verified。最高排名的兔子→通常怪兽→希望皇霍普路线得分 19.5；该分数类型为 heuristic，衡量当前 rabbit-v1 规则覆盖下的终场偏好，不是胜率或全局最优证明。

先前部署验收记录的一次默认预算分析为 723 个节点、728 次引擎调用、69 条完成线路和 5 条输出线路。721 与 723 的微小差别来自 60 秒墙钟截止附近的执行量变化。固定 512 node budget 的两次历史运行得到相同节点数和线路 ID；这比墙钟时限更适合确定性搜索回归。

## 4. 复验命令

从仓库根目录运行：

    cargo fmt --all -- --check
    cargo clippy --workspace --all-targets --offline -- -D warnings
    cargo test --workspace --offline
    cargo test -p ygo-engine-adapter --test live_engine --offline -- --ignored --nocapture

Python 全量测试需要安装项目 test extra。CLI 安装、运行和数据要求见 DEPLOYMENT.md；本地资产被忽略或具有许可/体积限制，不应把它们当成可由干净 Git checkout 自动取得的测试依赖。

## 5. 验证边界

- CI workflow 已存在，但这里记录的是本机运行证据；不宣称远程 CI 成功。
- 默认搜索可能因 time_budget 提前结束，只对已完成候选承诺报告和重放结果。
- Beam pruning 可能丢弃最终看来更优的前缀；预算内排名不是穷举最优。
- 未知决策停止对应分支；未覆盖信息保留 raw 并降级 partial。特定卡组投入前须增补消息、提示、效果及评分回归。
- combo-result JSON Schema 部分嵌套结构较宽松，Rust 反序列化、报告一致性检查和真实重放提供更严格约束；schema 负例仍是后续任务。
