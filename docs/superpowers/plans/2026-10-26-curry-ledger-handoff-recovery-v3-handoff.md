# Curry V3真实来源角色适配与零runner恢复交接

## 交付状态

本批已完成。V3来源角色修复、公共合成路径、全量Python测试、独立审阅、唯一一次真实纯Python恢复及只读verify均通过。新增原生、runner、worker、FFI调用均为0；未构建、未扫描实时资产、未创建scope、窗口或收费账本。

固定输出根：`data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26/`。

## 基线与实现

启动时基线源码身份为`36efdebebc14f992dc55915274ba61f1dff97f1c9579d7c839decf6cab9d8ffa`、586项。实现与测试后，审计工具冻结身份为`b84db687415eb990692e19c4385443e08ab478f9b5160d2cc11a9b44f1899954`、588项；相对V2最终清单增加恢复V3 schema和V3测试文件，修改审计器、恢复器、V3/V4/V5审计schema、合成支持和公共E2E测试。151项Rust/Cargo与V2最终清单逐项一致，没有新增、缺失或哈希变化。

固定V2失败报告SHA256为`7496f981438bdca15f768eb38c6402cf15cc8ff88401d661fae7ee554dc476d6`，V2 final delivery为`c3bf0aa851b5cd6b39045ee5b8897d3c53f934de4ab31a5ec0cf1dc93fb7ccfe`，V5 delivery为`3c689f9ae6860da3b42a0ea4f6f0e5e3b100fdc2c548f91f2e288268bd071278`，均经本批重新核对。V2实际V3来源角色是`v3_source_workspace_identity`；V3只接受该固定角色，不把`v3_source_confirmation_summary`当作别名。V2归档按静态字节核验，未执行归档代码，也未假设存在完整585项审计工作区归档。

V3规范精确要求187个输入角色。成功报告中的角色组为：V5原始审计164、V5恢复锚点5、原scope blob 6、V3预留100、V1失败源6、V2失败源6。同路径别名和blob次序由运行时与schema共同约束。修复后的发布重建把工具身份绑定到当前workspace，发布签名覆盖`tool`；verify-only仍允许文档收尾后workspace身份变化。独立只读复核确认这些约束，没有修改文件，也没有启动执行器或访问可写账本。

## 测试证据

恢复V3模块及V5兼容路径聚焦测试：17 passed（209.30秒）；V1/V2恢复及V3/V4/V5公共审计回归：5 passed（367.45秒）。显式枚举81个顶层Python测试文件的全套pytest为671 passed、9 skipped、0 failed，用时1,461.55秒。清单为`target/curry-ledger-handoff-recovery-v3-tests/pytest-files-v3-final.txt`，SHA256 `606d745432fb827c59aa2b6c82ef8b53cae61f279f15dfe3456a1c93750c7ce4`；带`-ra`日志为`target/curry-ledger-handoff-recovery-v3-tests/python-full-suite-v3-final2.log`，SHA256 `2f55b04de3f971d28d773c01c751622fc5f20bee5dca3a81ce033d4a309d9383`。发布身份的两个末尾覆盖测试随后另行通过（2 passed，1.68秒）。

9项跳过：Windows目录符号链接能力限制2项；v3 reports opt-in；v4 report opt-in；未提供本机引擎资产；本地快照/报告opt-in；真实v2报告opt-in；完整策略报告opt-in；未提供独立2026赛事配置。Rust/Cargo本批未改动，因此引用既有fmt、workspace全目标Clippy和workspace 380 passed/37 ignored结果，没有重复Rust总检。

## 唯一真实恢复结果

实际命令：

```text
py -m ygo_eval.research recover-curry-ledger-handoff --report-version 3 --baseline-dir data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26 --output data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26/recovery-report.json
```

纯Python退出0，耗时35.541927秒。报告`recovery-report.json`为51,891字节，SHA256 `69d2af394169d5773394e775718840ef9a3df22eac12167d2e7ba3c79484c468`，`status=passed`、`valid=true`，九项检查全部通过。审计工具身份`56f967190b3333f8bd0d5b323577149c577e1c34bbb6b158ba7c013e33a8cc31`绑定workspace身份`b84db687415eb990692e19c4385443e08ab478f9b5160d2cc11a9b44f1899954`。

进程原始stdout为51,891字节、SHA256 `6c1da8f3207603cee38202323c37e77ff1fdc893b7bad40cc296956e21645cf7`；stderr为空、SHA256为`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。退出码、原始stdout/stderr和元数据保存在`target/curry-ledger-handoff-recovery-v3-tests/real-recovery-attempt/`。恢复前后workspace身份相同。

唯一真实恢复重新认证原scope `curry-option-verification-v1`为消费1、完成1、未知0、额度7；认证历史子集为32，含该scope为33，风险预留7，规划总数40。旧confirmation实际消费与全部历史实际累计仍为`null`。stage 2请求、input、prepared、seal和账本哈希匹配固定值；stage 2收据仍缺失，原stage 2失败结论不变。

恢复后只读verify返回`valid=true`、187项输入。报告SHA256前后相同，V3输出树未变化，verify期间workspace稳定，native/runner/worker/FFI均为0。verify原始输出、错误流和元数据保存在`target/curry-ledger-handoff-recovery-v3-tests/verify-only-attempt/`。文档定稿后另做一次零调用verify；最终源码归档、文件清单及交付记录见`data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26/final-build/delivery-final.json`。

## 交接边界

- V1/V2失败报告、V5保存材料、原scope账本和所有旧收费槽位保持原样；旧六槽继续封存。
- 后续若继续原生工作，必须另立scope并取得新预算；不得从本批恢复报告推导原生重放、完整动作、概率、最优性或正式v6资格。
- `proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`继续为false。
- 不切换普通部署或active资产，不提交或推送Git。
