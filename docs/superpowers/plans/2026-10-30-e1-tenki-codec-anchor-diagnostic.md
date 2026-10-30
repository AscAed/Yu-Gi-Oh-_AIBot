# E1：Tenki `codec.rs` 历史保护锚点只读诊断

## 结论

E1 的只读追溯已完成。原历史 pin 和失败记录均未修改。现有材料确认 Tenki 专属归档反复保存了 `codec.rs` 的 `224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e`；Ground Collapse 工具包的 11 成员 ZIP 含有 `e8f97eefcf93ef626d2ecbc785661fde2fee47b0525e110ec7aee9a185aad133`。但没有来源链证明该 Ground Collapse 工具文件是 `curry-option-validation-v1` 某次实际执行所用的源码。因此，Curry 迁移中的 `224… → e8…` 可作为候选代码演进，不能认证为该 scope 的历史执行迁移。

当前 `codec.rs` 原始工作树字节 SHA-256 为 `62339e567426a4d37b95d39790b71ce1acad13e75faab9df8596bafb5e577e68`。当前文件是 CRLF；按 Git checkout 规则规范化为 LF 后与 HEAD 内容相同。该原始文件哈希差异不代表本地未提交的源码语义修改。

## 固定现场与原失败

- 分支：`codex/ci-language-review-selfcontained-20261029`；HEAD：`533bbd9224cc11946812939ca611669444f6bcbf`。
- 开始与收尾检查中，`codec.rs` 工作树 SHA-256 为 `62339e567426a4d37b95d39790b71ce1acad13e75faab9df8596bafb5e577e68`。`git status` 未报告该文件修改；当前文件按 CRLF→LF 规范化后与 HEAD 中该文件字节相同。
- 保留的本机 C1 Python 全套记录为 759 项：749 passed、9 skipped、1 failed；唯一失败是 `tests/test_native_tenki_placement_confirmation.py::test_seven_historical_ledgers_reaudit_read_only_without_runner`，错误 `protected_source_change_hash_mismatch`。它来自该测试对 `curry-option-validation-v1` 迁移映射的检查，不是本轮重跑结果。
- 源码中的 `CURRY_SCOPE_PROTECTED_SOURCE_CHANGE` 固定 `scope=curry-option-validation-v1`、路径 `crates/ygo-engine-adapter/src/codec.rs`、旧值 `224…`、新值 `e8…`。未修改该映射或测试。

## 归档核对

以下 ZIP 成员通过 SHA-256 重算，并与各自同目录 `source-native-file-list.json` 声明一致。它们证明相应归档包含该字节版本，不单独证明运行时使用该版本。

| 来源 | ZIP SHA-256 | 文件清单 SHA-256 | 清单文件数 | `codec.rs` 成员 SHA-256 |
|---|---|---|---:|---|
| Tenki confirmation 原生归档 `data/runtime/p1-tenki-placement-confirmation-native-2026-10-22/source-native.zip` | `a4c85682032597f1fe512a8c59eea498c8426b7f25e9f61b736f57051da55801` | `48d4477b91d6bbf70d54722f4849378599706e7d52dcd036c634e5a2e3a6f3fe` | 510 | `224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e` |
| Tenki confirmation 文档后归档 `data/runtime/p1-tenki-placement-confirmation-native-2026-10-22/final-build/source-native.zip` | `0bda44e2a69e0e450a022786e9065411d6f39199df4d2c5f99de883c53833a2c` | `7354006bc4e72b9e8660c6c4d2caeb04d9563bc6e0af737587330587afd46981` | 511 | `224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e` |
| Tenki confirmation preflight-1 `data/runtime/p1-tenki-placement-confirmation-native-2026-10-22/preflight-attempt-1/source-native.zip` | `3f389c3c31f2104c2846b5103d05917aef05719211541a461d9e87989a5d4951` | `d8234eeb787e0287b2864ab2893786c285217480c9500321a9ac24192ccd9eb4` | 510 | `224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e` |
| Tenki placement validation 原生归档 `data/runtime/p1-tenki-placement-validation-native-2026-10-23/source-native.zip` | `8c8c5d676d34ae03161491cd0a6dcedd5cc7c47d5ed2ecabdfbf4231c6e34e7e` | `fd02e8e722a38b0edfdfc0058c9d4007f1059edfe3c641c8b4a2774a00939653` | 683 | `224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e` |
| Tenki runner-repair 原生归档 `data/runtime/p1-tenki-runner-repair-offline-2026-10-23/source-native.zip` | `8e0565d8ea474198e6a76d839b7b50324891128fc20ce8c0f4e2d8cc7a6f302a` | `108aa3ccd29ab9117ad568a403dcdb3f01b97747f8a1b2ba830c95745f5d4bb7` | 534 | `224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e` |
| Tenki runner-repair 文档后归档 `data/runtime/p1-tenki-runner-repair-offline-2026-10-23/final-build/source-native.zip` | `87771094a6c6680096210e9e4e50efb68dc708d53e2f9982e0e0c982959f873d` | `ef1a6d1ef25fd770e608f58238c67739416bf37f370ab316dcd2a4a62a22bd3b` | 534 | `224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e` |
| Tenki diagnostics 文档后归档 `data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22/final-build/source-native.zip` | `db9f22e75c06b183578c710b4d9ee0a9c97e0c2032bf240197a1795ea9211595` | `93277504373eb87a2b4bdb33ee3b76c418a75ef9d98e1888144ab65b798ee755` | 459 | `224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e` |
| Ground Collapse preparation 工具包 `data/runtime/p1-ground-collapse-preparation-offline-2026-10-27/source-native.zip` | `acba1482356619bbf95626bb56200a3420faf372f645d11434d562eb3aeca3cd` | `ee12e0e898c4cf9ebce6d81d4b620f80d9df01fb96784bb9f2eeb17d06f44bee` | 11 | `e8f97eefcf93ef626d2ecbc785661fde2fee47b0525e110ec7aee9a185aad133` |

Ground Collapse `preparation.json` SHA-256 为 `5354438945079d9df4f2867e272e2420d71605909c772f0a874b6c21b8319d74`，状态为 passed；其工具包字段绑定上述 11 项 ZIP/list。报告另记录工作区元数据：602 项、identity `c96a9e5ec6e6aef5a24cf218b11cc18140be01cdbd4fd4e95d59ab12deee8862`，但 `workspace_identity_status=historical_capture_metadata_not_reauthenticated`。冻结缓存元数据也记录 602 项、无缺失、同一 identity；其缓存归档 SHA-256 为 `70cda05d86ac361172afdc209dc14d785e526d121dc3874c23039e3590a303fe`，清单 SHA-256 为 `fc23e6fba0205eda569147ba8e91979508dc044b6f0899033d835cd9b90a99fe`。这些记录绑定 Ground Collapse 工具冻结，未把 `e8…` 绑定到 Curry scope 的 runner 调用。

对上表每份归档，均独立重算 ZIP 哈希与清单哈希，并确认清单中的 `codec.rs` 哈希等于 ZIP 中唯一同路径成员的重算值；表中的文件数取自清单，没有在本轮逐个重算所有其他成员。placement validation 的指定 `final-build/source-native.zip` 文件不存在，故未把该路径计入结论。未将目录清单或相似哈希当作内容备份。

## 字节差异与时间顺序

按文本换行规范化逐行比较：

1. `224…` Tenki `codec.rs` 到 `e8…` Ground Collapse 工具成员的差异，是新增 opcode 92（`RECOVER`：player 与 u32 amount）和 opcode 56（`FIELD_DISABLED`：u32 disabled mask）的解析分支。
2. `e8…` 到当前工作树 `6233…` 的语义差异，是 `frame_matches_raw` 新增对历史 opcode 56/92 未解析帧表示的兼容读取；它允许旧报告保留 `{"unparsed":true}`，不会改写为当时已解析字段。当前文件对 Git HEAD 的差异只涉及 CRLF checkout 表示，规范化后内容相同。
3. Git 可见的相关提交 `990f68820d5d48c4dc2d6f675fb11ba225f093f3` 记录于 2026-10-28 00:15:12 +08:00，提交说明为 `chore: complete workspace audit and documentation refactor`，其 `codec.rs` 变更包含协议解析/历史帧兼容演进。Ground Collapse 工具准备记录日期为 2026-10-27。该时间顺序与代码差异相容，但不能证明任何 runner 实际加载了某个归档成员。

因此，C1 测试比较的是固定 Curry scope 迁移值与当前保护映射；单项失败意味着该迁移保护断言没有通过。它不自动否定 Tenki ZIP 中独立绑定的 `224…` 文件、各自的构建/收据/账本或其他已认证证据。那些证据的有效性仍由各自完整来源链决定。

## 来源状态与后续建议

| 结论 | 状态 |
|---|---|
| Tenki 归档中的旧 `codec.rs` 字节为 `224…` | 已由清单与 ZIP 成员双重核验 |
| Ground Collapse 工具包中的新解析器字节为 `e8…` | 已由工具包清单与 ZIP 成员双重核验 |
| `224… → e8…` 的代码差异 | 已静态核验，为新增 opcode 56/92 解析 |
| `e8… → 当前工作树` 的代码差异 | 已静态核验，为旧帧表示兼容逻辑；当前 raw `6233…` 含 CRLF |
| `e8…` 是 Curry `curry-option-validation-v1` 实际执行源码 | 未认证；缺少绑定该 scope、请求、runner/build 与实际调用的来源记录 |
| 历史执行实际退出码、当前源码导致旧执行结果变化 | 未认证；本批未重新执行测试或 runner |

建议后续单独制定 pin 处置与回归：优先从 Curry 自身认证的原生源码归档、构建关联和请求/收据链恢复适用字节；若材料无法建立迁移来源，则新增明确版本/来源角色的兼容读取合同，并分别测试“历史报告绑定旧源码”和“当前解析器读取旧帧”。不要仅把新值改为 `6233…`，也不要把 Ground Collapse 的工具哈希自动复用为 Curry 迁移授权。

## 检查范围与保留边界

本轮使用本地只读文件、ZIP 成员、SHA-256、Git 元数据/对象及文档内容核对；未运行 pytest、Rust 测试、构建、runner、worker、FFI、doctor、资产扫描或收费入口。没有修改 `codec.rs`、历史 pin、报告、归档、清单、账本或 ACL。导航与记录文档的链接及差异检查结果见 `docs/TESTING.md` 的 E1 条目。

递归列举 `data/runtime` 时出现访问拒绝，扫描不完整；观察到的相对路径包括 `data/runtime/curry-confirmation-archive-qn_cv8nj/`、`data/runtime/tenki-runner-audit-hpcytu5b/`、`data/runtime/validation-guard-krjjnq6e/`、`data/runtime/p1-tenki-placement-validation-native-2026-10-23/target/synthetic-workflow-tests/run-qqyo247j/` 和 `data/runtime/tenki-confirmation-tests-target/tmp/tmprv2su_kh/`。未改变权限、删除或清理任何证据。完整资料清点仍不完整。
