# Curry资产角色绑定修复与只读验收断点

## 结论

离线实现、全套测试、隔离runner构建和真实冻结输入的只读预检均已完成。只读审计报告为`passed`，9项检查全部通过；审计runner仅运行`--preflight-only --trace-stderr`，返回码0，报告为`preflight_passed=true,native_calls=0`。这不改变上一批Curry实验结论：旧scope仍`prepared=false`，七个槽位未消费并封存，opcode14、选项接受、LP变化和重放均未验证。

本批没有创建或打开实验窗口、scope或收费账本，也没有运行normal、worker、doctor、真实资产opt-in或48手评估。历史9份账本仍累计消费32次、未知0；旧Curry`research/calls.jsonl`仍不存在。四项资格标志继续为false。

## 已修复的身份检查

旧生产检查把`request.versions.engine_sha256`与worker身份比较。该字段绑定核心DLL，现与`expected_identity.roles.dll.sha256`比较；CDB及脚本清单检查、完整found/expected身份比较和一致性检查保留。manifest的`input_sha256.worker`独立绑定`expected_identity.roles.worker.sha256`。

normal路径在ledger访问及adapter构造之前运行`shared_preflight`身份扫描，并保留收费前和收费后检查，总计三次；显式preflight仍只扫描一次。三次合成扫描各模拟61秒的normal路径通过单JSON输出、合成收费和收据发布测试。角色哈希使用互异合成值；角色错绑、缺失、漂移、manifest worker哈希错配、预检失败及收费前超时均拒绝，失败时adapter调用为0。

实现位于`crates/ygo-engine-adapter/examples/curry-option-validation.rs`。独立只读入口位于`python/ygo_eval/curry_asset_binding_audit.py`，命令为：

```text
python -m ygo_eval.research audit-curry-asset-binding
  --baseline-dir data/runtime/p1-curry-option-validation-native-2026-10-23
  --runner data/runtime/p1-curry-asset-binding-offline-2026-10-24/native-artifacts/curry-option-validation.exe
  --build-record data/runtime/p1-curry-asset-binding-offline-2026-10-24/build-record.json
  --output data/runtime/p1-curry-asset-binding-offline-2026-10-24/audit-report.json
```

审核只读核对两时点构建、原Curry manifest/prepared/summary、请求、输入、seal、身份、窗口、原始诊断、源码归档及文件清单，并通过纯字节历史核验重算9份账本和引用材料。固定锚点如下：

| 材料 | SHA256 |
|---|---|
| 旧文档后构建记录 | `0101d9a46855189b50878e4fef6d4fecf5e0b279a6ad88f6171230fcfbd4ab41` |
| 旧原生构建记录 | `9bef7b74baac4a502ad94b1296ade61a081c233f027963329dc22b102ad17626` |
| 旧manifest | `b170c35ff48fb4c22892ecffd15324cc7ecc5dfe318a7f1668b0f448756641c3` |
| 旧prepared | `3ba3e920a0721c462e0ec3401a509b8e037a7c65a48b0a67c1dd8fc6aeb5a2b8` |
| 旧summary | `37a1bf1dab01305bed38d35d398594f112e67290c97c92379673002c06b8361a` |

原native和文档后源码身份分别为`29205c8ef0b98b07b3003a64baa6c7dede5e03391cf7e245b59905e0b2341028`（494文件）及`1dd6c895cc013add3b51dd5945d63ce3fa9c3da08b81ce512f569d690e7bc3ea`（495文件）；两份归档之间只允许三个文档差异。原summary诊断仍为`curry_preflight_output_mismatch`，原始进程材料仍观察为`curry_asset_identity_mismatch`。审计没有回写旧manifest或补造旧预检实际扫描值。

## 验证与构建

完整验证日志在忽略目录`data/runtime/p1-curry-asset-binding-offline-2026-10-24/verification/`：

- Python全套`py -m unittest discover -s tests -p 'test_*.py' -v`：382项总计，375通过、7跳过，191.278秒。
- 聚焦审计测试：19项通过、4个子测试通过；`py_compile`及CLI help通过。
- Rust `cargo fmt --all -- --check`、workspace全目标Clippy（offline/locked、`-D warnings`）通过。
- Rust workspace串行测试：325通过、0失败、36忽略；examples：42通过、0失败、1忽略。Cargo命令使用`target/curry-asset-binding-cargo`，同时设置`CARGO_TARGET_DIR`和`--target-dir`。

Python七项跳过及理由：v3报告opt-in、v4报告opt-in、本机引擎/ABI资产未提供、实际快照/报告未提供、实际v2报告未提供、完整策略报告opt-in、赛事独立2026资产配置未提供。Rust忽略用例及理由逐条保存在`verification/rust-workspace-serial.log`和`verification/rust-examples-serial.log`。真实资产opt-in、doctor、normal、worker及48手评估未运行。

审计时源码身份`43f4518145e6fa0157896c96f6d48dcd9df89c80f24d64bfc6a116b6be7e62f2`，498文件；源码归档SHA256 `a235cf00ee038196782e1e33992bc7719d5dce9169d56d204f5d99167a5fbbde`，文件清单SHA256 `75b21e3fd265ffac5c9bca78c4d067c6a479f937d07461733ef8fec73e005aff`。隔离构建记录SHA256 `da933dbae09031d5646cbed1eccdcafc403e3378e071f85e70d6d4b0945429e2`；runner SHA256 `f0cc84f858c8bbd5bc771cf6146850b8dfeabb9f78ffbff633cf53c15f479240`，5,703,680字节。构建观察记录没有证明可复现构建。

真实只读审计报告SHA256 `f31e019affc99d3cf8cfc81921f72a424c904fcc4750b67a0a443ae3fc5a74b5`。报告九项检查均通过，历史消费32/未知0，历史9账本以不可写方式核验。新runner正常单JSON stdout为239字节；stderr为225字节阶段追踪，shared_preflight耗时161.618秒。原始stdout、stderr和进程metadata均独占保存在忽略目录`process-diagnostics/`。原报告输入哈希`b57c301471920aa0ab9609be1d2893814b99cfd0d98fcd7a410d0e8233d0599f`；进程metadata哈希`3c170463135b2f8cfd6bb027369d1a2050d64700584aebac725b4ac97dc0a172`。

本批测试初次误在固定忽略输出根创建空目录`test-fixtures/`。检查确认其为空且没有历史材料；保留不动，不删除、不覆盖。

## 续接门禁

文档后最终源码归档、文件清单、构建记录、runner副本和证据体积记录位于同一忽略根的`final-build/`与`verification/`。最终源码身份以`final-build/source-identity.json`为准；审计runner仍仅绑定审计源码，不因文档后构建而取得历史原生资格。

下一次继续时先只读核对本handoff及忽略目录最终交付清单、源码身份/归档、日志、证据体积记录和9份账本。不要重跑已通过的真实审计，不要进入旧scope执行，也不要使用其七个封存槽位。未来Curry七阶段若另行推进，须先定义并授权全新scope与预算。普通部署、active资产、旧报告和Git索引均保持原样；不自动提交或推送。
