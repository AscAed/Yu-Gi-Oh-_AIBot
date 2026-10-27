# Curry V3材料兼容与零调用风险预留验收：完成交接

## 执行结论

本批按“V3精确适配并验收”完成；新增原生调用固定为0。真实来源只读审计和保存报告的只读verify均通过。未创建原生scope、窗口或收费账本；没有启动runner、worker、FFI或doctor。

| 项目 | 已核实结果 |
|---|---|
| V3报告 | `data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25/reservation.json`，SHA256 `14c13e4992673115c0211259dd7d035d968b9c36518c28b4a4ea159ff06ad43f`，36,306字节 |
| 真实来源检查 | 7/7 passed：`previous_failed_attempts`、`recovery_source_archives`、`latest_delivery_chain`、`real_v2_report`、`old_confirmation_scope`、`historical_ledgers`、`input_stability` |
| 只读verify | `valid=true`、退出码0、`native_calls=0`；报告前后字节和SHA256一致 |
| 预留 | policy `curry-unknown-reserve-seven-v1`，7次，ID `09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63` |
| 规划 | 已认证历史子集32 + 风险预留7 = 规划基数39；这不是实际消费或上界证明 |
| 实际记账 | 九份已认证账本、32次、未知0；旧confirmation新增/累计/未知消费均为`null`；全部历史实际累计为`null` |
| 旧槽位 | `curry-option-confirmation-v1`的7个槽仍封存，收费账本仍缺失 |

报告Schema验证通过，100项来源输入绑定齐全。confirmation保留64条角色行、43个物理路径及40个evidence别名。review字段分别来自原review与锚定acceptance；原review缺少的`public_cli_bypass_found`仍记为`null`。旧Windows绝对ledger path仅被解析并严格限定到固定scope下的`research/calls.jsonl`，未改写旧input。天玑placement ledger采用固定证据目录摘要、原acceptance和保护清单三方绑定；其他历史ledger仍按各自直接文件pin核验。

历史退出信息分层记录：原观察材料声称退出码1；冻结归档中的静态分支返回2；历史实际退出码仍未认证。失败来源和旧V1/V2报告保持原字节。

## 回归与独立审阅

聚焦测试19通过、1跳过、22子测试通过（242.08秒）。显式枚举62个顶层Python测试文件全套480通过、9跳过、152子测试通过，用时830.55秒。9项跳过：Windows配置不支持的两项目录符号链接，以及v3/v4报告、本机引擎资产、真实快照/报告、实际v2报告、完整策略报告和独立2026赛事配置的opt-in。日志和清单在`target/curry-consumption-reservation-v3-tests/`。

两位独立只读审阅均未发现阻断，没有真实程序副作用。审阅提出的可选测试增强是显式断言外部V2 acceptance不在旧V2 input index；现有合成成功路径已使用真实缺少该input行的数据形状，并独立绑定固定文件及SHA。

Rust/Cargo当前151个源码文件与V2最终源码归档逐项一致，未重跑Rust。过去159项是Rust源码加8项生成证据的历史验证选集，不再称为源码文件数量。

## 审计时和最终源码归档

正式来源审计前的源码冻结位于`target/curry-consumption-reservation-v3-tests/preaudit-freeze/`：身份`d76728dbd79ab42fcda13320c615683518fc70dd85a6219846244c6d02d0003d`、540项；ZIP SHA256 `dacf18ff0bb3ca0bee2a2ff79ddb2ee00b7ef5ead0184bee00f9632942ff1977`；清单SHA256 `f0dedaff625fac2c83edaaa8b4daa587165404f67cfe88f90b24facfdb40a96a`。相对V2最终536项源码归档新增四项：V3 schema、V3单元测试、V3公共E2E测试和E2E测试支持模块。审计报告内的八成员工具包身份为`69efac5351abf120f111e697ee9c596f864512201ae3ecf4060f3d6f185772b8`。

阶段测试后新增本断点，随后生成的文档后完整源码归档、file list、source identity、delivery acceptance及证据体积见同一忽略正式输出目录的`delivery/`。文档仅链接这个交付验收入口，避免源归档自引用。精确文件哈希和访问失败数记录在`delivery/evidence-size.json`。

完整测试日志、原始stdout/stderr、锚点预检、Rust口径核对和verify输出分别留在忽略目录`target/curry-consumption-reservation-v3-tests/`。正式报告根目录保存V3审计报告与其八成员工具归档；V1、V2正式失败件未更动。

## 当前边界和后续

- 7次是针对旧scope未认证消费的风险政策预留；历史实际总消费仍为`null`。
- 未来Curry原生实验必须引用成功预留ID，并另行使用新的scope与预算，不能重开旧7槽。
- 不切换普通部署或active资产，不提交或推送Git。
- `proof_ready`、`complete_action_coverage`、`global_optimality`和`native_probability_verified`均为false。

本批在此暂停；下一批从以上验收和冻结文件继续。
