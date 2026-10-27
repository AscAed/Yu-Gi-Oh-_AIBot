# Curry V5已存证据恢复交接（2026-10-26）

## 当前断点

本批的离线实现、合成验收、全套Python测试及独立审阅完成。对V5保存证据执行的唯一一次纯Python恢复，生成合法失败报告后在第一个来源检查点停止：

- 状态：`failed`，`valid=false`
- 首个检查点：`v5_delivery_and_archives`
- 稳定错误码：`recovery_v5_source_delta_invalid`
- 报告：`data/runtime/p1-curry-ledger-handoff-recovery-offline-2026-10-26/recovery-report.json`
- 报告SHA256：`bf85a81f7d6a204e4a960b2ffb8449e2f1a17d857ca5fcf7e5e2303f5285270d`
- 报告大小：3,891字节；Python合同和`curry-ledger-handoff-recovery-v1` JSON Schema通过。
- 后续检查均为`not_run`，`inputs=[]`；没有运行原scope账本解析、历史来源重验、保存进程证据复验或最终稳定性检查。
- 本批`native_calls=0`、`runner_process_calls=0`、worker=0、FFI=0。失败后未运行`--verify-only`。

按用户约束这是一次性真实恢复尝试。**不得在固定V5证据上重跑恢复、verify-only、V5审计或旧runner；不得覆盖报告或换路径再次试验。**要继续必须先制定一个独立、版本化的新工作包，并明确不把新检查倒填为本次恢复的成功。

## 本批工作与测试

修复了报告发布诊断边界，抽取可复用的只读来源重建/进程证据校验，增加独立发布诊断合同，并实现V5保存材料的纯Python恢复入口。账本解析器对原scope的七行记录、检查点、用途、请求身份、六个blob、事件及结果哈希使用真实解析逻辑。公共CLI合成路径验证了成功/失败发布、恢复和verify-only行为；该合成成功仅证明工具路径，不提升真实来源资格。

最终聚焦集合：48 passed，70.85秒。显式列出的79个顶层Python测试文件：651 passed、9 skipped、166 subtests passed，1,276.76秒；命令为`py -B -m pytest -p no:cacheprovider -q -ra <target/curry-ledger-handoff-recovery-tests/top-level-tests-final.txt>`。完整日志在`target/curry-ledger-handoff-recovery-tests/pytest-full-final2.log`。9项跳过为：两个Windows目录符号链接不可用；v3/v4报告、本地引擎资产、快照/本地报告、实际v2报告、完整策略报告及独立2026赛事配置为opt-in或材料未提供。独立二次审阅通过。Rust/Cargo本批未修改，引用既有fmt、Clippy及workspace 380通过/37忽略结果；本批未重跑Cargo。

审计时工作区身份：`d2307e164d2a949841f79a90715e12108b4c17b24be1275b37ea6a4700f4ddcf`，582项。冻结工具包身份：`9b29faec4ac18ba8cdb718a7cba5a5efe637759a98f027044954baf5f2a02078`，六个成员；ZIP SHA256 `a1c04170b571eef44c6379036ea0824c02cdd6c776488729c0aa165a8ba4bebb`，清单SHA256 `f078d9d3fc781a9b3577873f5bf67b0bfbd493596ead1a9b5fa5a22497491f1b`。审计时包另存于`target/curry-ledger-handoff-recovery-tests/audit-time-tool-freeze/`。

## 单次命令及操作记录

命令：

```text
py -B -m ygo_eval.research recover-curry-ledger-handoff --baseline-dir data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26 --output data/runtime/p1-curry-ledger-handoff-recovery-offline-2026-10-26/recovery-report.json
```

运行前纯读取检查确认固定V5 delivery SHA256为`3c689f9ae6860da3b42a0ea4f6f0e5e3b100fdc2c548f91f2e288268bd071278`、固定恢复目录不存在、stage 2收据不存在、原账本为`7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`。固定输入和prepared SHA256分别为`b144701eeceafd8c8d7e827c7e6823213e401614f46488a9e3564c2735f604b8`和`7f94f982f89ca1c2b720f32250f8e4f9451ec0eb99ba5a4afcec7dd7fc23c5ee`。V5正式`audit-report.json`在执行前不存在，执行后仍不存在。

PowerShell侧车碰撞检查表达式存在语法错误，shell继续启动了上述命令。真实恢复代码通过`mkdir(exist_ok=False)`独占创建正式输出目录，原本应受保护的固定目录在启动前另行被确认不存在。命令退出2。stdout SHA256 `9f0037a457370fe9c75b5f566d250d24d71b5e643f54c0fc91db92fc1be82f15`（72字节）；stderr为空，SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；退出记录为`target/curry-ledger-handoff-recovery-tests/real-recovery-exit.json`。CLI显示`recover-curry-ledger-handoff refused: recovery_v5_source_delta_invalid`。该shell防护错误是操作记录，不是恢复器失败报告中的来源诊断，也不推断V5历史异常。

真实失败报告只读解析并通过schema。它记录所有scope认证统计为null，预留政策7但预留ID及规划总数未发布。正式恢复目录当前含失败报告、六成员工具ZIP和清单。没有独立raw Python异常材料，因为本次失败由恢复器稳定错误码报告。

## 账务、历史与资格边界

- 已认证历史子集32次、未知0，政策风险预留7次、此前规划基数39：沿用既有证据，不由本批重新认证。
- 本次恢复未过第一检查门禁，不能据此重新发布原scope消费1、认证子集33或规划40；失败报告中的对应字段为`null`。
- 旧confirmation实际消费与全部历史实际累计均继续为`null`。
- 原scope历史上stage 1消费/完成1、未知0及stage 2收据缺失沿用之前已记记录；本批失败报告未重新认证该统计。
- V5历史外层命令退出2的内部异常仍未认证；V5正式审计报告仍不存在。不得将本次`recovery_v5_source_delta_invalid`倒推为V5当时的具体异常。
- 四项资格`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`保持false。
- 原账本、stage 2输入、prepared及V5 delivery锚点在本次尝试后只读哈希一致；stage 2 receipt仍缺失。

## 收尾及后续边界

本批不切换普通部署或active资产，不创建scope、窗口或收费账本，不提交/推送Git。工具归档和失败报告保留原字节。

文档定稿后仅生成独立final-build源码归档、清单和交付记录；最终证据体积清单最后写入，排除其自身，访问失败以相对路径记录。若后续要解决`recovery_v5_source_delta_invalid`，先基于已保存失败报告规划新的合同/输出，不在此固定目录补写或重试。
