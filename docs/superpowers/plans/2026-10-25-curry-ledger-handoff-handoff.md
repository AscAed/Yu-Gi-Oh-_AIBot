# Curry父账本锁释放与stage 2只读验收断点

## 当前结果

本批修复了父账本只读句柄与独占收费锁冲突，并完成离线回归；真实固定stage 2只读审计按计划只运行一次，但在最早的`acceptance_delivery`门禁失败。本批新增原生worker调用为0。

固定隔离目录为`data/runtime/p1-curry-ledger-handoff-offline-2026-10-25/`。唯一审计报告`audit-report.json`的SHA256为`4b3a802cb26097ec2bdf48ef59ffe56103ac87fc3b0842209feb3a7c89e0ec2e`（2,414字节），通过`curry-ledger-handoff-audit-v1` Python合同与JSON Schema。报告状态为`failed`，`failure_checkpoint=acceptance_delivery`，稳定诊断码为`curry_handoff_acceptance_accounting_invalid`。报告不可覆盖，不得在本断点直接重跑固定CLI。

## 固定基线与计数

- 原scope：`curry-option-verification-v1`，限额7，原生消费1、完成1、未知0；stage 1成功，stage 2在收费前失败，stage 2收据缺失，后续槽位6个封存。
- V3风险预留：7次、规划基数39，固定报告SHA256 `14c13e4992673115c0211259dd7d035d968b9c36518c28b4a4ea159ff06ad43f`。
- 已认证历史子集32次，加原scope已消费1次，沿用原验收口径为33次；规划40。旧confirmation实际消费及全部历史实际累计仍为`null`。新审计因首个门禁失败没有重新认证账本，所以不能把这些数字表述为本次新审计结论。
- 最新固定基线delivery SHA256 `2326c1e19fb58b41635141a16ea4321ad94c3002afdf19484e7fb643250c2f55`，acceptance SHA256 `d0283275972ce29fdb636ee2c5e005ab710b05c9125597cf6c34bdd67a56d9d3`。
- 本批审计源码身份 `9288335ca2fab0234489377ea1351bc651fca5b40fb6b03a25a472700b312ecc`，548项。审计时ZIP SHA256 `20ce6d7fde0a18f602c161c4a6b193795c1490eeedc138e2014e8bfa2c1fc20b`，清单SHA256 `713b24d41dbff9c1bf7a23f8529b0c348c28132d0645899dd328942dd215791d`。
- 隔离runner SHA256 `cd5f294e99aa5c44935e2ef414865a6f46fa2c8bbb5230f018d31ad606365b8d`；build-record状态`recorded`，源码前后身份相等。该runner只构建、封存，未启动。

## 代码和验证

Rust normal路径中的`verify_parent_request`现返回`Result<()>`，在打开同一ledger的独占writer前释放共享只读文件视图。normal的只读统计也处在局部作用域。独占journal打开后仍重新核验父收据、请求派生与收费资格，保留Windows共享模式和Unix锁。

新增`--audit-saved-input-only`只接受原verification scope的stage 2，要求prepared摘要和`--trace-stderr`。它在同一只读journal视图内核验父收据、派生请求和统计，并在writer或adapter之前返回，不受旧窗口到期影响。错误参数组合、其他stage、已有stage 2收据及账本消费不符都会拒绝。

Rust红测在stage 1之后真实合成路径复现Windows OS共享冲突；修复后生产normal stage 1→2合成收费通过。父证据语义TOCTOU测试在独占锁内重新验证后拒绝篡改且不作第二次adapter调用。validation、confirmation和verification的完整七阶段合成路径均通过。Rust与Python独立审阅通过。

验证明细：

- `cargo fmt --all -- --check`：通过。
- `cargo clippy --workspace --all-targets --offline --locked --target-dir target/curry-ledger-handoff-rust-target -- -D warnings`：通过。
- `cargo test --workspace --all-targets --offline --locked --target-dir target/curry-ledger-handoff-rust-target -- --test-threads=1`：380通过、0失败、37忽略，87个suite；Curry example runner harness 54通过。
- Python显式枚举`tests/`顶层64个`test_*.py`文件，最终全套517项：508通过、0失败、9跳过，686.28秒。跳过原因：Windows环境不支持的两个目录链接用例，以及v3/v4、真实v2、快照、完整策略、本机引擎资产和独立赛事资产配置的opt-in用例。日志及清单：`target/curry-ledger-handoff-python-tests-final/`。
- 第一次全Python测试与并行源码修改重叠，报告502通过、2个`source changed during capture`失败、9跳过；冻结后干净复跑通过。首轮日志保留在`target/curry-ledger-handoff-python-tests/`，不作为最终结果。
- 新Python审计和diagnostics聚焦测试：27通过、2个子测试通过；独立Python审阅另以`py -m pytest tests/test_curry_ledger_handoff_audit.py -q -ra`得到13通过。

## 真实审计为何停止

正式CLI只执行了一次：

```powershell
py -m ygo_eval.research audit-curry-ledger-handoff `
  --baseline-dir data/runtime/p1-curry-option-verification-native-2026-10-25 `
  --runner data/runtime/p1-curry-ledger-handoff-offline-2026-10-25/native-artifacts/curry-option-validation.exe `
  --build-record data/runtime/p1-curry-ledger-handoff-offline-2026-10-25/build-record.json `
  --output data/runtime/p1-curry-ledger-handoff-offline-2026-10-25/audit-report.json
```

耗时3.752秒、退出码1。`acceptance.json`的锚点哈希正确，且各会计值与期望一致；实际结构中的政策字段名是`policy_reserve`。审计器验证`expected_accounting`时也使用`policy_reserve`，但随后的整数类型列表误写为`policy_reserved`，于是固定成功材料在第一检查点被拒绝。合成成功夹具未覆盖与真实acceptance完全一致的字段集合。

该门禁失败发生在来源后续检查前。审计报告的`native_calls=0`、`execution_ready=false`、`new_consumed=null`、`unknown=null`。saved-input runner未启动，`process-diagnostics/`未创建；阶段2收据仍缺失。因而本次未重新核算九份历史账本或V3来源链，也不能据此认证真实saved-input通过或旧scope消费统计。

## 下一次续接

1. 先增加精确镜像固定acceptance的合成会计结构，并确保`policy_reserve`字段在expected值、类型检查、schema与校验器中一致；加入所有类型和缺失字段负例。
2. 运行聚焦Python失败测试，再运行Python完整517项（或当时新枚举的全部顶层文件）、Rust格式/Clippy/workspace串行测试，并重新独立审阅。所有构建和测试日志继续只写忽略目录。
3. **不要覆盖或重跑本批报告。**固定输出路径已有不可覆盖的失败报告；后续若获准重做，只读saved-input验收，需要新增独立版本/attempt目录与报告锚点，保留本次失败报告与进程输出字节。先检查新attempt路径不存在，再设计固定CLI。
4. 通过全部离线门禁后，才可根据下一批明确授权，运行一次既存stage 2输入的纯只读模式。严禁normal、worker、doctor、FFI、窗口或收费ledger。任何新的首检失败均保存并暂停。
5. 预期的saved-input结果仅用于验证请求/父收据/资产/ledger的一致性，不能把旧stage 2改写为成功执行或重放，也不提升四项资格。

文档定稿后的完整源码身份、文件清单和ZIP保存在忽略的`target/curry-ledger-handoff-python-tests-final/final-source-release/`，与审计时源码身份分开记录。最终体积清单`target/curry-ledger-handoff-python-tests-final/evidence-size.json`逐项记录测试、Rust隔离构建和审计交付的字节数、文件数及访问失败；测量未遇访问错误。ACL受限的既有临时目录保持原样，不删除、不改权限。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均保持false。
