# Mooyan Curry opcode14七阶段验真断点

## 当前结论

本批已完成离线实现、全套验证、隔离构建、历史证据复核及收费前准备。固定窗口的 `--prepare-only` 在只读预检失败，按原定门禁停止；没有进入 stage 1 normal 请求。不得用当前scope重试，也不得把剩余7个槽位转给其他scope。

- scope：`curry-option-validation-v1`
- 固定目录：`data/runtime/p1-curry-option-validation-native-2026-10-23/`
- 起点：`1792771619`（2026-10-23 16:06:59 UTC / 2026-10-24 00:06:59 +08:00）
- 限额：7次worker请求、7200秒；收费账本未创建
- 历史累计：32次、未知0；本批新增：0次、未知0
- `research/prepared.json`：`prepared=false`、`execution_ready=false`、`native_calls=0`
- `research/summary.json`：失败；`research/calls.jsonl`不存在
- Curry opcode14提示、两个选项响应、LP变化和独立重放均未触达；四项资格保持false

## 已固定的来源与构建

上批天玑验收SHA256为`242e0f5e1839f132d5b091963ba9917691536ae0913e7beeca6fc62635d7f4f9`，delivery SHA256为`7c46a4a790c56dea2daf77478c5a33654ee20bb3bd3179bdfb57ebf74cc21061`。重新核验通过，历史9份账本仍累计32次、未知0，518项保护材料匹配。保存的准备合同是`prompt-14-curry-v1`，执行资格仍为false；冻结核心 `operations.cpp` 哈希绑定为`b46cf0d53825cb662af319a7382015b555422aa11903067445c994c4b0c8a990`。

原生前源码身份 `29205c8ef0b98b07b3003a64baa6c7dede5e03391cf7e245b59905e0b2341028`（494文件），构建前后身份一致。build-record identity `5dc12ce4742ed5fb2364b8d8c51aed7bb95dd098734ee95e304f90a799d4fb88`，文件SHA256 `9bef7b74baac4a502ad94b1296ade61a081c233f027963329dc22b102ad17626`，状态`recorded`；`reproducible_build_proven=false`。CLI、runner、worker SHA256依次为：

- `00395cd2e209746ba7295d07782fd64ce635a960273c511469e0b0a89959e089`
- `57e119a1232b91dd57d13a5803475398589d2a801cc95ea27790a813326ed85f`
- `087fe574ac8d21a10befdbdad9ccfbc871805e643b6669e3fab520c8eb7fcb6d`

三份产物副本和构建记录一致。原生时源码归档`source-native.zip` SHA256为`d8b31b838f0b559adc513159a2e8135fd6ecaf2fab0c42897e3f8ebd6fc99582`；文件清单SHA256为`4c64d44dba562aa9f1ac8d133d63f56b9b0b6e4d02a826e144767477116cf04b`。普通资产身份`77d671fd2b48bdb230bbebb8445f5dce11d6958ec0f86577355a6810ad8de462`；完整双资产身份保存在忽略目录`identity.json`。

## 收费前阻断及根因

唯一runner进程为 `preflight_only`，原始诊断侧车：

- `process-diagnostics/preflight_only-d3e880ecf8d04c56a110a3d777e21a2e.json`
- stdout：0字节，SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- stderr：273字节，SHA256 `a3b70cf9e917d6791789e9f3933c92cf6d5ba9bf9c62c02f056bc5c8533f0672`
- runner退出码：2；stderr稳定错误为`Curry asset identity differs from frozen request`

输入验证和共享预检阶段后，Rust的`verify_asset_identity`拒绝身份。保存的请求中`versions.engine_sha256`是核心DLL SHA256 `446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9`，与冻结资产`roles.dll.sha256`匹配。冻结身份中worker SHA256是`087fe574ac8d21a10befdbdad9ccfbc871805e643b6669e3fab520c8eb7fcb6d`。但[`curry-option-validation.rs`](../../../crates/ygo-engine-adapter/examples/curry-option-validation.rs)的`verify_asset_identity`把`roles.worker.sha256`与`request.versions.engine_sha256`比较，因此必然拒绝这组身份。Python manifest门禁按正确角色绑定：worker身份与构建worker匹配，`engine_sha256`对应DLL，CDB和脚本manifest分别对应各自哈希。

Rust `--preflight-only`分支在ledger inspect/open和adapter构造之前返回；该调用没有启动worker，没有打开或创建新账本。`prepared.native_calls=0`，收费账本文件缺失。错误不是资产内容漂移。summary资格仍失败，不能把预检过程包装为响应或重放证据。

## 离线验证和独立审阅

在冻结构建前完成：

- Python：`py -m unittest discover -s tests -v`，373项通过、7项opt-in跳过（152.259秒）
- Rust：`cargo fmt --all -- --check`通过
- Rust全目标Clippy：offline/locked、隔离`CARGO_TARGET_DIR`、`-D warnings`通过
- Rust串行workspace：325通过、36忽略、0失败
- Rust examples：37通过、1忽略、0失败
- 独立只读审阅确认固定基线/路径、窗口先于候选资产扫描、runner preflight在账本与adapter前结束。随后对真实冻结输入的只读预检暴露了上述哈希角色不一致。

日志保存在忽略目录`target/curry-option-validation-tests/verification-20261023/`。真实资产opt-in、doctor、48手评估未运行。隔离Rust产物缓存为`target/curry-option-validation-tests/native-build-target/`。

## 暂停后的边界

1. 保留当前窗口、manifest、prepared失败状态、summary、诊断、原始请求/输入/seal、source archive、build record和产物字节，不清理或改写。
2. 不调用当前scope的`native-curry-option-validation` normal模式，不重新跑preflight，不新建替代目录或账本。
3. 离线修复应先增加真实语义分离测试：请求`versions.engine_sha256`绑定`roles.dll`，worker哈希与冻结expected identity/worker产物绑定，四类哈希保持角色分离；再修改Rust检查、运行聚焦和全套回归、独立审阅并构建。
4. 当前scope窗口已经创建且源码/产物已冻结，即使消费为0，也不可沿用7个请求。任何后续原生验真须先确认新scope/预算；新构建、新来源锚点和新的收费前准备不能改写本批报告。
5. 若后续不启用新原生窗口，可单独交付离线合同修复，但只能说明工具修复，不能声称Curry提示到达或两个响应可接受。

`TASKS.md`只更新当前状态，`docs/TESTING.md`追加本次实跑。保留原有未提交工作；没有切换普通部署或active资产，没有提交或推送Git。
