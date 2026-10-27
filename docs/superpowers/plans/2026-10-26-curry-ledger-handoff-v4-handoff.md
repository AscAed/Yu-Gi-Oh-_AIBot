# Curry V4精确输出合同与零调用验收：断点交接

日期：2026-10-26

## 当前结论

V4精确stdout合同、真实结构合成来源链、兼容回归、全量Python测试及独立只读审阅均通过。唯一一次真实V4只读审计在`previous_v3_failed_source`最早门禁失败后停止；保存输入runner没有启动，新增原生调用为0。本批没有创建scope、窗口或收费账本，也没有运行worker、FFI、doctor或真实normal。

真实审计报告保存在[`audit-report.json`](../../../data/runtime/p1-curry-ledger-handoff-v4-offline-2026-10-26/audit-report.json)，SHA256为`02f69485390c98cec677da83d3e9df3df70ffb9f238d38d3e8acf861968bad05`，5,522字节。报告通过V4运行时合同与JSON Schema，状态`failed`，`failure_checkpoint=previous_v3_failed_source`，稳定诊断`curry_handoff_build_root_contents_invalid`，`native_calls=0`、`runner.process_attempted=false`；后续检查均为`not_run`。

## 失败门禁与不可重试边界

固定V4审计根要求在调用前严格只含`native-artifacts/`、`build-record.json`、`source-native.zip`和`source-native-file-list.json`。本批隔离构建时在该根下另外留下`build-target/`和`build-command.json`，故参数/来源门禁拒绝继续。审计报告是门禁失败后保存的固定输出。原Stage 2 runner未启动，固定stage 2 input/prepared未被送入进程。

本批计划只允许一次真实审计；因此不得删除、移动或改名根内材料后重跑，也不得覆盖`audit-report.json`。若未来另行授权续作，应先制定新版本/新输出根的计划，重新定义构建目录布局和来源锚点；不得把本次失败称为Stage 2的审计结果或执行结果。

## 实施与验证

- V4增加独立`verification-accounting-v1`stdout合同，仅由V4来源配置启用。手写14字段期望包含成功状态、一次消费、六字段账本、固定历史32/预留7/规划39/预留ID与政策，以及结算后的33/40/unknown0；旧confirmation和全部历史实际累计保持null。其他scope继续使用旧三字段合同。
- 完整合成公共入口覆盖V4来源、stage 1父收据、stage 2派生、真实账本/blob解析、只读进程边界、报告保存与保存后校验；生产门禁未被合成成功标志、任意profile或绕过函数替代。
- V1–V4聚焦兼容集115项通过。显式枚举73个顶层Python测试文件，全套为614通过、9跳过、0失败，166个subtests通过，用时1,141.41秒。完整日志与清单位于`target/curry-ledger-handoff-v4-tests/`。跳过为两个Windows目录符号链接能力限制、v3/v4报告及快照/完整策略opt-in、本机引擎资产缺失、独立2026赛事资产配置缺失；逐项明细见pytest `-ra`日志。
- Rust/Cargo 159项集合与V3最终认证清单相同（151项Rust/Cargo源码、8项生成证据），本批未改动，引用既有格式、全目标Clippy及workspace 380通过/37忽略验证，没有重复运行Cargo总检。
- 独立审阅确认V4合同仅在V4路径使用，预留与会计字段绑定正确，V3合成runner语义保持原有，成功报告保存时使用V4根。

## 审计时点资产与旧scope

审计源码身份为`a6fe4f17ffa0b3a030681d9c78b6e70c39263a45e89a18466e80cb62c72c7ae7`，568项；原生源码ZIP SHA256 `bc73f2d8216c9553435844ed15f6b3845b60d898de57df9508fe8215abd55edb`，清单SHA256 `bad195d2875c7eb4a13bce054c18a83393e068308ba037de6cc291763394b1d3`。隔离runner SHA256 `e92ff677fb10045acef6222c7ffac1ca73959b50502aa54b3cbd937959ec3853`，构建记录identity `0cc8debbddba41dd50dd0c96004f5c12a4c3a8e214bfdbaa8b5a5a651f70586e`；仅构建，未运行。runner构建输出与审计根中额外`build-target/`、`build-command.json`的具体清单保留在忽略交付目录。

冻结Stage 2输入SHA256为`b144701eeceafd8c8d7e827c7e6823213e401614f46488a9e3564c2735f604b8`，prepared SHA256为`7f94f982f89ca1c2b720f32250f8e4f9451ec0eb99ba5a4afcec7dd7fc23c5ee`；本批未启动runner核验。V4报告中`stability.ledger_stable=not_checked`。本轮结束后的独立只读SHA保护检查与原账本SHA256 `7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`一致；本批没有打开或改写账本。Stage 1此前认证消费/完成1、unknown0，Stage 2收据缺失。

认证历史子集32次、政策预留7、规划基数39保持来源口径；原scope实际仍仅有已认证Stage 1消费1次。旧confirmation实际消费和全部历史实际累计继续为null。V4本批原生调用为0。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均为false。

## 文档后交付

最终文档完成后，V4审计时报告、runner、构建记录和原生源码归档均保持原字节。权威文档后交付记录为`data/runtime/p1-curry-ledger-handoff-v4-offline-2026-10-26/final-build/delivery-final.json`；文档后源码身份、独立归档/清单及体积清点位于V4忽略目录的`final-build/`。它们不改变审计时源码绑定，也不给未启动的runner补发资格。体积遍历中的访问错误按记录保留，不调整ACL。

旧V1、V2、V3失败报告及scope窗口、剩余六槽、部署和active资产保持不变。本批结束后暂停；不提交或推送Git。
