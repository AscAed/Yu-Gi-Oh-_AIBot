# Curry V5交付与单次只读验收断点

## 当前结论

V5代码、schema、固定离线打包器、合成公共CLI回归和独立只读审阅已完成。显式枚举77个顶层Python测试文件后，全套为637 passed、9 skipped、166 subtests passed，用时1,146.60秒。独立审阅没有发现材料来源、164角色绑定、四项打包布局或V1–V4兼容方面的阻断。Rust/Cargo选集151项与V4最终源码清单一致，本轮未改Rust/Cargo，引用既有fmt、Clippy和workspace 380 passed/37 ignored验证。

唯一一次固定V5审计已启动保存输入专用runner一次。runner退出码0，输出显示父收据有效、stage 2公开派生有效、只读资产检查通过、stage 2收据仍缺失，账本为消费1、完成1、未知0、额度7。外层Python命令随后以退出码2拒绝，输出为`audit-curry-ledger-handoff refused: fixed source, runner, or output check failed`；正式`audit-report.json`没有写出。由于CLI隐藏了内部异常，准确Python失败检查点未能认证，本断点不猜测该检查点，也不把单独的runner成功解释成整批审计成功。

本批新增原生调用为0；没有worker请求、FFI、doctor、normal执行，没有创建新scope、窗口或收费账本。V5审计不得重跑，固定输出目录不得覆盖或换名续跑。后续先设计离线报告恢复/诊断路径；若要再次执行saved-input runner，必须另立版本、输出目录和授权预算。

## 冻结基线和产物

计划开始时源码身份为`7c94c46b431c496011de4a4edf5f1761660f21b0e9599794f4747e81310ca236`、569项。加入本批V5代码和测试后，native audit runner的源码快照为`c37902c3e949fe6759df7ec0a6c30a54fa08dc3099cd638d5cb5833bbab5515f`、576项，HEAD为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`。

正式V5根为`data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26/`。打包时根目录恰好有`native-artifacts/`、`build-record.json`、`source-native.zip`、`source-native-file-list.json`四项，固定布局门禁通过。打包报告`native_calls=0`且`audit_runner_started=false`。构建使用`cargo build --offline --locked -p ygo-engine-adapter --example curry-option-validation --target-dir <隔离target>`，`CARGO_TARGET_DIR`与显式target-dir一致。

| 材料 | SHA256 / 身份 |
|---|---|
| V4失败报告 | `02f69485390c98cec677da83d3e9df3df70ffb9f238d38d3e8acf861968bad05` |
| V4最终交付 | `bfc4f04042aad0b07df53d71e3496611193d782c2d96e7f55cf5e887707ace0f` |
| V5 runner | `2ef1a214fa16e9f4a3ba666ec614165a016eadc739a4eadcdc2c9e4cdd0338af` |
| V5 build-record身份 | `e67bd1a7d18d69777e7af29b425dfc84dc38a37fc594433ad7be17b87dae81e5` |
| V5 build-record文件 | `b6f1e120e6eb3057f421f8747992865e387767e55f7af7063f09d6cd3a292951` |
| V5源码ZIP | `ce194380f6d2bb6c587e96009382cac6d9ed03f24af4fe660873da4b5d3480fa` |
| V5源码文件清单 | `c776edf40bcab67da85e011770d9c3ffdb27806c9aca8f72ed39ccc49df512f6` |

## 测试及审阅证据

- 完整Python测试清单和`-ra`日志：`target/curry-ledger-handoff-v5-tests/top-level-test-files.txt`、`target/curry-ledger-handoff-v5-tests/pytest-all.log`。日志SHA256为`217454fe4889674463afb3b8eb1039d3e9c70c63e30a4896b49f621e4f783239`。9个跳过项分别是两个Windows目录符号链接能力测试、v3/v4报告opt-in、本机引擎资产opt-in、本地快照/真实v2报告opt-in、完整策略报告opt-in、独立2026赛事配置缺失。
- V5、schema、打包和V1–V4兼容聚焦集：82 passed；独立V5公共CLI E2E：1 passed，用时72.83秒。聚焦日志保存在`target/curry-ledger-handoff-v5-tests/`。
- 独立审阅结论：无材料发现；V4来源子项由固定交付/构建记录导出，164输入角色、100条V3来源、V5根路径传播、原始进程侧车和四项打包门禁均有验证。审阅只读，没有启动真实runner。
- Rust/Cargo：151项选集与V4最终文件清单逐项一致，变化0。本轮不重跑Rust；引用workspace 380 passed、37 ignored及既有fmt/Clippy验证。

## 唯一真实审计尝试

固定命令以`--report-version 5`、V5正式root、已认证的verification baseline和V5隔离runner执行。执行前再次计算并匹配冻结输入与prepared：

```text
stage-2-input.json  b144701eeceafd8c8d7e827c7e6823213e401614f46488a9e3564c2735f604b8
prepared.json       7f94f982f89ca1c2b720f32250f8e4f9451ec0eb99ba5a4afcec7dd7fc23c5ee
```

保存输入runner只读输出：`saved_input_audit_passed=true`、`parent_receipt_valid=true`、`request_derivation_valid=true`、`stage_receipt_absent=true`、`native_calls=0`；账本字段为`consumed=1, completed=1, unknown=0, limit=7, reserved=0, abandoned=0`。追踪阶段为`input_validation`、`parent_request_check`、`saved_input_asset_scan`、`ledger_check`的start/end共8行；资产扫描阶段耗时149,918,244,100 ns。

原始输出侧车位于`data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26/process-diagnostics/`：

- metadata `audit_saved_input_only-dbe7dea1aa144582894cafdbb48872d2.json`：SHA256 `b0cdb6f20dc55fc5dac128a1cea67ac07ae3481c4f74d78b6eced03548c72f81`。
- stdout：SHA256 `36a312ae0b0ef05b8303243cb5414835d3e600abcc3e81feb6a970dd02ee89eb`，422字节。
- stderr：SHA256 `afca76668db499825cb98913923187ccf206ad8e7cd3da2fa382ce46726750af`，454字节。

外层命令日志在`target/curry-ledger-handoff-v5-tests/audit-command.log`，SHA256 `13d58e319136732edd70edfa44d11d3d3efb4986abe594b25d7efbf1ce977efa`。独立观察记录`target/curry-ledger-handoff-v5-tests/real-audit-attempt-observation.json` SHA256为`386aba20924ced9d7f686c6691b7d7e7219fd0922588cc511c1ebd8969e377e8`。由于命令退出2且没有`audit-report.json`，这两者是失败观察，不是V5合同报告。

原scope账本SHA256仍为`7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`；stage 2收据缺失。上述runner输出重核的是既有账本，不产生新消费。认证历史基数32、政策预留7、规划基数39沿用V3预留证据；旧confirmation实际消费和全部历史实际累计继续为`null`。本批不得将其标为33次认证或规划40，因为V5报告未发布。

## 后续断点

1. 保留V1–V4材料、V5四项package、V5进程侧车和本次命令日志的原始字节。formal root当前增加了`process-diagnostics/`，不能再通过审计前“四项精确布局”门禁。
2. 不重跑V5 CLI或保存输入runner，不补写/覆盖`audit-report.json`，也不从runner输出推断Python隐藏的失败检查点。
3. 下一任务先做离线错误路径分析，修正CLI能保存合法失败报告、并揭示稳定错误码的缺陷；通过合成失败用例后，如需真实重审，另建报告版本与固定目录，由用户/计划单独授权。
4. 四项资格`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`继续为false。不切换部署/active资产，不提交或推送Git。


## 最终文档后归档

本断点已定稿。文档后源码归档、文件清单和结论记录固定写入data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26/final-build/；权威索引为delivery.json。最终证据体积清单写入V5根目录vidence-size.json，不计入其自身。
