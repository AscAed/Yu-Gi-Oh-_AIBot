# 天玑 placement confirmation 六阶段验真断点（2026-10-23）

## 结果

本批的离线实现、合同、测试和收费前准备已通过；原生六阶段目标未通过。唯一一次正常 runner 进程调用在stage 1报告`runner_timeout`，没有stage收据或账本收费请求。异常stdout看起来是stage 1 `--preflight-only`响应（215字节、`preflight_passed=true`、`native_calls=0`）；stderr为空。该异常原因尚未确定，因此按计划停止，不再尝试同一scope。

固定批次为`tenki-placement-confirmation-v1`，目录`data/runtime/p1-tenki-placement-confirmation-native-2026-10-22`，上限6次、7200秒，worker超时30秒。唯一窗口起点保存在`window-start.json`，`started_at=1792691169`。`--prepare-only`通过，冻结context为`0f55ccf433f7d0e90421cf40850e64de8c02614404ec8d6028e767dfbbbbb138`，stage 1请求SHA256为`fac2455f2b2876bc9f28666252bdc8326dcd16cf95c63335230f2d49eac9a134`。不得重建窗口、请求、seal或账本，也不得将其余5槽用于后续执行。

## 账本、诊断和消费

本批`research/calls.jsonl`只有header和零消费checkpoint，694字节，SHA256 `5daf512e4381803663df466575f4706f083843629ae660caf8c557ebecc8bc21`；没有`begin`记录或收费请求。只读stats报告消费0、完成0、未知0。`stage-1-report.json`和`summary.json`将批次标为失败，诊断`runner_timeout`；`stage-2`至`stage-6`没有运行。随后`--verify-only`只读返回`valid=false`、`incomplete_stage_receipts`、新增调用0、消费0、未知0。

正常进程诊断位于`research/process-diagnostics/normal-2fcaa6d8512249329af5efe8188a3442.json`。它绑定stdout文件SHA256 `b91e902f0319a3abfbb90ba152d577dc8e1ac6b6b4ea7714383ee06dce57fe60`（215字节）及stderr SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`（0字节）。不要将该输出解读为stage 1成功，也不要假设worker请求已发出；收费状态以只读账本为准。

七份更早的账本按9/8/1/4/2/2/0次重核为26次、未知0，哈希均匹配；本批未改写它们。早期天玑prompt-probe scope的2/6和placement scope的0/6继续各自封存，不向本批或未来scope转移。新confirmation账本实际0/6，但窗口已经建立并参与了准备及失败进程，不续用其剩余槽位。累计报告为旧26次加本批实际0次，即26次、未知0。

## 离线实现与验证

本批新增了独立confirmation入口/报告合同、新的固定`batch_kind`和私有scope配置、只读`CallJournal::inspect_existing`视图，以及预检/统计/verify-only零写入路径。修复后，stage 1预检响应与冻结普通资产identity正确绑定；缺少收费账本时只有尚未尝试收费才报告0，正常runner已尝试后若无法确定账本则保留未知。

- 聚焦Python测试11项通过；之后Python全套`py -m unittest discover -s tests -v`为276项通过、7项跳过，139.061秒。七项均为明确opt-in的资产/快照/版本报告案例，逐项原因见忽略目录的Python日志和跳过记录。
- Rust `cargo fmt --all -- --check`、workspace全目标Clippy（offline/locked，`-D warnings`）、workspace默认串行测试及adapter examples均通过；汇总为288通过/36忽略、examples 21通过。日志为本批根目录`rust-fmt.log`、`rust-clippy.log`、`rust-tests.log`和`rust-examples.log`。这些Rust检查在最后两处Python修复后未受Rust源代码变化影响。
- 未运行真实资产opt-in、doctor、48手评估或其他原生实验。

原生时点HEAD为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，源码身份`554891b51a1316ae68b145559930e95264e64470da6e1240969ae41ed96df133`，510份文件。构建记录identity为`97bb1c490a95f079210fc5cd343003af4b35e793757be498b2e4a3ce95cc0f63`，状态`recorded`，但`reproducible_build_proven=false`。原生CLI、worker、runner哈希分别为`50d377576e27df55dff918b2a0fefd14e8c5ef227cb389218e9ef5f69350c3c3`、`39610bbf4dd32fc3dbc29801463db485f2e4d42dfb3533f18739d29e542537c9`、`5b951a1d93384c9ce2d8c78b943de729ee67670b8444d010699aba0471db5224`。源码归档SHA256 `a4c85682032597f1fe512a8c59eea498c8426b7f25e9f61b736f57051da55801`，文件清单SHA256 `48d4477b91d6bbf70d54722f4849378599706e7d52dcd036c634e5a2e3a6f3fe`。

普通和赛事身份分别为`981d4352dcc83479ad96b9ad6bbc4d3961d8d24b5cb257ed8fb9f491d3647d80`和`5c456f1b351c4fdf1f05eebc9c869cfd558382ea582e4dbb3618b8f45849bd0f`。原生时点构建/资产身份仍绑定原构建记录；文档收尾后的源码、归档、文件清单和独立`final-build`记录见忽略目录`data/runtime/p1-tenki-placement-confirmation-native-2026-10-22/final-build/delivery.json`，不替代或重签原生证据。

## 下一次恢复边界

此批已按stop gate暂停。未来若要重新验证，先单独诊断“normal模式为何超时且输出预检形状”，补充针对该路径的回归和独立审阅，再制定并明确授权新的scope、窗口、账本和请求。不要再次调用本批normal模式，不要使用本scope剩余5槽，不要恢复任何早期2/6或0/6窗口。保留现有stdout/stderr、账本和失败报告原字节。

成功资格仍全部为false：`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`。没有固定区域/Opcode 13响应接受或重放的新证据，不切换普通dist/active资产，不提交或推送Git。
