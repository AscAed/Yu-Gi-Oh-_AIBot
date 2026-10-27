# Curry 新scope七阶段验真断点

## 本批状态

本批固定使用 `curry-option-confirmation-v1`、目录 `data/runtime/p1-curry-option-confirmation-native-2026-10-24`、最多7次请求和7200秒窗口。已完成离线实现、回归、独立审阅、隔离构建、基线核验及收费前 `prepare-only`。窗口起点为 `1792787058`。`prepared.json` 报告 `prepared=true`、`execution_ready=true`、`native_calls=0`、`planned_calls=7`。

正常编排命令返回：

```text
native-curry-option-confirmation refused: frozen input, build, ledger, or output check failed
```

没有stage收据、normal runner进程诊断或 `research/calls.jsonl`。未运行 `doctor`，未切换部署或active资产。随后 `--verify-only` 返回 `valid=false`、`native_calls=0`、`diagnostic=incomplete_saved_stage_files`；新增消费、累计消费及未知统计均为 `null`。失败summary单独保存并通过schema验证，标记 `successful=false` 和诊断 `normal_cli_refused_without_authenticated_stage_receipt`；该summary是根据保存状态制作的收尾报告，不是runner生成的stage证据。

因为调用统计未知，不能将累计写为32次确定值，也不能把新消费填写为0。9份历史账本独立复核仍是32次、未知0；本批scope以及旧Curry七槽均不得复用或续开。本批新增正常阶段已停止，不再重试。

## 实现与验证

- Python新增固定 `native-curry-option-confirmation` 入口、独立报告合同和新scope配置；旧 `curry-option-validation-v1` 接口保留。
- Rust runner接受固定 `curry-option-confirmation-v1` 模式并使用独立scope/账本/报告类型。
- verify-only要求prepared状态和执行就绪标志都为真；保存源码ZIP、文件清单哈希须与manifest输入角色一致。
- Python完整套件398项、7项跳过、0失败；Rust格式、全目标Clippy、workspace串行测试和examples测试通过。聚焦测试51项通过。
- 最新基线delivery及audit锚点匹配；9份历史账本32次、未知0；545项保护输入通过。
- 隔离构建源码身份 `316443a5aa270488fb5ab88f463174a9e6c3f66cc9ddc1702c1ffe96f0525408`，501文件；构建记录SHA256 `a576968b9cdcc69fce1791a262b6b57d4e58e81c2f4ab77918f2ad35d15f718b`，reproducibility未证明。

Normal拒绝后做过安全只读诊断：当前源码与manifest一致；21项冻结输入哈希一致；delivery锚点匹配。**normal拒绝的精确内层错误仍未知**。不要猜测为提示、资产或worker错误。下一任务如需继续，应先单独定位该预扣费拒绝路径，完成合成失败回归后再制定全新scope和预算。

## 关键证据

忽略证据目录：`data/runtime/p1-curry-option-confirmation-native-2026-10-24/`

- `build-record.json`：原生时点隔离CLI、runner、worker构建关联。
- `native-artifacts/`：上述隔离产物副本。
- `source-native.zip`、`source-native-file-list.json`：原生时点源码及清单。
- `window-start.json`：固定新窗口，禁止重置。
- `research/manifest.json`、`prepared.json`及 `stage-1-input*.json`：冻结输入和成功零调用预检。
- `process-diagnostics/`：预检原始stdout/stderr和元数据。
- `research/verification.json`、`summary.json`：verify-only不完整结果和收尾失败摘要。
- `final-build/`：文档收尾后的单独构建、源码归档和文件清单。
- `acceptance.json`：最终交付摘要。

四项资格 `proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`仍为false。发行依据未知。普通部署、active资产和Git提交状态保持原样。
