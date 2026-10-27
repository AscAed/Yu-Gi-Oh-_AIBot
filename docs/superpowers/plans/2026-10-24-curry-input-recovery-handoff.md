# Curry 冻结输入恢复门禁断点

## 本批状态

本批已完成代码修复、合成回归、离线总检和独立只读审阅；真实冻结材料审计按计划只运行一次，随后因源码归档检查失败而暂停。**新增原生调用为0**，未创建或修改窗口、scope、收费账本；没有启动runner、worker、FFI或doctor，也没有运行真实normal。

当前Git HEAD为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`。真实审计启动前的工具身份为`c36aae0ef1ce981c3f2770520e8cfadc20991b04aea038e5337f07aca691a6ac`、506个源文件。审计报告记录acceptance、delivery和证据清单锚点通过；在`source_archives`阶段以`archived_refusal_source_hash_mismatch`失败。冻结输入、9份历史账本、旧材料保护与采集前后稳定性阶段均为`not_run`。不能据此判断是哪一个归档源码模块哈希不符，也不能断言归档ZIP损坏；不继续诊断、不重跑本次审计。

失败报告保存在忽略目录：

```text
data/runtime/p1-curry-input-recovery-offline-2026-10-24/audit-report.json
```

报告SHA256为`e6140724dc2048b82165a98306d970b4793cee6e4d9c46e487e98a49d6131e14`，并通过`curry-input-recovery-audit-v1`结构校验。失败报告的字段`archived_refusal_branch_return_code=2`来自报告初始化默认值；归档源码哈希断言失败后，后续解析未执行，故不能将2表述为本次核实结果。

该报告`native_calls=0`、`execution_ready=false`，runner、worker、FFI与可写账本标志均为false。报告中的历史消费字段为null，因为历史账本阶段未运行。此前独立只读核验得出的9份账本累计32次、未知0仍作为此前证据，不归因于本次审计。旧`curry-option-confirmation-v1`新增消费、累计消费和未知数仍为null；七个槽位继续封存。没有认证该scope为零消费，也没有改写旧normal观察、summary或历史退出码。

## 实施内容

- prepare、normal恢复及审计共用纯读取哈希计算：`base_request`和`candidate_case`继续以既有规范化JSON对象身份绑定；容器原始文件哈希另行用于输入保护。原始冻结案例文件继续使用固定内容锚点。
- banlist相对路径统一以仓库根解析，并拒绝越界、链接及缺失路径。
- normal恢复的来源、prepared、哈希及输入拒绝路径在进入阶段循环前保存路径安全的独立结构诊断；诊断独占保存失败时闭锁。
- 新增`audit-curry-input-recovery`和独立v1报告/诊断schema。实现路径保持只读，不使用native入口或可写账本恢复接口。
- 合成回归覆盖规范化对象与容器字节的差异、prepare到七阶段与重放的完整合成路径、拒绝诊断、损坏输入及保护失败。

## 验证结果

- 聚焦unittest：49项通过；最后一次定向复验：9项通过。
- 明确文件清单的Python全套：402通过、7跳过、0失败。跳过项都是本机资产/报告或赛事配置opt-in，详情在`docs/TESTING.md`。
- `cargo fmt --all -- --check`及隔离target下workspace all-targets Clippy通过。
- workspace串行测试：327通过、36忽略、0失败；adapter examples：44通过、1忽略、0失败。忽略测试的名称和原因已记录在`docs/TESTING.md`。
- 默认pytest目录发现模式因ACL受限的旧临时目录出现56个`PermissionError`而未完成收集；显式选择45个顶层Python测试文件后全套通过。相关路径原样保留，没有删除或改ACL。
- 独立审阅确认真实审计停止阶段、调用状态和可写账本状态的描述准确；审阅未运行审计或外部进程。

## 恢复条件

本批已暂停。下一批应先另行处理`archived_refusal_source_hash_mismatch`的来源解释，不得把本报告解释为冻结输入或账本核验通过。若后续要重新进行任何真实审计，必须先明确新的审计计划、独立输出位置和调用边界；本批的一次性审计不得重跑来覆盖失败证据。

审计时工具身份是`c36aae0ef1ce981c3f2770520e8cfadc20991b04aea038e5337f07aca691a6ac`、506文件。最终文档后的源码身份、ZIP归档、文件清单、工具链、测试日志、schema校验与acceptance保存在忽略目录`data/runtime/p1-curry-input-recovery-offline-2026-10-24/final-delivery-after-docs/`；对应最终源码身份和归档哈希以该目录`tool-identity.json`、`source-final-file-list.json`及`acceptance.json`为准。当前交付总证据量见其`evidence-size.json`。审计日志位于`target/p1-curry-input-recovery-offline-2026-10-24-verify/`；固定输出及最终收尾材料位于`data/runtime/p1-curry-input-recovery-offline-2026-10-24/`。旧confirmation七个槽位和所有历史窗口不转移、不续用。四项资格`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均保持false；不切换部署、不提交或推送Git。
