# 天玑历史锚点修复与零调用预检断点（2026-10-22）

## 当前状态

本批离线诊断和真实冻结stage 1只读预检已通过，原生验真仍未通过。修复把Rust中的错误旧stage 1常量从66位更正为与实际冻结字节及Python锚点一致的64位SHA256：

```text
c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7606dbce5ceaf76
```

历史源码归档里的错误值、原native `runner_failed`结论以及原报告均保留。历史stderr没有保存；本批确认静态因果关系，不声称恢复了stderr或重放了历史失败。

截至预检源码身份为`7e3471035380cf1043a84b43a5b94f08d3f322c53919cb48814209bb6dac81e6`，458份源码/未忽略文件，HEAD `8a6b2f6762131aebea6d8c0f5f61363d573f1b36`。本次工作区未提交状态完整保留。文档收尾后的身份、完整源码归档、文件清单和隔离构建在忽略目录`data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22/final-build/delivery.json`；该最终构建不是原生时点产物，也不转移任何运行资格。

## 零调用预检结果

运行器example新增严格的`--preflight-only`模式，仅接受固定stage 1。它检查冻结请求、stage输入seal、历史来源和资产身份，随后在`TenkiPlacementBatch::open`之前返回；此路径不创建或打开收费账本、不调用worker、FFI或普通收费模式，也不检查旧窗口的剩余调用时间。

实际运行入口：

```text
python -m ygo_eval.research audit-tenki-placement-preflight
  --baseline-dir data/runtime/p1-tenki-probe-native-2026-10-21
  --experiment-dir data/runtime/p1-tenki-placement-native-2026-10-22
  --runner data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22/native-artifacts/tenki-placement-probe.exe
  --build-record data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22/build-record.json
  --output data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22/preflight-report.json
```

九项检查全部通过，资产身份匹配，报告通过运行时不变量和`tenki-placement-diagnostics-v1` JSON Schema。报告绑定审计源码`7e347103…6dac81e6`、构建身份`b79668df…09f863fe`及runner SHA `f8cbeb4f…1186d56`；输入468项，证据体积155,012,220字节，执行耗时698.659秒。专用进程退出码0，stdout 215字节、stderr 0字节；原始字节及SHA保存在`process-diagnostics/`。报告固定`native_calls=0`、`execution_ready=false`，四项证明/完整性/概率资格均false。报告不含个人绝对路径。

初次完整预检曾在保存成功报告前发现重复的`(role,path)`证据记录。修正为仅折叠规范JSON字节完全相同的记录后，独立审阅又指出Python `1 == True == 1.0`可能错误合并类型冲突；现已使用规范JSON比较并为`int/bool`与`int/float`增加负例。之前的runner、构建和报告移动到本批`verification/*-before-strict-dedupe`，作为历史保留，不覆盖；最终报告由严格比较版本重新生成。

## 账本、窗口与资产保护

首次审计前的不可变快照包含六份历史账本、placement账本和窗口起点共8项。预检后逐字节/哈希复核8/8不变；六份历史消费序列仍为9/8/1/4/2/2，累计26、未知0；placement账本仍只有header及`consumed=0`起点检查点，新增消费0、未知0；窗口起点未重建、未延期。366项保护清单仍只有既定worker迁移差异：其余365项匹配，目标worker迁移值为`4f2b…7680`，当前来源仍未知。

本批没有启动worker或doctor，没有运行普通runner、FFI、收费查询、六阶段编排，也没有创建窗口、scope或收费账本。原scope剩余4槽继续封存，不能因为离线预检通过而恢复使用。原native stage 1 runner失败和六阶段任务未通过结论保持有效；区域18、区域选择、opcode13响应分支和独立重放均未取得新证据。普通dist、active资产和原worker未切换。

## 验证

- 严格去重修复的聚焦Python测试12项通过，另有2个类型子用例通过；测试先验证了原实现的两个类型冲突失败。
- Python全套：257通过、7跳过、58个子用例通过，用时119.74秒。两个拒绝遍历的临时目录已明确排除；所有Python跳过及36个Rust ignored测试的名称/原因见忽略文件`verification/test-exclusions-final.json`。
- Rust源码未因本次Python修复而变化，引用此前同一隔离目标上的验证：格式检查、workspace全目标Clippy通过；workspace串行测试293通过/36忽略；adapter examples 23通过。命令日志在`verification/cargo-*-final.log`。
- 真实资产opt-in、worker、doctor和48手评估均未运行。
- 历史输入、输入seal、来源目录及保护文件扫描前后均未漂移；旧账本与placement窗口材料维持原字节。

## 下一断点

本批按计划暂停，不自动进入原生阶段。旧六阶段窗口已启动但从未收费；不可重置，不可重试，也不可使用剩余4槽。若之后继续验证区域选择或opcode 13，须先根据本次预检确定新scope、公开动作条件、请求派生及新预算，并取得新的明确授权；不得把`execution_ready=false`解释为可直接收费。

四项资格`proof_ready`、`complete_action_coverage`、`global_optimality`及`native_probability_verified`保持false。不切换部署，不提交或推送Git。
