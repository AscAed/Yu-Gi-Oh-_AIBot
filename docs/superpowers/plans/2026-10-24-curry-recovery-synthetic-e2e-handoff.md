# Curry 公共审计完整合成验收：额度暂停断点

## 暂停状态

用户告知当前 Codex 五小时额度不足 5%，因此本轮在不启动任何原生工作后暂停。当前交付目标仍未完成：需要用完整合成来源树贯通既有公开 `audit_to_output`，再跑完整 Python 验证并完成交付。此断点记录不是验收通过声明。

暂停前的工作树源码身份为 `0e702c63e9ba133304d874391609dea4b2745a58f7ed5e7a2aa1a0a68754a1d9`，526 个身份文件，HEAD `8a6b2f6762131aebea6d8c0f5f61363d573f1b36`。该身份是在新增本断点文档及索引更新之前采集；文档更新会改变工作树身份。工作区已有大量未提交改动，必须保留，不能 reset、清理或提交。

固定事实仍为：上批验收 SHA256 `20654b7d09247f5f71acd038c6f72546b50a8bfa85f0a3bb9041fc297b1c69e0`；既有真实 v2 报告 SHA256 `67c6332310aed1e77ccc9eb4394b700f4169837b198a50de20d422dc01da757b`。已认证历史子集为九份账本、32 次消费、未知 0。旧 Curry confirmation 的消费仍为未知/null，七个槽位继续封存。固定交付目录 `data/runtime/p1-curry-recovery-synthetic-e2e-offline-2026-10-24` 在暂停时不存在；不可提前创建。无新增原生请求、窗口或收费账本；没有启动 runner、worker、FFI 或 doctor。

## 已完成且保留的改动

- `tests/test_curry_recovery_e2e.py` 增加提示来源文件哈希固定测试。修正测试时发现 helper 会覆盖子来源中已固定的 prompt 文件；现已改为读取并验证固定文件，不再重写它们。
- `tests/support/curry_recovery_e2e.py` 补充递归历史账本所需的合成消费计数；修正 Tenki 验证交付的 `identity`/`source_identity` 字段绑定；调整合成归档成员、delivery audit 相对路径及外层 Curry 归档成员。
- `python/ygo_eval/native_tenki_placement_validation.py` 显式把交付 `identity` 字段映射到来源描述的 `source_identity`，并继续逐字段严格匹配归档、清单、身份和文件数。
- `python/ygo_eval/native_curry_option_validation.py` 从不可变来源描述取得 delivery 期望哈希，避免测试路径依赖硬编码生产锚点。
- `tests/test_native_tenki_validation_workflow.py` 的合成 verify 响应补齐 `successful` 和认证账本统计，符合现有 verify 合同。

最后一次未经复验的补丁，是为外层合成归档增加两个严格要求的源码成员：`crates/ygo-engine-adapter/src/tenki_placement_probe.rs` 和 `python/ygo_eval/native_tenki_placement.py`；同步调整占位成员数，保留归档总成员数。此前直接公共验证已推进到这两个成员缺失的异常，因此该补丁针对最后观察到的根因；**补丁尚未运行测试验证**。

## 已运行验证及停止处

- 提示来源固定测试先红于错误使用不存在的 `audit.sha256_file`，改用 `hashlib` 后继续测试；随后红测准确发现 helper 重写已固定来源文件。修正后该测试通过（10.99 秒）。
- 较早的聚焦集为 3 failed、6 passed、5 subtests passed（77.17 秒）。失败都在公共递归成功路径的早期门禁，之后逐项补足合成来源字段、归档映射和verify统计。
- 最近一次直接调用现有完整公共审计路径，错误推进到了外层 Curry baseline ZIP 中缺少 `crates/ygo-engine-adapter/src/tenki_placement_probe.rs`；上述最后补丁尚未复跑，所以当前成功状态未知。
- 未运行全套 pytest、Rust/Cargo 总检，也未执行真实历史审计。旧 ACL 受限 pytest 临时目录保持原状，不改权限、不删除。既有来源报告仍在，固定最终交付目录不存在。

## 恢复步骤

1. 先查看本文件、`TASKS.md` 顶部状态、`docs/TESTING.md` 顶部实跑记录和 `docs/INDEX.md` 链接。重新确认固定最终目录仍不存在、真实 v2 报告及九份历史账本锚点仍匹配；不要用缺失文件推断旧 confirmation 消费为 0。
2. 查看 `tests/support/curry_recovery_e2e.py` 最后改动，并运行下面的聚焦集，验证上节所述最后归档修补：

   ```powershell
   py -B -m pytest -q -ra -p no:cacheprovider tests/test_curry_recovery_e2e_fixture.py tests/test_curry_recovery_e2e.py tests/test_curry_recovery_checkpoints.py
   ```

   任何失败先定位最近实际门禁，不跳过递归验证、不替换哈希/角色映射或调度器。合成材料只写到被 `.gitignore` 排除的 `target/curry-recovery-synthetic-e2e-tests/`。
3. 补强 checkpoint 测试：`tests/test_curry_recovery_checkpoints.py::CurryRecoveryCheckpointPublicPathTests.test_each_v2_checkpoint_failure_is_saved_and_stops_the_public_audit` 当前七个失败子用例覆盖 `acceptance_delivery_anchors`、`evidence_inventory`、`source_archives`、`frozen_input_binding`、`historical_ledgers`、`old_material_protection`、`input_stability`。审查发现 `historical_ledgers` 目前没有断言该真实阶段确实已被调用，可能在前置阶段失败后仍被错误贴上该checkpoint；增加 spy/call-count 断言。另补一条 journal `previous` 指针被修改的损坏链负例。
4. 聚焦测试通过后，显式枚举 `tests/` 顶层所有 `test_*.py` 并以 `py -B -m pytest -q -ra -p no:cacheprovider` 执行全套；保存测试名、跳过原因、耗时及日志到 `target/curry-recovery-synthetic-e2e-tests/pytest-full.log`。不要广泛扫描 ACL 受限临时目录，也不要更改 ACL。
5. 让独立审阅确认完整合成来源树确实通过公共 `audit_to_output`，报告通过现有 v2 Python 校验器和 JSON schema，七个检查点负例各自停在目标阶段且后继阶段/禁止操作调用数为零。若 Rust/Cargo 文件与此前认证源码归档一致，引用既有 Rust 验证；若变动，则按任务计划隔离并重跑 fmt、Clippy、串行 workspace 和 examples。
6. 只有完整成功路径、负例、总检和审阅全部通过后，才首次独占创建 `data/runtime/p1-curry-recovery-synthetic-e2e-offline-2026-10-24` 并保存合成报告、测试日志、审阅和验收。若该目录届时已存在，核对断点后续写，禁止覆盖或换名。
7. 更新 `TASKS.md` 当前状态、在 `docs/TESTING.md` 顶部追加真实测试证据、保持 `docs/INDEX.md` 链接和本断点；保存测试时点及文档收尾身份/清单。不得重跑真实审计或创建原生窗口。最终结论必须保留 native calls 0、旧 confirmation 消费 null、四项资格 false。不提交、不推送。

## 保护边界

仅完成这一批原本授权的离线合成验收。禁止启动任何 runner、worker、FFI、doctor、真实审计或原生实验；禁止创建 scope、窗口或收费账本；不切换部署、不改旧报告/账本/验收，不删除或修复 ACL 受限文件，不提交或推送。合成结果不能获得真实历史来源或原生资格。
