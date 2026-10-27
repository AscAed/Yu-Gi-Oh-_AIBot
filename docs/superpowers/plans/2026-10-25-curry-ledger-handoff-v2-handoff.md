# Curry V2账本交接审计断点（2026-10-25）

## 结果

本批已完成V2离线合成验收、显式顶层Python全套、独立只读审阅和隔离runner构建。固定真实审计只执行一次，并在首个`previous_failed_source`门禁失败。依照一次性规则，本批在此暂停；**禁止重跑、覆盖或复用固定V2输出目录**。

- V2报告：`data/runtime/p1-curry-ledger-handoff-v2-offline-2026-10-25/audit-report.json`，SHA256 `9d74b97e6553ba141537bae414e0f60740220de48e0b031fdb6bff0bad0928c1`，3532字节；schema v2，`status=failed`，`failure_checkpoint=previous_failed_source`，诊断`audit_failed`。
- V1失败报告：`data/runtime/p1-curry-ledger-handoff-offline-2026-10-25/audit-report.json`，SHA256 `4b3a802cb26097ec2bdf48ef59ffe56103ac87fc3b0842209feb3a7c89e0ec2e`，保持原字节。
- runner没有启动：V2报告`inputs=[]`，return code及stdout/stderr/process-capture字段均null，没有诊断侧车；`native_calls=0`、`execution_ready=false`。本批没有创建scope、窗口或收费账本。

## 首个阻断及后续发现

V2前次失败来源代码要求`native-artifacts/curry-option-verification.exe`，而V1失败交付实际仅有`native-artifacts/curry-option-validation.exe`。后者SHA256为`cd5f294e99aa5c44935e2ef414865a6f46fa2c8bbb5230f018d31ad606365b8d`，与V1 build record的runner产物哈希一致；`curry-option-verification.exe`不存在。这是本次实际触发的首个失败。

独立静态审阅还发现，即使只修正路径，现有“旧归档仍含父读视图跨独占打开”判定也与V1归档不符：548成员源码归档中的`verify_parent_request`已经返回`Result<()>`并释放只读view，`_parent_view_crosses_exclusive_open`对其结果为false。此检查没有在真实审计中运行。不能修改V1归档或把该静态断言写成已通过；后续若继续，必须明确区分真正含原缺陷的历史源码证据和V1审计工具源码，按证据修复来源角色与根因绑定，再走新版本/新输出锚点及完整门禁。

V2报告中的workspace、baseline、reservation、ledger和runner-build稳定性为passed；stage 2收据前后仍缺失。报告检查在`previous_failed_source`停止，其余业务检查为`not_run`，因此V3预留、冻结输入和历史账本并未由本批完整审计重验。

## 已完成验证

- Python：显式运行68个顶层测试文件，555项中546通过、9跳过、0失败，806.42秒；`-ra`逐项明细见`target/curry-ledger-handoff-v2-tests/pytest-full.log`，输入列表见`pytest-files.txt`。9项跳过：两个Windows目录符号链接能力限制；v3/v4报告、本机引擎资产、快照/真实v2、完整策略及独立赛事配置opt-in。
- Rust/Cargo：151项源码与认证清单一致，本批未改Rust；引用既有workspace 380通过/37忽略、fmt和全目标Clippy验证。
- 独立审阅通过；聚焦合成/schema测试2项通过。
- V2 runner构建关联：build-record SHA256 `eef3a7c9519c7996c12b65ef04b0b93a22448a1902419d1e70b7428581307930`，identity `6020ab76de9a097ef28611ff439f061af313c20f6e259d47c222616a5ee2b961`；runner SHA256 `f3cd6148e62addb164e6efd1d613fbcfb6ec81f428ea77c273b436e5f98db8ac`；source identity `cf271cd66778dbc2f3ea066bb1be7df257163686745f8eafdc116a8a2fb52e6e`，557项；source ZIP SHA256 `0f6851a7cb2dd9f03f96c730739b9ab6b57b966d8bc5a656a75acc71af570e2a`，list SHA256 `3dd1eb14e80d97c7f1c6631c77b6817c75843e21d0d5fb721f7b02ac97558784`。

## 记账与保护

独立只读复核确认原账本SHA256 `7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`（2726字节）未变；旧scope既有认证消费1、完成1、未知0，stage 2 receipt缺失。此为此前已认证状态，本批没有运行新runner重验。V1报告未变。认证历史子集33、未知0，政策预留7、规划40沿用已有报告；旧confirmation实际消费和全部历史实际累计仍为null。未认证的新消费/unknown统计保持null。旧六槽继续封存。

`target/curry-ledger-handoff-v2-tests/`保存全套测试日志、文件清单、合成材料、审阅和本次静态根因复核。V2正式目录已由失败报告和构建文件占用，不得清空、改名或覆盖。文档定稿后的完整源码归档、目录清单及完整性记录只存于忽略的`target/curry-ledger-handoff-v2-tests/final-source-release-doc-final/`；证据体积见`target/curry-ledger-handoff-v2-tests/evidence-size-release.json`。体积清点记录了`target/curry-ledger-handoff-v2-tests/tmpaeo1xiqn`的`PermissionError`，该ACL受限目录原样保留。

## 后续安全边界

若后续另行继续，需先制定新的版本化计划和新的独占输出路径，核实并修正前次V1 runner角色绑定，明确将“原缺陷源码归档”与“V1审计工具归档”分开绑定，并补齐新版本合成公共入口和独立审阅。旧V1/V2报告必须只读保留；不得通过预置成功布尔值、跳过来源链、把失败推定为零消费或复用封存槽位来推进。

本批新增原生调用为0；四项资格保持false。不切换部署/active资产，不提交或推送Git。
