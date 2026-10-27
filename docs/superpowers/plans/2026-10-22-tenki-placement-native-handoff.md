# 天玑区域18与opcode13验真：断点交接（2026-10-22）

## 当前状态

新六阶段scope的代码和离线测试已完成，但原生阶段被保护worker哈希差异阻断。新实验目录和scope未创建，未消费额度。本轮不要从stage1开始，也不要将当前`target/debug`二进制视为通过基线。

仓库HEAD仍为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`。完整离线总检时源码身份为`7349d8a09e74d975e81a85c02b8725cea424d6cc82353765761c742238ec2004`、396项内容文件；该身份取自当前保留的未提交工作树，文档收尾会使内容身份继续变化。不要从HEAD覆盖当前工作区。

## 基线和零调用复核

- 六份旧账本只读核验累计26次、未知0；旧预算窗口继续封存，旧scope余4槽不使用。
- `data/runtime/p1-tenki-probe-native-2026-10-21/native-artifacts/prompt-probe.exe`与记录SHA匹配：`d28c6678f39428552b0301b654f1a1961c2becb5ab794a8005be755abd142e4f`。
- 前一轮合同收尾的记录显示，旧stage1/2输入SHA、收据SHA、`research/calls.jsonl` SHA在其核验前后保持不变；匹配runner对两阶段分别执行`--verify-recorded`和`--stats`，四项输出均为`native_calls=0`，账本消费2、未知0，账本SHA为`5337352e249a13eb51a5a6dd124bc2397c4402a68e99cd77c2bffc7da22392b6`。stage1成功；stage2失败并停在opcode18/prompt9。本轮在保护文件哈希门禁处停止，没有再次运行旧runner。
- 保护清单366项中365项哈希匹配。唯一不匹配是`target/debug/ygo-engine-worker.exe`：期望`a384b35aff160049b3381f15bfc35e17cf373a1ada54986b8c884bde09c78c7e`，当前`be6aae6ec2d03ae3293f2954fb84be211483bd9c5b57e4ac3b546b7239db9eba`。本地和关联目录、历史源码包、runtime副本搜索均未找到可验证原件；历史build记录来源不具可复现证明力。

## 验证记录

- 聚焦Python：`py -m unittest tests.test_native_tenki_placement -v`，9项通过。
- Python全套：`py -m unittest discover -s tests`，223项，216通过、7跳过，用时102.925秒；忽略原因均为opt-in/live资产：v3报告、v4报告、本机引擎ABI、真实快照/报告、实际v2报告、完整策略报告、赛事资产重放。完整输出在忽略目录`target/tenki-placement-offline/python-full.log`。
- Rust格式和全目标Clippy通过：`cargo fmt --all -- --check`、`cargo clippy --workspace --all-targets --offline -- -D warnings`。测试使用隔离`CARGO_TARGET_DIR=target/tenki-placement-offline`，避免改写受保护`target/debug`。
- Rust workspace串行测试：292通过、36忽略、0失败；`ygo-engine-adapter` examples：22通过、0忽略、0失败。36个忽略项均需真实冻结引擎/资产、手工准备或显式pilot opt-in，明细保存在`target/tenki-placement-offline/workspace-test.log`。
- schema通过Draft 2020-12检查。独立审阅确认收费阶段绑定完整；修正了`Ok`/`Err` JSON schema拒绝真实结果的缺陷。CLI help中包含`native-tenki-placement-probe`。
- 本轮未运行普通原生模式、worker、doctor、真实资产opt-in或48手评估；未切换部署、提交或推送。

## 继续条件与入口

先解决受保护worker原件/基线锚定问题。取得匹配原件时核对其精确SHA与来源，不覆盖其他文件；若没有可核实原件，应先获得对基线更新的明确授权。解决前不要创建新预算窗口、账本或实验目录，不扫描候选资产，也不要调用新runner。

恢复后以[实施计划](2026-10-22-tenki-placement-native.md)为准。新目录固定为`data/runtime/p1-tenki-placement-native-2026-10-22`，已核实本轮结束时不存在；若之后存在，只核对并恢复其中的同一断点，不换名续费。六阶段上限6次/2小时，stage1/2提示发现不授予重放资格，stage3/4为false执行/重放，stage5/6为true执行/重放；任一停门条件成立即停止，不重试。

原生每组历史消费前缀分别应为1至6；成功累计才是32。当前应记录原26＋本轮0＝26、未知0。`proof_ready`、`complete_action_coverage`、`global_optimality`和`native_probability_verified`继续false。
