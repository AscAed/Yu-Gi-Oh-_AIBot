# Curry v2清单驱动审计与零调用收尾断点

日期：2026-10-24

## 结果与状态

本轮修复并运行了Curry冻结输入恢复审计的v2路径。正式审计命令只执行一次，状态`passed`；新增原生调用为0。该批仍标为部分完成，因为计划要求的“完整九份合成账本贯穿公共审计入口成功路径”夹具没有实现。已通过的真实只读审计不能替代该测试验收项。

审计时源码身份为`62b0729c20381023f655fb08f47863f8150c6de8d713f273c39e6bf4d99b8c06`，508文件，HEAD `8a6b2f6762131aebea6d8c0f5f61363d573f1b36`。源码ZIP SHA256为`388406d46af755abdf02ce6a5aaf811868954831ba3149b35774974e3906b4c4`，认证文件清单SHA256为`f70b0f279644e6f8668572bccb967ed5b6985b1716726e9f764b6f316d1b8fb1`。审计产物位于忽略目录`data/runtime/p1-curry-v2-validation-2026-10-24/audit-source-snapshot/`。

正式只读审计报告：`data/runtime/p1-curry-input-recovery-v2-offline-2026-10-24/audit-report.json`，SHA256 `67c6332310aed1e77ccc9eb4394b700f4169837b198a50de20d422dc01da757b`，142,277字节，运行70.474482秒。v2模块校验器和JSON Schema校验通过；七个检查均通过，报告内历史账本为9份/32次/未知0，输入集SHA256 `45f4fef1f52a38e2a3cfb1c00dd57c403ad5c93de07de7af832a2d227d74fac9`。工具身份、事件检查点和保护哈希保存在报告内。

## 本轮交付

- 归档ZIP及文件清单先通过固定锚点与认证清单核验，再由清单读取两个Python成员的预期哈希逐项复算；去除了重复的源码成员哈希常量。归档成员身份及语义检查均通过。
- `base_request`与`candidate_case`继续使用canonical提取对象身份参与manifest/context比较。报告`inputs`记录实际容器文件字节哈希，容器保护另行复核。
- confirmation旧根与来源资产审计根明确区分，分别保护目录。
- 失败收尾保留主失败检查点，并把已采集的源码、文件、目录和账本缺失状态记录为一致、漂移、未采集或复核失败；后置阶段不因前置失败继续执行。
- CLI新增`--report-version {1,2}`，默认仍为v1；本批使用独立`curry-input-recovery-audit-v2`合同。旧v1合同及失败报告未改写。
- v2退出码从null开始：观察原件核验后记录其声称的1，归档代码核验后记录静态返回值2；`historical_exit_code_certified=false`，历史实际退出码未知。

独立审阅报告`data/runtime/p1-curry-v2-validation-2026-10-24/independent-review.json` SHA256 `5798ae30323ea3c0b209a2218cf7a2734aa78ac1a7aabe3fa949de52a2ef5a65`。审阅确认真实审计路径没有runner、worker、FFI、子进程或可写journal调用。

## 验证记录

- Curry审计和CLI dispatch聚焦测试：31通过。
- Python全套显式枚举顶层测试文件：419收集、412通过、7跳过、0失败，186.870秒。跳过项为v3报告、v4报告、本机引擎资产、快照/报告、实际v2报告、完整策略报告、独立2026赛事配置opt-in；逐项名称和原因在`data/runtime/p1-curry-v2-validation-2026-10-24/pytest-full-v2-final.log`。
- Rust/Cargo源码对上一轮认证清单逐项匹配157项，无差异。Rust/Cargo未修改，引用既有通过记录：fmt与Clippy通过、workspace 325通过/36忽略、adapter examples 42通过/1忽略。
- 既有失败报告`data/runtime/p1-curry-input-recovery-offline-2026-10-24/audit-report.json`仍为SHA256 `e6140724dc2048b82165a98306d970b4793cee6e4d9c46e487e98a49d6131e14`。本批不重写、不覆盖、不重跑旧失败审计。
- 旧confirmation ledger `data/runtime/p1-curry-option-confirmation-native-2026-10-24/research/calls.jsonl`仍不存在。尽管报告确认其前后缺失，scope的new/cumulative/unknown消费继续为null，七个槽位封存。
- 全局9份认证账本累计32次、未知0。本批`native_calls=0`，`execution_ready=false`。四项资格`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均保持false。

## 尚未完成的验收与续接

计划原要求构造完整合成来源树，并通过公共审计入口贯通九份合成历史账本、原始/归一化哈希、manifest/request/input/seal/prepared及最终成功报告。本轮没有实现这条完整成功夹具；独立审阅如实标记`full_public_success_flow_synthetic_fixture=not_implemented`。现有31项聚焦测试与本次真实只读报告通过，不能等价为这项合成验收。后续若补测，应使用全新的忽略测试目录与纯合成材料，调用真实的公开审计函数/CLI dispatch，并检查成功报告合同；不得调用runner、worker、FFI或可写账本，也不得改写本报告。

任何后续原生实验必须先解决旧confirmation消费不确定性门禁，再明确新scope及预算；不能复用七个封存槽位，也不能把缺失账本推断成零消费。本轮不切换部署、不提交或推送Git。ACL受限pytest临时目录保留原样；没有删除证据或更改权限。


文档定稿后的完整源码归档、文件清单、工具身份及验收保存在忽略目录`data/runtime/p1-curry-v2-validation-2026-10-24/final-delivery-after-docs-v2/`；同目录证据体积清单记录访问状态。较早的`final-delivery-after-docs/`仅作为文档补充前的中间快照保留。
