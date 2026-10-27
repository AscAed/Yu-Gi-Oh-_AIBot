# Curry V2精确来源恢复：续接断点

## 本批结果

本批已完成版本化V2恢复器、V1兼容、181角色合成成功与文档变化后verify测试、全套Python及独立审阅。唯一一次真实纯Python恢复失败并按计划停止；固定V2输出不得再次运行或覆盖。没有执行runner、worker、FFI、doctor或实时资产扫描，新增原生调用为0。

开始时只读基线：源码身份`b004f9a37769ccdd0c2ed8d859d8639df416b4ab884d031d7a2eca8b2cc4ceca`、583项；Rust/Cargo 151项未变；V1失败报告SHA256 `bf85a81f7d6a204e4a960b2ffb8449e2f1a17d857ca5fcf7e5e2303f5285270d`，V1 delivery SHA256 `154d77cb4c8790cd971e19dbd17dcc8a4417df1e0f460747948e306706328e2e`。V5 delivery SHA256 `3c689f9ae6860da3b42a0ea4f6f0e5e3b100fdc2c548f91f2e288268bd071278`。恢复时工具工作区身份为`b13fda5a05a93f341580f7449232387b174745298610caa2b63eb8b31790932b`，585项；该身份记录在失败报告的工具元数据中，区别于V5历史源码身份及文档后最终源码身份。

唯一实际命令：

```powershell
py -B -m ygo_eval.research recover-curry-ledger-handoff `
  --report-version 2 `
  --baseline-dir data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26 `
  --output data/runtime/p1-curry-ledger-handoff-recovery-v2-offline-2026-10-26/recovery-report.json
```

进程退出2。报告`data/runtime/p1-curry-ledger-handoff-recovery-v2-offline-2026-10-26/recovery-report.json` SHA256 `7496f981438bdca15f768eb38c6402cf15cc8ff88401d661fae7ee554dc476d6`，47,789字节，通过当前Python合同、V2 schema和恢复目录内7成员工具归档中的schema。状态`failed`、`valid=false`，首个失败检查点`scope_ledger_semantics`，稳定诊断`recovery_success_input_set_incomplete`。之前`previous_recovery_failed_source`、V5来源链、历史来源、冻结输入与父链、保存进程证据均通过；输入稳定性与成功发布流程未执行。归档工具schema SHA256 `cd30ad9d99e8f84552cf8166c351d625b0bbc207f43ba7e92ef9f8b9d912a385`。

报告保留181条输入角色，来源组为V5 audit 164、恢复锚点5、V3预留100、前次恢复6、Curry scope blob 6。问题在固定角色名不符：已认证V3材料提供`v3_source_workspace_identity`，当前V2 `V3_INPUT_ROLE_ALLOWLIST`构造的完整期望集使用`v3_source_confirmation_summary`。因此`_validate_input_rows(..., success=True)`拒绝成功集合；这不是外部输入篡改的证据，也不能把消费统计默认成0。报告`checks.scope_ledger_semantics=failed`，其余尚未执行的后续检查保持`not_run`。V2失败统计中的scope consumed/completed/unknown、认证含scope总数、reservation ID及planning total均为null。

原始CLI输出在写入目标报告之前先保存到target：stdout 77字节、SHA256 `552d1bcfa2ba3ae2837fae98bc70105acb8c5ff3f79622bf92883dbfca54ba27`；stderr 0字节、SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。stdout为稳定拒绝说明`recovery_success_input_set_incomplete`。恢复后只读锚点检查通过：原scope账本仍为SHA256 `7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`；stage2输入`b144701eeceafd8c8d7e827c7e6823213e401614f46488a9e3564c2735f604b8`、prepared `7f94f982f89ca1c2b720f32250f8e4f9451ec0eb99ba5a4afcec7dd7fc23c5ee`未变；stage2收据及V5正式`audit-report.json`仍缺失。V1失败件与delivery、V5 delivery锚点不变。

测试证据位于忽略目录`target/curry-ledger-handoff-recovery-v2-tests/`：33项聚焦回归通过；显式枚举80个顶层Python测试文件的全套结果为655 passed、9 skipped、166 subtests passed，1,311.87秒。完整日志`pytest-full.log` SHA256 `726d266f0124d81fba1bdb491ef8a9ab730e5e4db8f26c200e48b1f4b4f8ec42`；文件清单`top-level-python-test-files.txt` SHA256 `8315ab8b3b2270462ade7c7ea64c709a122c77cbfd29cd81d0e3f65505a40f0d`。`-ra`跳过原因：Windows目录符号链接能力2项；v3/v4报告、引擎资产、本地快照/报告、实际v2、完整策略、独立赛事资产缺失共7项。Rust/Cargo在本批无修改，引用已认证151项源清单及此前fmt/Clippy、workspace 380 passed/37 ignored结果。

独立只读审阅通过，未发现阻断进入全套Python测试的问题。原始V5退出码2的内部原因仍未认证；本批失败只说明恢复器固定来源角色集不匹配。全程`native_calls=0`、`runner_process_calls=0`、`execution_ready=false`；`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均false。

## 续接限制与后续入口

- 保留V1失败报告、V5原材料及本V2失败报告原字节。固定V2输出目录`data/runtime/p1-curry-ledger-handoff-recovery-v2-offline-2026-10-26/`不可重跑、覆盖或重命名续跑；此失败报告不做verify-only。
- 不把V2报告中null的scope统计改写成0。此前认证历史子集32、政策风险预留7、规划基数39沿用既有证据；本批未发布33/40。旧confirmation消费和全部历史实际累计继续为null。
- 下一批先通过红测让V3输入期望集合精确反映认证V3清单中的`v3_source_workspace_identity`，再验证成功/失败schema及181角色合同。新代码只能在新的独立恢复报告版本/输出根中进行新的单次真实审计；不得改写本V2失败报告，也不得宣称修复后自动认证V5历史执行。
- 核查新增V2运行时目录与文档后的源码清单时记录访问失败；不得清理或修改旧ACL受限材料。

文档后最终源码归档和delivery记录位于本恢复目录`final-build/`，稍后由本批执行者生成；本handoff只依赖外部delivery记录，不嵌入自身哈希。未提交或推送Git，部署与active资产未切换。
