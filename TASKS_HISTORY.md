# 实施任务与验收状态

## 当前状态（2026-10-27）：P1局部研究与产品工作台双轨

这是当前状态和开放任务的唯一入口。产品目标、研究定义及阶段依赖分别见[产品愿景](docs/PRODUCT_VISION.md)、[最优性研究](docs/OPTIMALITY_RESEARCH.md)和[路线图](docs/ROADMAP.md)；本次文档重整与具体小批任务见[项目再规划](docs/superpowers/plans/2026-10-27-project-realignment.md)。下方各批历史数字仅适用于其日期和范围，不覆盖本节。

| 阶段 | 当前能力与未完成门禁 |
|---|---|
| P0 | 首批身份、构建记录、清点与输入工具已交付；全正式OCG发行分母及依赖证据未完成 |
| P1 | P1.1协议、观察、局部原生案例和证据工具已推进；P1.2完整小问题尚不可进入证明，完整动作、真实概率、循环和独立值界仍缺 |
| P2 | 39卡中文候选及来源已调查；名称/正文语义、简繁、别名、字段和使用依据未通过，中文检索/更新服务未交付 |
| P3 | 草稿、编辑、YDK/JSON导出和本机浏览器未交付；可与研究线独立推进 |
| P4 | 仍在R1，真实执行安全续跑未完成；R2–R5门禁均未通过 |
| P5–P6 | 指定profile知识和有限关联已有；通用知识、主题识别、自动构筑与评估反馈未交付 |
| P7–P8 | 指定灰流丽场景有局部证据；通用干扰、全卡覆盖、最优性证明及可分发产品未交付 |

最近Ground Collapse opcode24批次只完成离线协议、合成oracle和固定来源准备，**新增native/runner/worker/FFI调用均为0**；`execution_ready`、原生可达、响应接受及完整性/概率/最优性资格均为false。13/14已有各自冻结案例的部分原生分支和独立重放；24实际提示、掩码及响应接受仍未知，详见[本批交接](docs/superpowers/plans/2026-10-27-ground-collapse-preparation-handoff.md)。

最新可认证会计口径为**认证消费子集40、政策预留7、规划47**；旧confirmation实际消费和全部历史实际累计仍为`null`。旧窗口和槽位依各自scope封存；新增原生实验必须另定范围、预算和窗口，不能直接执行既有准备报告。

### 当前开放任务

- [x] 完成本次纯文档定位、研究规范、证据规范、历史导航和双轨阶段计划；核对记录见[TESTING](docs/TESTING.md)顶部。
- [x] 2026-10-27环境自检：区分部署包与开发资产，清理229个已确认空测试目录，整理pytest缓存及冗余直接依赖；范围和验证见[TESTING](docs/TESTING.md)。
- [ ] A1 / P4-R1a：用零原生的聚焦回归复现并处理首次结果级错误/查询捕获失败与诊断验证器可能不对称；目前仅有静态代码证据，尚未声称已实跑复现。
- [ ] B1 / P3.1：交付可保存草稿及主/额外/Side编辑、YDK/JSON导入导出往返，区分草稿状态与完整合法性。
- [ ] B2 / P3：在B1上建立最小本机中文浏览器工作台，未知卡或缺译明确提示；不等待P1完整证明或P2全部中文资料。
- [ ] C1 / P2.1：核验既有39卡中文名称、正文、别名、字段及使用依据；不因候选存在授予正式语言资格。
- [ ] A2 / P1：为单一研究阻断项设计下一小实验；Ground Collapse是可选候选，另定scope/预算并另行确认后才可执行。
- [ ] A3 / P4-R1b：完成真实执行进度持久化、安全检查点及端到端暂停/重开；失败、未知消费和实际前缀分别留证。
- [ ] A4 / P1：每批选择信息投影、条件概率、动作顺序、自然结束或循环中的一个缺口验收；不能只增加成功线路。
- [ ] P4-R2：86项场景内规则完整语义与逐项原生认证；现有12项成对规则、1项实际Scythe灰点，仍缺74项规则资格。
- [ ] P4-R3：正式v6规划/报告/CLI及v1–v5完整兼容回归。
- [ ] P4-R4：冻结独立人工基准，完成16+32手可续跑评估及汇总验真。
- [ ] P4-R5：最新源码和双资产独立干净checkout部署、doctor、重放与身份/账本比较。
- [ ] P0/P1/P5–P8：全卡发行分母、完整信息/概率与证明、通用知识/构筑反馈及最终产品验收，按阶段依赖继续。
- [ ] M1：比较研究关口与工作台用户流程的实际改善，按成本与证据选择下一个独立小批。

前次交付后的603项源码归档身份、原生时点身份和普通dist是不同对象；后续文档、pytest配置和Cargo依赖整理已改变工作区，不再声称其与该归档完整逐字一致。实跑与静态核对分别见[TESTING](docs/TESTING.md)，历史导航见[HISTORY_INDEX](docs/HISTORY_INDEX.md)。

## 历史状态（2026-10-27）：Ground Collapse opcode24离线准备通过

**Ground Collapse opcode24的离线协议支持、公开选区准备、合成验收及固定来源准备/verify均通过；本批完成并暂停。**新增原生、真实runner、worker及FFI调用均为0，没有创建scope、窗口或收费账本，也未切换部署、active资产或Git提交状态。

Rust decoder新增opcode56 `FIELD_DISABLED` 的严格5字节解析`[56,u32 LE]`，只输出`disabled_mask`，拒绝截断和尾部。独立Python oracle直接解析opcode24、HINT_ZONE及FIELD_DISABLED原始帧，绑定掩码、菜单坐标、Choice和响应字节。固定公开规则为唯一激活90502999；若出现opcode18则按唯一坐标`0/8/0`响应`[0,8,0]`；opcode24按序选择`1/4/0`、`1/4/1`，响应`[1,4,0,1,4,1]`，缺失/重复/不可用时停止。45个规范组合及90种有序编码仅为合成或静态结果；反序编码保持可区分，原生接受与顺序等价未验证。

真实离线准备报告为[`preparation.json`](data/runtime/p1-ground-collapse-preparation-offline-2026-10-27/preparation.json)，SHA256 `5354438945079d9df4f2867e272e2420d71605909c772f0a874b6c21b8319d74`（25,131字节）。六项检查全部通过，固定Curry delivery、11份历史账本保护、冻结候选、CDB/禁限/脚本/核心和输入稳定性均通过；会计沿用认证消费40、政策预留7、规划47，旧confirmation消费及全部历史实际累计仍为`null`。报告`execution_ready=false`，所有证明、原生可达、响应接受和完整性资格均为false。真实命令于2026-10-27退出0、耗时357.287秒，stdout单一JSON（180字节，SHA256 `acfebec454437161277b74741ef5f192f651817f5bfa70f387a73b4339f86920`），stderr为空；零调用verify于文档前退出0、耗时313.189秒，`valid=true`，stdout 130字节、stderr为空，报告哈希保持不变。原始进程字节和状态保存在`target/ground-collapse-preparation-tests/real-prepare-attempt-final/`及`verify-before-docs-final/`。

收窄输入捕获缓存后，聚焦组44 passed、19个子测试通过；完整Python全套显式枚举88个顶层测试文件，734 passed、9 skipped、200个子测试通过、0失败，用时1,695.86秒。9项跳过逐项见[测试日志](target/ground-collapse-preparation-tests/pytest-full-after-cache-tightening.log)：两项Windows目录符号链接能力限制，以及v3/v4报告、本机引擎资产、本地快照/报告、真实v2报告、完整策略和独立2026赛事配置各自opt-in/缺少材料。Rust未在最后Python缓存优化中改动；本批Rust修改的既有隔离验证为fmt与全目标Clippy通过、workspace 382 passed/37 ignored、examples 52 passed/1 ignored；逐项忽略原因见[workspace日志](target/ground-collapse-preparation-tests/workspace-tests-serial.log)和[examples日志](target/ground-collapse-preparation-tests/adapter-examples-tests.log)，唯一examples忽略依赖固定历史genesis证据。独立审阅确认解析/选择及输入缓存保护无阻断发现。

该批文档前工具源码身份`c96a9e5ec6e6aef5a24cf218b11cc18140be01cdbd4fd4e95d59ab12deee8862`、602项；源码ZIP SHA256 `70cda05d86ac361172afdc209dc14d785e526d121dc3874c23039e3590a303fe`、文件清单SHA256 `fc23e6fba0205eda569147ba8e91979508dc044b6f0899033d835cd9b90a99fe`。文档定稿后的源码归档、只读verify及访问失败清单由[外部交付记录](target/ground-collapse-preparation-tests/final-release/delivery.json)绑定；详细续接见[本批交接](docs/superpowers/plans/2026-10-27-ground-collapse-preparation-handoff.md)。正式报告只用于离线准备，不能直接启动原生实验；未来opcode24发现、响应接受及独立重放必须另立scope和预算。发行依据、原生可达性及`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`继续未通过。

## 历史状态（2026-10-27）：绑定V3恢复证据的Curry七阶段再验真

**固定Curry revalidation scope七阶段、两个分支独立重放、全套验收及只读verify均已通过；本批完成并暂停。**scope `curry-option-revalidation-v1` 共消费并完成7/7次，unknown=0；窗口起点为2026-10-27 00:24:49 +08:00，normal总流程耗时954.67秒。旧scope槽位继续封存；未运行终场、求解器、其他提示实验、doctor或48手评估，不切换部署/active资产，不提交或推送Git。

V3基线delivery/recovery哈希分别为`dbc0db354846fdc772305970c90f7dbcee0d10804aded678845dd7bdaffd7a55`及`69d2af394169d5773394e775718840ef9a3df22eac12167d2e7ba3c79484c468`。固定预留ID为`09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63`。原认证历史33、政策预留7、规划基数40；加入本scope后认证子集为40、规划总数47。旧confirmation消费与全部历史实际累计仍为`null`。

七阶段结果：stage 1唯一识别58074572命令5激活；stage 2到opcode 18；stage 3按`0/8/0`响应`[0,8,0]`并发现opcode 14；stage 4选项0响应`[0,0,0,0]`、RECOVER player 0/200、LP `[8200,8000]`；stage 5独立重放一致；stage 6选项1响应`[1,0,0,0]`、RECOVER player 1/200、LP `[8000,8200]`；stage 7独立重放一致。各阶段收据成功、响应oracle匹配、unknown=0。总summary位于`data/runtime/p1-curry-option-revalidation-native-2026-10-26/research/summary.json`，SHA256 `fcc3d1aebe8b97f6c954a56593c86461afd7b71613669e47c6c8e1ba0e0d9098`。

prepare-only新增消费0。normal外层命令退出0，raw stdout 3,559字节，SHA256 `3b64fad1a14845c92e8a422fa509d186fa4e74a0238d9d92d6362bf2b3d6e4fd`，stderr为空；诊断保存在`target/curry-option-revalidation-tests/normal-execution-640ec24fca2d4262953d742672b9d0e0/`。七阶段只读verify-only返回`valid=true`、native_calls=0、消费7/完成7/unknown0；原始stdout和状态保存在`target/curry-option-revalidation-checks/0efeaf7cfe5041eaa809120c356f70fc/`。来源复核和89项保护映射复验通过。完整阶段、构建、来源和限制见[本批交接](docs/superpowers/plans/2026-10-27-curry-option-revalidation-handoff.md)。

Python聚焦组66 passed、37 subtests passed；公共CLI合成E2E 1 passed。显式枚举84个顶层Python测试文件的全套结果为685 passed、9 skipped、181 subtests passed、0 failed。Rust fmt、全目标offline/locked Clippy、串行workspace及examples均通过；具体计数、逐项跳过/忽略原因和日志见`docs/TESTING.md`。独立只读审阅无阻断发现，唯一P3测试临时目录偏差已在交接记录。

本批仅证明冻结Curry前缀的区域选择、opcode 14两个分支、RECOVER/LP及各一次独立重放，不证明完整线路、发行资格、全部动作覆盖或最优性。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均保持false。下一工作需另定目标、scope与预算；本批交付后暂停。

## 历史状态（2026-10-26）：Curry V3真实来源角色适配与零runner恢复

**V3精确来源角色修复、公共合成验收、全量Python测试、独立审阅、真实纯Python恢复及只读verify均通过。**本批新增原生、runner、worker、FFI调用均为0；未构建、未扫描实时资产、未创建scope、窗口或收费账本。

显式枚举81个顶层Python测试文件并运行完整套件：671 passed、9 skipped、0 failed，用时1,461.55秒；`-ra`跳过原因保存在`target/curry-ledger-handoff-recovery-v3-tests/python-full-suite-v3-final2.log`，文件清单为`pytest-files-v3-final.txt`。之后新增的发布绑定断言聚焦复验为2 passed（1.68秒）。9项跳过分别为Windows目录符号链接不可用2项，v3/v4报告、本地引擎资产、本地快照/报告、真实v2报告、完整策略报告及独立2026赛事配置opt-in或未提供。Rust/Cargo的151项与V2最终源码清单逐项一致（140个`.rs`、11个Cargo文件；新增、缺失、哈希变化均为0），本批未修改Rust/Cargo，引用已通过的fmt、全目标Clippy及workspace 380 passed/37 ignored结果。

V3恢复报告[`recovery-report.json`](data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26/recovery-report.json) SHA256为`69d2af394169d5773394e775718840ef9a3df22eac12167d2e7ba3c79484c468`（51,891字节），状态`passed`、`valid=true`，9个检查点全部通过。报告含187个唯一输入角色：原V5 164项、V3预留100项、V1/V2失败来源各6项、5项恢复锚点及6项原scope blob角色；别名及固定后缀通过合同复核。恢复工具身份为`56f967190b3333f8bd0d5b323577149c577e1c34bbb6b158ba7c013e33a8cc31`，当时工作区身份`b84db687415eb990692e19c4385443e08ab478f9b5160d2cc11a9b44f1899954`（588项）。原V2错误角色集合与真实报告差异被记录，没有执行旧归档代码。

真实V3命令仅运行一次，纯Python进程退出0，耗时35.54秒。CLI stdout原始字节51,891、SHA256 `6c1da8f3207603cee38202323c37e77ff1fdc893b7bad40cc296956e21645cf7`，stderr为空、SHA256为标准空流哈希；退出及原始输出保存在`target/curry-ledger-handoff-recovery-v3-tests/real-recovery-attempt/`。报告重新认证原scope为消费1、完成1、未知0、额度7；历史子集32、含该scope为33、政策预留7、规划40。旧confirmation实际消费及全部历史实际累计均保持`null`。stage 2收据仍缺失，未改变既有stage 2失败结论。

真实恢复后只读verify返回`valid=true`、187项输入；报告SHA256前后均为`69d2af…84c468`，正式V3输出树未变，工作区身份前后稳定，`native_calls=0`、`runner_process_calls=0`。verify原始输出和元数据在`target/curry-ledger-handoff-recovery-v3-tests/verify-only-attempt/`。文档定稿后的再verify及最终源码归档/交付清单见[最终交付记录](data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26/final-build/delivery-final.json)；续接说明见[本批交接](docs/superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-v3-handoff.md)。四项资格仍为false；部署、active资产和Git提交状态未改变。

## 历史状态（2026-10-26）：Curry V2精确来源恢复与零runner验收

**离线总检及独立审阅通过；唯一一次真实纯Python恢复已保存V2失败报告，停止于`scope_ledger_semantics`来源角色覆盖门禁。**本批新增原生调用、runner进程、worker、FFI调用均为0；未构建、未扫描实时资产、未创建scope/窗口/收费账本，也未运行doctor。失败后没有verify-only、重试或改写旧材料。

V1/V2聚焦集33 passed（144.74秒），包括V1兼容、V2公共成功/失败合成路径和文档变化后verify。显式枚举80个顶层Python测试文件后，全套为655 passed、9 skipped、166 subtests passed，耗时1,311.87秒；清单和`-ra`日志分别为`target/curry-ledger-handoff-recovery-v2-tests/top-level-python-test-files.txt`、`target/curry-ledger-handoff-recovery-v2-tests/pytest-full.log`。9项跳过：Windows目录符号链接能力2项；v3报告、v4报告、引擎资产、本地快照/报告、真实v2报告、完整策略报告、独立2026赛事配置各为opt-in或缺少环境材料。Rust/Cargo本批未改动，151项源清单沿用此前核验，引用既有fmt、全目标Clippy及workspace 380 passed/37 ignored结果；未重跑Rust。独立只读审阅未发现阻断。

唯一真实恢复报告位于[`recovery-report.json`](data/runtime/p1-curry-ledger-handoff-recovery-v2-offline-2026-10-26/recovery-report.json)，SHA256 `7496f981438bdca15f768eb38c6402cf15cc8ff88401d661fae7ee554dc476d6`（47,789字节）。报告通过V2工具包内7成员schema和运行时合同，`status=failed`、`valid=false`、`failure_checkpoint=scope_ledger_semantics`、`diagnostic=recovery_success_input_set_incomplete`；之前的来源、冻结输入/父链及保存进程证据检查通过，稳定性和发布成功路径未运行。失败报告记录181条输入角色，但实际冻结V3来源为`v3_source_workspace_identity`，当前固定allowlist要求`v3_source_confirmation_summary`；其余181项集合门禁未能匹配。失败统计保持null，未将预留计为消费，也未发布33/40。报告内V1失败源status/checkpoint/diagnostic及真实V5 delta均正确；V1失败报告SHA256 `bf85a81f7d6a204e4a960b2ffb8449e2f1a17d857ca5fcf7e5e2303f5285270d`与V1 delivery `154d77cb4c8790cd971e19dbd17dcc8a4417df1e0f460747948e306706328e2e`均通过绑定。

真实命令退出码2；已先保存原始stdout/stderr：`target/curry-ledger-handoff-recovery-v2-tests/real-recovery.stdout.bin`为77字节、SHA256 `552d1bcfa2ba3ae2837fae98bc70105acb8c5ff3f79622bf92883dbfca54ba27`，stderr为空、SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。V2工具归档7成员及清单通过复核，报告SHA256与归档schema匹配。禁止再次运行固定V2恢复；失败报告不执行verify-only。

恢复前后只读检查确认V5 delivery锚点`3c689f9ae6860da3b42a0ea4f6f0e5e3b100fdc2c548f91f2e288268bd071278`、V1失败报告/delivery、原scope账本SHA256 `7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`均未变；stage 2输入/prepared仍为`b144701eeceafd8c8d7e827c7e6823213e401614f46488a9e3564c2735f604b8`和`7f94f982f89ca1c2b720f32250f8e4f9451ec0eb99ba5a4afcec7dd7fc23c5ee`，stage 2收据仍缺失，V5正式audit report仍缺失。既有认证子集32、政策预留7、规划39仅沿用先前证据，本报告未重新认证原scope消费；旧confirmation及全部历史实际累计仍为`null`。四项资格保持false。具体续接见[本批恢复交接](docs/superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-v2-handoff.md)。

## 历史状态（2026-10-26）：Curry V5已存证据恢复与报告发布诊断

**报告发布诊断修复、七行账本恢复器、完整公共CLI合成验收、Python全套测试及独立审阅通过；唯一一次真实纯Python恢复在`v5_delivery_and_archives`首门禁失败，本批按一次尝试规则暂停。**本批新增原生调用、runner进程、worker及FFI调用均为0；不运行doctor、实时资产扫描或旧V5审计，也未创建新的scope、窗口或收费账本。

Python聚焦恢复/审计/公共CLI回归为48 passed（70.85秒）；显式枚举79个顶层测试文件的完整套件为651 passed、9 skipped、166 subtests passed（1,276.76秒）。最终日志与清单见`target/curry-ledger-handoff-recovery-tests/pytest-full-final2.log`及`top-level-tests-final.txt`，`-ra`跳过明细保存在日志中。独立只读审阅确认来源身份交叉绑定、输出根创建失败诊断、来源重建失败分类，以及写后复验失败的`written_unverified`状态和候选报告哈希均正确。Rust/Cargo本批未改动，引用既有fmt、全目标Clippy及workspace 380 passed/37 ignored记录；本批没有重跑Rust。

唯一恢复报告为[`recovery-report.json`](data/runtime/p1-curry-ledger-handoff-recovery-offline-2026-10-26/recovery-report.json)，SHA256 `bf85a81f7d6a204e4a960b2ffb8449e2f1a17d857ca5fcf7e5e2303f5285270d`（3,891字节），通过Python合同和v1 JSON Schema；状态`failed`、`valid=false`，首个检查点`v5_delivery_and_archives`，稳定诊断`recovery_v5_source_delta_invalid`，其余六项检查均`not_run`、`inputs=[]`。因此本报告的原scope统计及其派生总数保持`null`；没有发布33或40，也没有运行`--verify-only`。工具归档、清单已随报告保存在恢复目录，恢复工具身份`9b29faec4ac18ba8cdb718a7cba5a5efe637759a98f027044954baf5f2a02078`。审计时工作区身份为`d2307e164d2a949841f79a90715e12108b4c17b24be1275b37ea6a4700f4ddcf`（582项）。

真实恢复命令退出2；CLI stdout为72字节、SHA256 `9f0037a457370fe9c75b5f566d250d24d71b5e643f54c0fc91db92fc1be82f15`，stderr为空（SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`），退出记录在`target/curry-ledger-handoff-recovery-tests/real-recovery-exit.json`。启动命令前的PowerShell侧车碰撞检查表达式有语法错误，shell仍继续执行了命令；固定恢复根在之前的只读预检中确认不存在，恢复实现通过独占目录创建避免覆盖。此操作偏差不解释报告中的`recovery_v5_source_delta_invalid`，也不作为V5历史失败原因。按“一次真实恢复”门禁，不重试、不覆盖、不换目录，并且失败报告不执行verify-only。

运行后只读复核确认原scope ledger SHA256仍为`7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`，stage 2 input和prepared哈希仍分别为`b144701eeceafd8c8d7e827c7e6823213e401614f46488a9e3564c2735f604b8`和`7f94f982f89ca1c2b720f32250f8e4f9451ec0eb99ba5a4afcec7dd7fc23c5ee`，stage 2收据仍缺失。V5 delivery锚点仍为`3c689f9ae6860da3b42a0ea4f6f0e5e3b100fdc2c548f91f2e288268bd071278`，V5正式`audit-report.json`仍缺失。已认证历史子集32、政策预留7、既有规划基数39仅沿用此前证据；本次恢复未通过账本门禁，不能据此重认证原scope消费1或将基数提升到33/40。旧confirmation实际消费和全部历史实际累计仍为`null`。V5此前外层退出2仍未认证其内部异常；本次首门禁错误只属于恢复器本轮，不能倒推V5历史原因。四项资格继续false。本批断点见[恢复交接](docs/superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-handoff.md)。不切换部署、active资产或Git提交状态。

## 历史状态（2026-10-26）：Curry V5干净交付与单次零调用验收

**V5实现、合成路径、总检、独立审阅和四项隔离打包完成；唯一真实只读runner执行通过其输入检查，但外层审计命令退出2且未发布正式报告，整批验收未通过。**本批新增原生调用0；runner进程调用1次、模式为`audit_saved_input_only`，没有worker/FFI/doctor/normal，没有创建新scope、窗口或收费账本。

Python全套显式枚举77个顶层测试文件：637 passed、9 skipped、166 subtests passed，用时1,146.60秒。`-ra`跳过原因逐项记录于`target/curry-ledger-handoff-v5-tests/pytest-all.log`：两项Windows目录符号链接能力限制，v3/v4报告opt-in，本机引擎资产opt-in，本地快照/真实v2报告opt-in，完整策略报告opt-in，独立2026赛事配置未提供。V5、schema、打包及V1–V4兼容聚焦集82 passed；公共CLI合成E2E 1 passed（72.83秒）。独立审阅无材料发现。151项Rust/Cargo与V4最终清单完全一致，本批没有Rust/Cargo改动，引用已验证的fmt、Clippy及workspace 380 passed/37 ignored。

V5固定打包路径`data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26/`在审计前恰好通过四项布局检查；native runner SHA256为`2ef1a214fa16e9f4a3ba666ec614165a016eadc739a4eadcdc2c9e4cdd0338af`，构建身份`e67bd1a7d18d69777e7af29b425dfc84dc38a37fc594433ad7be17b87dae81e5`。唯一审计启动后已保存原始process-diagnostics，但`audit-report.json`不存在。外层CLI只输出`fixed source, runner, or output check failed`，内部错误被隐藏，因此不声称具体失败检查点，也不补造schema报告。runner自己的只读JSON确认父收据、公开派生、资产身份均有效，既有账本统计消费1/完成1/未知0/额度7，stage 2收据缺失；这不是本批新消费。

原scope账本仍为SHA256 `7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`。已认证历史子集32、V3政策预留7、规划基数39沿用此前证据；旧confirmation实际消费及全部历史实际累计为`null`。V5未发布报告，不将上述基数提升为33或40。本批具体失败及唯一续接点见[本批断点](docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v5-handoff.md)。固定V5目录不得重跑或覆盖；后续先修离线失败报告保存/稳定错误码，再另行设计版本化恢复。四项资格继续false，不切换部署、active资产，不提交或推送Git。文档定稿后的源码归档和交付记录见`data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26/final-build/delivery.json`。

## 历史状态（2026-10-26）：Curry V4精确输出合同与单次零调用验收

**V4精确stdout合同、公共合成来源链、回归测试和独立审阅通过；唯一一次真实只读审计在最早的`previous_v3_failed_source`门禁失败后按计划停止。**本批新增原生调用固定为0；saved-input runner未启动，未运行worker、FFI、doctor或真实normal，也未创建scope、窗口或收费账本。

Python全套显式枚举73个顶层测试文件：614 passed、9 skipped、0 failed，166个subtests通过，用时1,141.41秒。完整日志和文件清单见`target/curry-ledger-handoff-v4-tests/pytest-full.log`及`top-level-tests.txt`；V1–V4聚焦兼容集115项通过，用时288.70秒。9项跳过及逐项原因已由pytest `-ra`记录，包括Windows目录符号链接能力限制、v3/v4报告和本机资产/报告opt-in、独立赛事配置未提供。独立审阅通过。Rust/Cargo认证集合159项（151项源码与8项生成证据）与V3最终清单一致，本批未改Rust/Cargo，引用既有fmt、Clippy及workspace 380通过/37忽略结果。

唯一一次真实只读审计报告为[`audit-report.json`](data/runtime/p1-curry-ledger-handoff-v4-offline-2026-10-26/audit-report.json)，SHA256 `02f69485390c98cec677da83d3e9df3df70ffb9f238d38d3e8acf861968bad05`（5,522字节），通过V4 Python合同和JSON Schema。状态`failed`，首个检查点`previous_v3_failed_source`，诊断`curry_handoff_build_root_contents_invalid`；原因是固定V4输出根在收费/runner调用前包含审计器未允许的`build-target/`与`build-command.json`。报告记载`native_calls=0`、`runner.process_attempted=false`，后续检查为`not_run`。依照“一次真实验收”约束，不整理固定根、不重试、不覆盖；原Stage 2 runner未启动。

V4审计时源码身份`a6fe4f17ffa0b3a030681d9c78b6e70c39263a45e89a18466e80cb62c72c7ae7`（568项）；源码ZIP SHA256 `bc73f2d8216c9553435844ed15f6b3845b60d898de57df9508fe8215abd55edb`，文件清单SHA256 `bad195d2875c7eb4a13bce054c18a83393e068308ba037de6cc291763394b1d3`。隔离runner SHA256 `e92ff677fb10045acef6222c7ffac1ca73959b50502aa54b3cbd937959ec3853`，构建记录身份见本批断点和V4目录；runner仅构建。V4报告中的ledger稳定性为`not_checked`；本轮结束后的独立只读SHA检查与固定旧账本值一致（`7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`），账本在本批未被打开或修改。既有stage 1消费/完成1、未知0，Stage 2收据缺失。认证历史子集32、政策预留7、规划基数39；旧confirmation及全部历史实际累计仍为`null`。四项资格保持false。文档后归档、清单、交付及体积记录见V4目录`final-build/`，权威文档后交付记录为[`delivery-final.json`](data/runtime/p1-curry-ledger-handoff-v4-offline-2026-10-26/final-build/delivery-final.json)。续接边界见[本批断点](docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v4-handoff.md)。不切换部署、active资产或Git提交状态。

## 历史状态（2026-10-26）：Curry V3来源角色修复与只读验收

**V3来源角色修复、合成验收、全套Python测试和独立审阅通过；唯一一次真实只读审计在旧stage 1收据的输出合同检查失败，按计划暂停。**本批新增原生调用固定为0；saved-input runner未启动，没有worker、FFI、doctor、真实normal、收费账本或新scope/窗口。

顶层Python全套显式列举71个测试文件、共608项，599通过、9跳过、0失败，用时1,022.86秒；跳过原因见`-ra`日志：Windows目录符号链接不可用两项，以及v3/v4报告、本机引擎资产、快照/实际v2、完整策略和独立赛事配置opt-in。代码最后一次聚焦复跑48项V3合同/E2E全通过。151项Rust/Cargo源文件与已认证清单一致、没有Rust改动，引用既有fmt、Clippy及workspace 380通过/37忽略结果。独立审阅未发现来源绑定与旧版本兼容阻断；详见[本批断点](docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v3-handoff.md)。

真实审计报告`data/runtime/p1-curry-ledger-handoff-v3-offline-2026-10-25/audit-report.json` SHA256为`b0c8aa022a02b00ad546a37d04890a36c14eeeb29082447aef4def35b6fe10bf`，11,194字节；Python合同和V3 schema通过。报告在`stage1_parent_receipt`以`curry_saved_stage_process_output_invalid`失败：真实V3 stage 1 stdout含与冻结预留一致的附加会计字段，而当前辅助校验严格要求仅有`successful/native_calls/ledger`三字段。stage 2、隔离runner构建核验和saved-input审计均未运行；本批runner只构建未启动。不得在固定目录重试或覆盖。

前六个检查通过：V1/V2失败来源、V2最终源码、acceptance/delivery、双时点来源、V3预留及历史链、冻结scope输入。稳定性复核记录workspace、baseline、预留、原账本、runner构建及stage 2 receipt状态一致；原stage 2 receipt仍不存在。V3报告`native_calls=0`；新消费、unknown、planning total、旧confirmation实际消费及全部历史实际累计为`null`。历史认证子集32次、政策预留7、规划基数39仍区分登记；原scope账本SHA256为`7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`，既有stage 1为1次消费/完成、未知0仅沿用此前证据。本次未产生新收费，四项资格保持false。

隔离runner SHA256 `6f6cc47b090525f49fe4c443a91a0a63889d4b4284a1bad3b38d65086f2a7c44`；构建记录SHA256 `b87073c899124942148c623fe1f26e412172f10f38dd1d1009a897bb3f5e08b7`、identity `16a5bcfb380180c1c8af7686e9ab6a6abe1d1bee316f32dceecc4abf70da69b0`，源码身份`148a8df98a314db571c3825f5cf472fa410801097d9daeb4d3645a5d2d847da0`/563项。源码ZIP与文件清单哈希分别为`80366616585ca58e59fac4fbabc793c66ce90bd0611e5da3558bff5c66255deb`和`7d05667aed55f0c1b03c0be0073afb3f45a2236bde5471975cceeecd48d5964c`。Python全套日志位于`target/curry-ledger-handoff-v3-tests/full-python-20261025T185658Z/pytest.log`，完整证据、文档后源码归档和目录清点见本批忽略交付目录。原V1/V2失败报告保留原哈希；不切换部署、不提交或推送Git。

## 历史状态（2026-10-25）：Curry V2账本交接恢复审计

**离线合成验收、总检和独立审阅完成；唯一一次V2真实只读审计在首个`previous_failed_source`门禁失败，按计划停止。**本批新增原生调用为0；没有启动保存输入runner、worker、FFI或doctor，也没有创建新scope、窗口或收费账本。

全量Python测试显式列举68个顶层测试文件，共555项：546通过、9跳过、0失败，用时806.42秒。跳过原因为两个Windows目录符号链接能力限制，以及v3/v4报告、本机引擎资产、快照/真实v2、完整策略和独立赛事配置opt-in。Rust/Cargo 151项与已认证源码清单一致；引用既有workspace 380通过/37忽略、fmt及全目标Clippy结果，本批未改Rust。独立审阅通过。日志与清单见`target/curry-ledger-handoff-v2-tests/`。

V2报告`data/runtime/p1-curry-ledger-handoff-v2-offline-2026-10-25/audit-report.json` SHA256为`9d74b97e6553ba141537bae414e0f60740220de48e0b031fdb6bff0bad0928c1`（3532字节），通过运行时合同与schema；状态`failed`，首个检查点`previous_failed_source`，其余检查未运行。首个来源映射把V1审计runner误指向`curry-option-verification.exe`；实际V1来源包中存在且与build record一致的是`curry-option-validation.exe`（SHA256 `cd5f294e99aa5c44935e2ef414865a6f46fa2c8bbb5230f018d31ad606365b8d`）。此外，V1归档源码已将`verify_parent_request`改为返回`Result<()>`并释放只读view，故要求该归档仍包含锁冲突缺陷的静态断言与实际归档不符。该第二项尚未到达运行门禁，作为静态发现记录；不改写归档或旧报告。

V2报告的`inputs`为空，runner退出码、stdout/stderr捕获均为null，无进程诊断侧车；保存输入审计未运行。原V1失败报告保持SHA256 `4b3a802cb26097ec2bdf48ef59ffe56103ac87fc3b0842209feb3a7c89e0ec2e`。独立复核确认原scope账本SHA256仍为`7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`，stage 1消费/完成1、未知0，stage 2收据仍缺失；本批没有重新认证这些消费。既有认证子集33、政策预留7、规划40沿用原证据口径；旧confirmation实际消费与全部历史实际累计仍为`null`。四项资格继续false。

本批隔离runner SHA256为`f3cd6148e62addb164e6efd1d613fbcfb6ec81f428ea77c273b436e5f98db8ac`；构建记录SHA256 `eef3a7c9519c7996c12b65ef04b0b93a22448a1902419d1e70b7428581307930`，identity `6020ab76de9a097ef28611ff439f061af313c20f6e259d47c222616a5ee2b961`，源码身份`cf271cd66778dbc2f3ea066bb1be7df257163686745f8eafdc116a8a2fb52e6e`（557项）。源码ZIP及清单SHA256分别为`0f6851a7cb2dd9f03f96c730739b9ab6b57b966d8bc5a656a75acc71af570e2a`和`3dd1eb14e80d97c7f1c6631c77b6817c75843e21d0d5fb721f7b02ac97558784`。本次真实审计后不重试、不覆盖固定V2输出目录。恢复边界见[本批断点](docs/superpowers/plans/2026-10-25-curry-ledger-handoff-v2-handoff.md)。不切换部署、active资产或Git提交状态。

## 历史状态（2026-10-25）：Curry V1账本交接恢复审计

**锁生命周期修复和离线回归已完成；真实stage 2只读验收在最早的acceptance会计门禁失败并按计划暂停。**新原生调用固定为0；未创建新scope、窗口或收费账本，未启动normal runner、worker、FFI或doctor。

Rust以生产normal分派完成stage 1→2合成收费回归，并覆盖validation、confirmation、verification三种配置的完整七阶段执行/重放夹具。读视图在独占写账本前释放；独占打开后仍复验父链和派生请求。只读stage 2模式用同一个不可写账本视图校验父收据与统计，并在构造adapter或打开可写账本前返回。

离线验证：Python顶层全套517项，508通过、0失败、9跳过；Rust workspace all-targets为380通过、0失败、37忽略（87个测试套件）；格式和全目标Clippy通过。独立审阅通过。第一次Python全套与源码编辑并行，出现两项`source changed during capture`，冻结源码后的干净复跑通过。逐项日志、跳过/忽略明细与源清单见本批断点及忽略目录。

唯一一次真实只读审计报告位于`data/runtime/p1-curry-ledger-handoff-offline-2026-10-25/audit-report.json`，SHA256 `4b3a802cb26097ec2bdf48ef59ffe56103ac87fc3b0842209feb3a7c89e0ec2e`，通过v1合同及schema；状态`failed`，检查点`acceptance_delivery`，诊断`curry_handoff_acceptance_accounting_invalid`。归档的acceptance实际使用`policy_reserve`键，而门禁的整数类型检查读取`policy_reserved`，因此固定基线尚未完成核验；saved-input runner没有启动，未产生进程诊断，账本未被本次命令打开。未重试本次审计。

原scope仍为消费1/7、未知0；stage 1成功，stage 2未收费且余6槽封存。此前认证子集33、政策预留7、规划40维持原证据口径；旧confirmation实际消费及全部历史实际累计继续为`null`。四项资格仍为false，不切换部署或active资产，不提交或推送Git。下一步见[本批断点](docs/superpowers/plans/2026-10-25-curry-ledger-handoff-handoff.md)。

## 历史状态：Curry V3预留绑定的七阶段验证（2026-10-25）

**Curry V3预留绑定的七阶段验证已按失败门禁暂停；仅stage 1通过，stage 2未获收费，后续阶段未运行。**固定scope为`curry-option-verification-v1`，额度7次/7200秒；窗口起点`1792898169`。stage 2 runner在`ledger_check`之后、`batch_call`之前以退出码2结束，stderr报告Windows共享冲突（OS error 32）。收费账本认证为消费1、完成1、未知0；不将stage 2诊断改写为成功，也不重试或调用后续阶段。

只读`--verify-only`执行0次原生调用，报告`valid=false`、诊断`incomplete_saved_stage_files`：已认证stage 1收据；stage 2保留请求、输入、report和进程侧车，但缺少receipt。验证报告保留于`target/curry-option-verification-checks/14a607e5e6a744fd95229e81403c98ca/verification.json`。本scope在stage 2后停止，剩余6个槽位封存，不得复用。

本批会计为已认证历史32次、政策风险预留7次、规划基数39；新scope实际认证消费1次，因此认证历史子集含新增为33、规划总数40、未知0。旧confirmation实际消费与全部历史实际累计继续为`null`。隔离构建、离线总检和独立审阅结果，以及原生/验证诊断哈希见[本批断点](docs/superpowers/plans/2026-10-25-curry-option-verification-handoff.md)；文档收尾后的单独构建、源码归档和验收索引在忽略目录`data/runtime/p1-curry-option-verification-native-2026-10-25/final-build/`；原生前实施计划保留作历史依据。`proof_ready`、`complete_action_coverage`、`global_optimality`和`native_probability_verified`仍为false。不切换部署、active资产或Git提交状态。

## 历史状态：Curry V3材料兼容与风险预留（2026-10-25）

**Curry V3材料兼容、风险预留和只读verify已通过；新增原生调用为0。**针对真实固定材料修复了review字段来源、Windows绝对账本路径、64条角色/43个物理路径及40个证据角色的双层索引、天玑账本目录认证四处兼容，并绑定修正后的534项源码归档与535/536项V2源码链。V1/V2原合同和失败件均保留。

唯一一次真实V3审计通过全部7项检查。报告位于`data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25/reservation.json`，SHA256 `14c13e4992673115c0211259dd7d035d968b9c36518c28b4a4ea159ff06ad43f`，36,306字节；V3 schema验证通过。确定性预留ID为`09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63`，政策预留7次，规划基数39。已认证历史子集为9账本/32次/未知0；旧confirmation实际新增、累计及未知消费仍为`null`，全部历史实际累计为`null`。预留不是收费记录或实际消费上界。

62个显式顶层Python测试文件全套为480通过、9跳过、152个子测试通过，用时830.55秒；聚焦测试为19通过、1跳过、22个子测试通过。两位独立只读审阅通过。151项Rust/Cargo源文件与V2最终归档逐项一致，未重跑Rust；旧159项是包含8项生成证据的历史验证选集，不是源码文件数。日志、清单及来源冻结见忽略目录`target/curry-consumption-reservation-v3-tests/`。

审计源码身份`d76728dbd79ab42fcda13320c615683518fc70dd85a6219846244c6d02d0003d`、540项；相较V2最终536项归档新增四个V3模块/schema/测试文件。原生调用0，未创建新scope、窗口或收费账本，旧七个槽位继续封存。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均为false。最终交付索引见`data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25/delivery/acceptance.json`，续接说明见[本批断点](docs/superpowers/plans/2026-10-25-curry-consumption-reservation-v3-handoff.md)。不切换部署，不提交或推送Git。

## 历史状态：Curry V2风险预留（2026-10-25）

**Curry v2风险预留合同、合成恢复路径和Python总检已通过；真实只读审计按首个业务门禁失败并暂停。**新增独立v2合同与前次失败来源核验；V1入口、六成员工具归档及报告语义保持兼容。60个显式顶层测试文件全套为472通过、9跳过、147个子测试通过（772.47秒）；修正后的空`inputs`精确错误码聚焦用例另为1通过。独立审阅确认V2成功报告的Python合同和schema均拒绝空输入，V1语义未变。日志与清单见忽略目录`target/curry-consumption-reservation-v2-tests/`。

固定V2真实来源审计只运行一次，失败报告SHA256为`5fb0cd2e10d3477fd09544e85e02b5234386b60668721ba33bc85ccb1db745da`（5,338字节）；报告通过V2合同和schema，`failure_checkpoint=latest_delivery_chain`、诊断`independent_review_invalid`。已绑定的旧V1失败报告哈希仍为`17dd4b3f08c4c13c1d440bf6641a3fa4b9c9ae498e652c5d852156c8891ee3e7`。静态核查发现固定独立审阅材料没有`public_cli_bypass_found`字段，而当前固定门禁要求其为`false`；因此这次未进入真实v2报告、旧scope或历史账本检查。按停止规则不修补既有来源、不重试、不执行verify-only；原V1报告保持原字节。

本批`native_calls=0`、`execution_ready=false`。预留未记录，reservation ID和规划总数均为`null`；本次报告中的历史账本统计及旧scope实际消费保持`null`。此前已认证的九份历史账本/32次/未知0作为既有事实保留，但本批没有重验；全部历史实际累计仍未知。没有创建scope、窗口或收费账本，旧七个槽位继续封存。审计时源码身份`be9414a756ab436ba12221f178ea23bbb55ac00bfa0ff55c170ca69647bafc98`、535项；完整源码归档SHA256 `8104ee889d2ae0a686fb5b5a3cba8add1076ad22f29e029f871ee825eea9eb67`、清单SHA256 `08dd2255a19eea71b1a8d92c03051e1d7b20717265044b91ce7f4005dfb180c9`，保存在忽略测试目录。下一步须另行制定版本化恢复路径和新输出锚点，不得覆盖本次V2失败输出。详见[本批续接断点](docs/superpowers/plans/2026-10-25-curry-consumption-reservation-v2-handoff.md)。四项资格继续为false。

## 历史状态（2026-10-24）

**Curry公共审计完整合成验收已完成；真实原生资格不变。**修正了重复归档角色的来源路由：旧Curry的两份归档及允许差异从`asset_audit_scope`子节点读取，九账本历史从`historical_chain`读取；通用最近节点规则未改变。新增的公开入口合成回归贯通全部七项检查、真实账本解析器及v2报告校验。合成账本消费分别为9/8/1/4/2/2/0/0/6，共32；最早账本保留37条记录。生产来源固定值由节点断言及完整树黄金摘要锁定。

全量Python测试显式列举59个顶层测试文件，复跑为461通过、8跳过、130子测试通过（497.48秒）。8项跳过分别为：Windows目录符号链接不可用；v3报告、v4报告、本机引擎资产、真实快照/报告、实际v2报告、完整策略报告及独立2026赛事配置均为opt-in。初次全套曾发现历史账本来源单测的合成节点缺少逐账本消费字段；补齐夹具后完整复跑通过。日志和文件清单见`data/runtime/p1-curry-recovery-synthetic-e2e-offline-2026-10-24/`。

合成成功报告SHA256为`45d127bed0f27870167c042a23f8f253c88fb4338edc17ca73a9dc6443578812`；报告通过v2 schema，七项检查均为passed，`native_calls=0`、`execution_ready=false`。该报告来自隔离的合成仓库，不是重新执行真实审计。只读字节检查确认真实v2报告SHA256 `67c6332310aed1e77ccc9eb4394b700f4169837b198a50de20d422dc01da757b`及其验收文件`data/runtime/p1-curry-v2-validation-2026-10-24/final-delivery-after-docs-v2/acceptance.json`（SHA256 `20654b7d09247f5f71acd038c6f72546b50a8bfa85f0a3bb9041fc297b1c69e0`）不变；生产来源描述指向的九份账本字节全部匹配。旧Curry confirmation收费账本仍缺失，不推断其消费为0。已认证历史九账本仍为32次、未知0；旧Curry confirmation新增/累计/未知消费仍为null，七个槽位封存。

独立只读审阅确认生产锚点未放宽、来源节点路由明确、公共CLI没有合成来源绕过。正式交付目录的文件数、字节数和访问失败记录见`evidence-size.json`（该清单不计入自身）；旧ACL受限临时目录未遍历、清理或改权限。未运行真实审计、runner、worker、FFI或doctor；未创建窗口或收费账本。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`仍为false。测试时源码身份为`72b411d19cc6cf1e8115ac526ae06f735483490148ad7bb49c5385312536f728`、528文件；文档后的源码归档及验收见该批`final-build/`。续接说明见[本批断点](docs/superpowers/plans/2026-10-24-curry-recovery-synthetic-e2e-handoff.md)。

## 历史断点（额度不足时；2026-10-24）

**Curry 公共审计完整合成验收因 Codex 额度不足 5%暂停，尚未验收完成。**暂停前完成若干合成来源树/递归账本夹具修复；最后为外层合成归档补齐两个必需源码成员的改动尚未复测。完整公共成功路径、checkpoint 负例、Python 全套及最终交付仍待完成。当前暂停前工作树身份为`0e702c63e9ba133304d874391609dea4b2745a58f7ed5e7a2aa1a0a68754a1d9`/526文件；该值在本断点文档修改前采集，不代表文档后身份。既有真实v2报告SHA256 `67c6332310aed1e77ccc9eb4394b700f4169837b198a50de20d422dc01da757b`和历史九账本32次、未知0保持锚定；旧Curry confirmation消费仍为null，七个旧槽封存。本批无原生调用，不创建窗口或账本。恢复命令、最后未验证改动与验收顺序见[续接断点](docs/superpowers/plans/2026-10-24-curry-recovery-synthetic-e2e-handoff.md)。固定合成交付目录尚未创建；工作区改动全部保留，不提交、不推送。

## 历史状态快照（Curry v2审计后；2026-10-24）

**Curry v2清单驱动真实只读审计通过；本批没有原生调用，但一项完整合成验收仍未实现，故保留为部分完成。**审计修复从已认证文件清单读取ZIP成员预期哈希，区分案例对象身份与原始容器保护哈希，并分别绑定confirmation根和来源资产审计根；失败后稳定性复核保留主失败检查点。新增`--report-version 2`及独立v2合同，历史退出码只有对应证据已认证后才记录，实际历史退出码仍未认证。独立审阅确认审计路径不启动runner/worker/FFI、不调用子进程且不打开可写journal。

Python聚焦31项通过；全套显式顶层pytest为419项、412通过、7跳过、0失败（186.870秒），逐项结果见`data/runtime/p1-curry-v2-validation-2026-10-24/pytest-full-v2-final.log`。Rust/Cargo源码未变；157项与此前认证源码清单匹配，引用上一批已通过的fmt、Clippy、workspace 325通过/36忽略及adapter examples 42通过/1忽略，不重复运行Rust总检。真实v2审计按固定命令只运行一次并通过全部7个检查；报告SHA256 `67c6332310aed1e77ccc9eb4394b700f4169837b198a50de20d422dc01da757b`（142,277字节），耗时70.474482秒。审计时工具身份`62b0729c20381023f655fb08f47863f8150c6de8d713f273c39e6bf4d99b8c06`/508文件。历史9份账本认证为32次消费、未知0；本轮新增原生0。旧失败报告SHA256 `e6140724dc2048b82165a98306d970b4793cee6e4d9c46e487e98a49d6131e14`保持不变。旧confirmation收费账本前后均缺失，其新增/累计/未知消费继续为null，七个槽位封存。完整九份合成账本贯穿公共入口的成功测试尚未实现；不以本次真实审计替代该计划验收项。详见[本批断点](docs/superpowers/plans/2026-10-24-curry-input-recovery-v2-handoff.md)。最终文档后的源码归档、身份、验收及证据体积见`data/runtime/p1-curry-v2-validation-2026-10-24/final-delivery-after-docs-v2/`。四项资格仍为false；不切换部署、不提交或推送Git。

**前一版Curry冻结输入审计的历史失败结论保留。**其v1真实只读审计在`source_archives`检查以`archived_refusal_source_hash_mismatch`失败，冻结输入和九份账本等后续检查未运行；报告SHA256为`e6140724dc2048b82165a98306d970b4793cee6e4d9c46e487e98a49d6131e14`。本轮v2报告由修复后的实现独立重核，不改写旧v1报告，也不把历史观察中的退出码1或静态代码返回2称为实际历史退出码。完整旧分析见[上一批断点](docs/superpowers/plans/2026-10-24-curry-input-recovery-handoff.md)。

**上一批Curry新scope七阶段验真未通过并暂停。**固定scope `curry-option-confirmation-v1`、窗口起点`1792787058`、上限7次/7200秒。离线总检、独立审阅、最新基线核验、隔离构建及`prepare-only`均通过；prepared为`true`，新增原生调用0。进入normal编排后，CLI返回“frozen input, build, ledger, or output check failed”；没有stage收据、normal runner诊断或收费账本。只读`--verify-only`返回`valid=false,native_calls=0,diagnostic=incomplete_saved_stage_files`，新增消费、累计消费及未知数均为`null`，不可按零消费结案。历史9份账本仍为32次、未知0。根据停止门禁，不修线路重试，不再使用本scope七个槽位。详细证据与续接条件见[本批断点](docs/superpowers/plans/2026-10-24-curry-option-confirmation-handoff.md)和忽略目录`data/runtime/p1-curry-option-confirmation-native-2026-10-24/`。四项资格继续为false；不切换部署、不提交或推送Git。

**本批Curry资产角色绑定修复与只读验收已完成，新增原生调用为0。**生产身份检查已将engine版本哈希绑定DLL角色，并独立绑定manifest中的worker哈希；normal路径现有三次身份采集、显式preflight一次采集，收费前失败时adapter调用为0。新的隔离runner通过对旧冻结stage 1输入运行`--preflight-only --trace-stderr`，9项审计检查全部通过；实际执行耗时203.599秒，其中共享资产预检161.618秒。历史9份账本仍为32次消费、未知0；旧Curry结果仍是`prepared=false`，原七个未消费槽继续封存，旧失败诊断不改写。Python全套382项中375通过、7跳过；Rust workspace 325通过、36忽略，adapter examples 42通过、1忽略；格式与Clippy通过。审计源码身份和原生时点构建见本批忽略交付目录，最终文档后独立构建及归档也另存。源码改动、测试、跳过项和测试目录误建说明见[本批断点](docs/superpowers/plans/2026-10-24-curry-asset-binding-audit-handoff.md)与[`docs/TESTING.md`](docs/TESTING.md)。本批只证明角色绑定及只读预检；没有运行worker、normal、doctor、真实资产opt-in或48手评估。四项研究/资格标志继续为false。

**上一批Mooyan Curry opcode14七阶段验真的历史结果保持未通过。**新增scope固定为`curry-option-validation-v1`，窗口起点`1792771619`，上限7次/7200秒。prepare-only保存完整manifest、stage1输入与seal、失败summary和进程诊断；旧runner的`--preflight-only`以退出码2结束，stdout 0字节，stderr 273字节，错误为`Curry asset identity differs from frozen request`。当时`research/calls.jsonl`不存在，新增原生调用0、消费0、未知0，历史32次保持不变。七个未消费槽封存，本scope不得重试或续用。根因为Rust `verify_asset_identity` 把请求`versions.engine_sha256`（核心DLL哈希`446f26df…`）与`roles.worker.sha256`（worker哈希`087fe574…`）比较；本批已修复此离线角色混淆，但没有重写旧请求、预期身份、失败报告或部署。详见[原批断点](docs/superpowers/plans/2026-10-24-curry-option-validation-handoff.md)。旧状态报告`prepared=false`、`successful=false`；opcode14和选项响应、两次重放仍未触达。


**上一批天玑完整路径定向验真已完成：新scope六阶段全部成功，消费6/6、未知0；历史26次，累计32次。**固定scope `tenki-placement-validation-v1` 的stage 1–6依次验证opcode18五个区域响应、坐标0/8/0选择及opcode13、false分支到下一idle与独立重放、true分支到含两张同名候选的opcode15与独立重放。每阶段响应oracle、单一自动动作、冻结资产和窗口门禁均通过；stage4和stage6重放一致。`summary.json.successful=true`，只读`--verify-only`结果`valid=true,native_calls=0`；调用账本SHA256 `4244d92bd17413861bc92d4618803bc647dd05cab074189e678be8429f89971c`，summary SHA256 `9b250b347a9f05c3eef8d321f6eba259d389d0cb1a9f4c1db0a84b205b8eee49`，verification SHA256 `836ef6447087290496ec9ef1a6e6f6492b1859b526099f3cc45b83bddfafd669`。原生源码身份`e9538276391f0e08bfa707534aeab6c8e663784da8fcd9a97dc5ea0e9eb6e8f0`/683文件；隔离runner/worker/CLI SHA256依次为`60fb6b9b531d1f1166fbb51a009a507f61c06534cf90a14d308607e8a5dcc035`、`905ec0d590755565c74b7c8bd60919474174e0614e96b81b4880555f57a5fb03`、`ef663c1ea863f22bdb11e0b1c1a9157f750eb3021b2fc27dc1e3769ece2b9796`；原生源码归档SHA256 `8c8c5d676d34ae03161491cd0a6dcedd5cc7c47d5ed2ecabdfbf4231c6e34e7e`。详细证据、测试和续接见[本批断点](docs/superpowers/plans/2026-10-23-tenki-placement-validation-handoff.md)及[`docs/TESTING.md`](docs/TESTING.md)。本结果仅覆盖冻结前缀的局部提示/响应和两分支重放，不完成检索或终场；四项证明、完整动作、全局最优和概率资格均保持false。该scope额度已用满，旧窗口和剩余槽均不转移；不切换部署、不提交或推送Git。

**上一批天玑runner输出/期限离线修复及只读验收已完成；当时原生六阶段仍未通过。**normal、stats、verify与显式preflight共用单JSON输出路由，新增可选stderr阶段追踪；normal runner期限改为原窗口剩余时间并保留30秒worker裕量。单元回归、Rust/Python总检通过。真实冻结stage 1仅以`--preflight-only --trace-stderr`验收：新runner退出0，stdout为单个JSON，输入/共享预检两阶段耗时记录完整；共享预检耗时约157秒，确认旧60秒runner期限不足。8项审计检查通过，历史消费26、未知0，当前confirmation ledger消费0，新增原生调用0；旧报告`runner_timeout`保持原结论。审计源码身份`5ccaa25c19b6b53cf6759c7ebe63481a108ddc8029cdf570c25b1119633e762d`/534文件，runner SHA256 `96a1ad1b0a8c3374e2ef158b7c569cf4ae1aa0daee362f08e1d47c74249ec46c`。实跑报告、构建、归档、测试日志和证据体积记录见忽略目录`data/runtime/p1-tenki-runner-repair-offline-2026-10-23/`；最终文档后身份/构建见该目录`final-build/`。证据体积对既有ACL拒绝路径保持不完整；不修改ACL、不删除材料。六个未消费槽继续封存；不运行normal、worker、doctor或48手评估。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`保持false，不切换部署、不提交或推送Git。

**上一批confirmation scope：离线验收与prepare-only通过，原生目标在stage 1 runner超时后未通过并按门禁暂停。**新增`tenki-placement-confirmation-v1`窗口上限6次/7200秒，只创建一次，起点`1792691169`；`--prepare-only`通过且新增原生0。唯一正常runner尝试被记录为`runner_timeout`：stdout 215字节、stderr 0字节；stdout内容却是`preflight_passed=true,native_calls=0,stage=1`的预检形状，原因尚未查明。只读账本仅含header与零消费checkpoint，无begin/收费请求；本批实际消费0、未知0，stage1–6均未完成，`verify-only`以`incomplete_stage_receipts`返回无效。本scope仅有1次normal runner进程尝试、账本消费0/6；六个未消费槽全部封存，不得续用。原天玑2/6及placement 0/6封存预算也不转移。累计仍26次、未知0，七份旧账本/保护输入均未变。源码与离线实现细节、日志、原生时点身份/构建及最终文档后身份见[本批断点](docs/superpowers/plans/2026-10-23-tenki-placement-confirmation-handoff.md)与`data/runtime/p1-tenki-placement-confirmation-native-2026-10-22/`。原生stage 1没有产生提示或动作证据，固定区域、opcode13、false/true及重放均未验证。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`保持false；不切换部署、不提交或推送Git。

**上一批历史锚点离线诊断与只读stage 1预检已通过；原生验真仍未通过。**修正Rust旧stage 1锚点的66位常量，使其与冻结字节及Python锚点一致为`c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7606dbce5ceaf76`；原归档错误值与未保存的stderr如实保留。新`--preflight-only`通过冻结请求、seal、历史来源、资产身份及目录/保护输入复核，9项检查全通过，新增原生调用0，且未打开账本、调用worker或FFI。诊断报告、原始进程输出、完整跳过/忽略清单和本轮源码身份见忽略目录`data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22/`；当前审计源码身份`7e3471035380cf1043a84b43a5b94f08d3f322c53919cb48814209bb6dac81e6`、458份文件，文档收尾身份及独立构建以该目录`final-build/delivery.json`为准。六份历史账本仍累计26次、未知0；placement账本消费0/未知0，原窗口未变，六阶段旧scope剩余4槽封存。旧原生stage 1 `runner_failed`及六阶段未通过结论不改写；区域18、区域响应、opcode13两分支和重放仍未获原生验证。下一次原生工作必须单独建立并授权全新scope/预算，不得使用旧窗口或剩余槽。见[本批断点](docs/superpowers/plans/2026-10-22-tenki-placement-diagnostics-handoff.md)。四项证明、完整性和概率资格保持false。


**上一批v2天玑执行结果（历史状态，未因离线诊断而改写）。**本批v2单文件基线迁移、隔离构建和prepare-only已通过；原生stage 1 runner在收费前返回`runner_failed`，六阶段验真未通过。原生时点源码身份为`ebd4d89356b32398a492d900ff9b604e7b03f072d5f24142300e19ba23bf2287`、401份源码文件；全部未提交工作保留。六份旧账本为9/8/1/4/2/2次，累计26次、未知0；旧天玑scope剩余4槽继续封存。366项保护文件中365项匹配，唯一迁移为`target/debug/ygo-engine-worker.exe`从`a384b35aff160049b3381f15bfc35e17cf373a1ada54986b8c884bde09c78c7e`登记至`4f2b5a7c73914f07b0bce39ed01b7f74ed9c335dba329ef3a3bf1803a6db7680`；其当前文件来源仍未知，其余365项匹配。六阶段窗口已创建且不得重置或重试；账本仅有header和零消费起点检查点，保存runner的只读stats确认本批新增0、未知0，因此累计仍26。没有stage收据，opcode18区域提示、区域响应、opcode13两分支和重放均未获原生验证。历史细节见[v2执行断点](docs/superpowers/plans/2026-10-22-tenki-placement-native-v2-handoff.md)，原计划及先前断点保留历史。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`保持false。

**上一批天玑opcode 13合同兼容修复及离线收尾已完成；原生目标未通过。**修复成功stage schema对`catalog`/`banlist`空标签的错误限制，保持两字段必填、字符串类型及其余成功约束。原manifest、stage1、stage2和summary均通过现schema复验；原runner只用`--verify-recorded`/`--stats`零调用复核两收据，累计26次、未知0，余4槽封存。该批stage1仍成功、stage2仍停在区域18/prompt9；opcode13、false/true和重放未验证。完成细节见[2026-10-22收尾断点](docs/superpowers/plans/2026-10-22-tenki-prompt-probe-recovery.md)，原[暂停断点](docs/superpowers/plans/2026-10-22-tenki-prompt-probe-handoff.md)保留历史。

**剩余提示离线触达准备已交付，按计划暂停。**按[准备计划](docs/superpowers/plans/2026-10-21-prompt-probes-offline.md)新增prepare-prompt-probes、独立准备/报告合同、纯唯一激活项选择器和合成响应夹具。Tenki、Mooyan Curry、Ground Collapse三个完整候选均有静态脚本/核心及牌组来源依据；命令6因当前首回合战斗规则与worker停止边界明确阻断。发行依据未知，原生可达/响应接受及execution_ready均false；不含原生执行入口。Rust280通过/36忽略、examples19通过、Python200项中193通过/7跳过，独立审阅通过。新增原生0，五账本累计24、未知0；不切换部署或提交推送。实跑见TESTING，续接见[本批断点](docs/superpowers/plans/2026-10-21-prompt-probes-offline-handoff.md)。

**洗手牌后结束线路观察闭合已交付，按计划暂停。**按[线路计划](docs/superpowers/plans/2026-10-21-shuffle-route-offline.md)新增独立观察配置、合同及audit-information-route。两条历史run各有两个己方决策视图和一个无后继研究终止视图，共6个视图；己方动作进入可见历史，对手HINT/空连锁仅在外层审计。14×2原查询经现存纯数据runner独立绑定，计数/正常效用0，终止点phase未知。固定线路内无范围缺口；完整Rabbit/赛事和其他菜单分支仍范围外。新增原生0，累计24、未知0，旧报告/五账本/部署不变；总检与独立审阅见TESTING，续接见[本批断点](docs/superpowers/plans/2026-10-21-shuffle-route-offline-handoff.md)。

**P1可见信息/概率/动作顺序离线批已交付，按计划暂停。**按[离线计划](docs/superpowers/plans/2026-10-21-information-offline.md)新增独立information-study合同及audit-information入口。固定历史语料生成10个观察视图；16条合成策略样本、3个分组一致，保留4条范围缺口。仅适配Rabbit首次idle和洗手牌后idle；完整Rabbit/赛事未获得整回合观察资格。合成Fisher–Yates的120/20精确分布和顺序编码核验通过，真实核心概率及顺序等价仍未验证。新增原生0，五份账本累计24、未知0；未创建实验窗口/账本或切换部署。独立审阅及总检见TESTING，续接见[本批断点](docs/superpowers/plans/2026-10-21-information-offline-handoff.md)。

**独立历史核验及四次续办已完成，按计划暂停。**按[核验与续办计划](docs/superpowers/plans/2026-10-21-history-followup.md)交付纯只读audit-history与新来源门禁。用户明确接受独立账本/结果完整性核验作为后续依据；旧9次的原runner来源仍未验证，不补签历史重新执行资格。赛事完整线路、公开洗手牌后结束线路均完成执行和独立重放，每次14项查询、精确终场绑定、计数/正常效用0；资产和重放一致。新增4次、未知0，累计24次；零调用恢复不改变账本及收据，第一组保留消费2前缀。该scope已用满，不自动续用。见[本批断点](docs/superpowers/plans/2026-10-21-history-followup-handoff.md)及TESTING；完整动作和最优性资格仍false。

**上一批四次入口的离线交付：**[原计划](docs/superpowers/plans/2026-10-20-terminal-followup.md)实现固定4次模式和报告合同，但当时因旧9次原runner缺失在收费前拒绝，累计保持20次。该次阻断及零消费证据原样保留，后续独立核验政策和新消费见上项；历史[断点](docs/superpowers/plans/2026-10-20-terminal-followup-handoff.md)不再代表当前未用额度。

**Rabbit两次验真已交付：**按[单例计划](docs/superpowers/plans/2026-10-20-terminal-smoke.md)完成独立2次scope、重放前门禁及冻结原生验真。执行/独立重放均engine_verified，14+14目标查询完整、边界绑定通过，计数/正常效用均1，资产与重放一致。新增2次、未知0，累计20次；零调用恢复账本字节不变。仅该冻结Rabbit线路获得终场绑定与重放证据，完整动作和最优性资格仍false。已收尾暂停，见[本批断点](docs/superpowers/plans/2026-10-20-terminal-smoke-handoff.md)及TESTING；赛事/洗手牌后结束另定预算。

**上一批T1/T2已交付，T3触发停止门禁：**按[终场绑定计划](docs/superpowers/plans/2026-10-20-terminal-binding.md)实现显式采集、独立校验、v2评价及候选研究问题。首次Rabbit查询失败、原调用及失败证据仍保留；该批1次使累计达到18次，随后离线修复，不将本批新验真改写为原调用成功。旧6次窗口剩余5次继续冻结。历史断点见[终场绑定交接](docs/superpowers/plans/2026-10-20-terminal-binding-handoff.md)。

**S1/S2已交付，S3按停止门禁收尾：**[快照评价与小额回归计划](docs/superpowers/plans/2026-10-20-snapshot-native.md)已实现离线评价、终止诊断、独立预算与可恢复编排。Rabbit/赛事完整线路和空前缀通过；命令8组原生执行/重放及资产一致，但观察器误计初始化历史消息，已停止后续原生组，离线修复与复核另存。第5组命令7前缀未执行，不以工具修复自动续费。证据见TESTING，续接见[本批断点](docs/superpowers/plans/2026-10-20-snapshot-native-handoff.md)。正常终场效用、完整动作与最优性资格仍未通过。

**首批A–E已交付：**按断点恢复，完成用户额外授权的赛事执行/重放两次、零新增消费重开，以及最终构建/双配置身份关联。证据见TESTING顶部和忽略目录acceptance.json；[断点交接](docs/superpowers/plans/2026-10-19-baseline-audit-handoff.md)保留暂停时点历史。后续任务仍按下列门禁推进。

**P1离线批M1–M4已交付：**修复idle命令6/8及4096子集边界，新增只读历史帧审计、精确旧报告派生字段兼容和[P1.2候选问题](docs/P1_MICROCASE.md)。本批原生新增0；工具验收通过不代表历史语料完整性通过。实施范围见[P1离线计划](docs/superpowers/plans/2026-10-19-p1-actions-offline.md)，实跑与缺口见TESTING顶部。

现有v6专项目标是“异常证据闭环 → 完整首回合语义 → 正式v6 → 16+32手评估 → 独立干净部署”，对应新路线P4。目前局部报告v2、不可覆盖选择检查点、符号搜索前沿续跑及费用后故障前缀已实现；正式`combo plan`仍只分派v1–v5。首回合代码没有正式v6规划CLI。

2026-10-19已确认[产品愿景](docs/PRODUCT_VISION.md)：中文本机浏览器工作台可以先交付；最终AI仍要求全部正式OCG及首回合明确情景下全局最优证明。以下产品研究/工程入口与v6内部门禁分开，不把基础工具交付记为最终AI完成。

### 2026-10-21前后产品路线入口（历史）

以下为当时记录，进展及消费口径已由本文顶部的2026-10-27状态取代；保留原历史描述用于追溯。

- [x] 目标/差距/研究定义及P0–P8小任务文档落地；文档检查和只读复核见docs/TESTING.md的2026-10-19文档交付条目。
- [x] P0.2首批身份/构建记录工具：Rust只读资产身份、Python工作区和双配置采集、观察构建记录及独立v1合同；不等于可复现构建证明。
- [x] P0.1首批覆盖工具：只读CDB、发行证据/脚本清单、alias/预发行及缺口报告；复用39卡依据，分母仍未建立。
- [x] P0.3/P1.1首批协议审计：结构案例合同、10类canonical响应oracle、持久总预算及原生提示/独立重放证据；完整动作、顺序等价与最优性资格仍为false。
- [x] P2.1首批中文来源调查：固定来源版本/哈希与39卡候选映射；名称/正文未人工核对，繁体/别名/字段/许可缺口保留，正式语言资格未通过。
- [x] P1.1离线小批：动作修复、合成负例、三份历史语料对照及P1.2输入/阻断清单；未增加原生触达或证明资格。
- [x] P1状态评价与小批工具：快照计数、终止未知诊断、独立16次预算、证据收据与零调用恢复；本批原生第5组未完成，不等于研究门禁通过。
- [x] P1终场采集与合同工具：可选采集、原始批次/查询绑定、独立评价v2及research-problem候选；工具批首次真实查询失败证据保留，后续Rabbit验真见下项，其他场景尚待验证。
- [x] P1冻结Rabbit终场验真：修复后的worker完成14+14查询、计数/正常效用1及独立重放；仅该线路有证据，不覆盖其他情景或完整游戏树。
- [x] P1固定四次入口离线实现：双案例顺序、独立scope、严格零值/重放门禁及报告合同通过离线验证；历史来源门禁明确拒绝缺失原产物。
- [x] P1独立历史核验：旧9次37条记录、结果/请求/检查点及五组报告绑定通过；第7次单例及未收费后继错误保留，部分报告元数据来源和原runner来源仍未认证。
- [x] P1赛事/洗手牌后结束终场原生验真：独立4次scope完成两组执行/重放，14×4查询完整、绑定及计数/正常效用0；不扩展完整动作/概率/最优性资格。
- [x] P1受限信息离线工具：原始前缀观察投影、按策略分组的精确分布检查、理想洗手牌模型及顺序可区分性；工具通过不关闭完整研究问题阻断项。
- [x] P1冻结洗手牌结束线路观察闭合：己方动作历史、私有提示隔离、研究终止视图及独立终场衔接；仅覆盖固定线路，不认证其他分支、真实概率或完整动作。
- [x] P1剩余提示静态准备：13/14/24三候选、唯一菜单匹配及合成响应；命令6阻断。后续触达、接受和独立重放另定预算，不直接执行准备合同。
- [ ] P0：补齐全正式发行/区域/别名/规则依赖的独立分母与完整证据；首批清点不是全卡验收。
- [ ] P1：修复/补齐动作与信息/概率基础，再开展完整小问题、循环及独立证明校验；当前协议合同不代表数学问题或策略已获证明。
- [ ] P2：通过中文字段核验与使用依据后做查询、候选更新/回滚；当前没有中文搜索服务。
- [ ] P3：草稿/完整牌组导入导出、编辑约束及中文本机浏览器预览；不等待v6全部规则。
- [ ] P5–P8：通用知识、构筑反馈、干扰/证明及全卡发布，按依赖逐项领取；当前未通过最终AI验收。

首批用法及边界见[基线审计](docs/BASELINE_AUDIT.md)、[研究审计](docs/RESEARCH_AUDIT.md)，实际计数/故障/身份见[TESTING](docs/TESTING.md)顶部。细任务与验收见[产品演进计划](docs/superpowers/plans/2026-10-19-product-evolution.md)，阶段依赖见[ROADMAP](docs/ROADMAP.md)。计划里的未来任务框不承担第二份实时进度。

首批验收范围：身份可追踪、覆盖缺口可统计、研究输入可审计、动作有局部原生证据、中文来源有明确未通过结论。历史四份账本9+8+1+2保持不变；本批固定4次已用满，累计24次、未知0，所有旧窗口继续封存。下一步先审阅三条已绑定线路及剩余提示/信息/概率/动作顺序/循环/自然结束/树规模缺口，再单独制定研究任务与新预算，不能直接续费。发行分母与中文字段/许可核验可独立推进。本批不提升全卡、正式v6或最优性资格。

### 当时的既有v6专项门禁（历史；当前开放项见顶部）

- [x] 内部局部报告与符号前沿可持久化/重开；首批真实费用后故障保留并独立重放。
- [ ] 完整执行中的安全检查点和端到端暂停/恢复；其余异常分支/调用中崩溃验收。
- [ ] 86项规则完整语义与逐项认证（当前12项指定分支、1项实际Scythe灰点；仍缺74项规则资格）。
- [ ] 正式v6规划/报告/CLI以及v1–v5完整兼容回归。
- [ ] 冻结独立人工基准、16+32手可续跑评估及汇总验真。
- [ ] 最新源码和双资产在独立干净checkout部署、doctor、重放与身份/账本比较。

这里的`[x]`表示实现/专项有证据，不代表整阶段门禁通过。最新复验和提交号见[`docs/TESTING.md`](docs/TESTING.md)顶部；阶段依赖见[`docs/ROADMAP.md`](docs/ROADMAP.md)。

## 阶段历史（时间点记录；不是当前任务清单）

以下记录用于追溯已实施阶段、历史资产和当时的验收状态；未勾选项不覆盖上方当前门禁，历史“下一步”也不再生效。

### 2026-10-18 从73414c6继续（整轮未完成）

- [x] 复现同一提示重试覆盖事前证据；新增不可覆盖的选择／预测检查点，保留旧局部v1读取。
- [x] 内部局部v2分别保留实际结果、已审计前缀、执行／审计故障及未执行选择；初始失败不借用旧局面。
- [x] 查询审计的持久意图、失败进度、worker原始错误及费用引用重算；完整审计结果和已支持诊断的篡改负例。
- [x] 独立符号搜索前沿的暂停／持久化／重开恢复；与旧连续搜索逐项一致，并拒绝篡改前沿、预留所有权变化及检查点后的未完成扣费。
- [x] 初始调用的持久意图及0新增消费预算拒绝证明；超大计数的局部v1／v2报告拒绝而不溢出。
- [x] 实际取除素材后注入worker故障，保留并独立重放待处理前缀；审计成功不能抹去执行故障，查询缓存版本单独核对。
- [ ] 全部异常分支、调用中崩溃与完整搜索安全续跑验收；已有专项通过不代表整阶段完成。
- [ ] 剩余74项指定规则资格及完整86项语义、全部实际灰点资格、正式v6。
- [ ] 冻结独立人工基准与16＋32手评估、离线编排和完整续跑验证。
- [ ] 全量兼容、最终提交双资产干净部署、独立重放和身份／账本比较。

当前认证仍为12项指定分支／1项Scythe灰点；不以错误处理测试或单条线路成功扩大认证。历史记录在下文保留，最新实跑结果见docs/TESTING.md。

## v6收尾实施：基础集成

- [x] 保存原有开发改动，补齐first_turn知识模块及五个接口；102项分类、86项场景内规则均保留。
- [x] 结构化操作／候选过滤／次数与来源绑定；14项潜在灰点与已验真灰点分离，JSON不能自签验真。
- [x] 新JSON固定LF；牌表字节身份与来源／覆盖引用更新，旧协议身份算法不变。
- [x] 默认Rust120项、Python25项通过／7项跳过；格式、Clippy、新知识来源检查与v6响应探针通过。
- [x] 统一持久扣费包装层：预扣费、预留、分块结果、崩溃残片、检查点与篡改检查；Scythe探针改用统一账本。
- [x] 新知识包原生验真入口、来源／案例／重放引用合同；12个定向案例覆盖6项规则的正反例，安全续跑和独立审计已测试。
- [x] 第一组6项因果转移及原生预测对照：费用／效果分开、同名素材、可选触发、Veil属性复原；未提升整包验真资格。
- [x] v6原始历史与查询见证基础：实例／宿主／费用／无效、通常召唤及名称次数；独立收费查询审计通过。完整限制和认证仍待接入。
- [x] 分支认证视图与已审阅案例身份：6项成对原生资格、0项实际灰点资格；持续／延迟负例独立分类，正式全覆盖仍拒绝。
- [x] 实际闭链主阶段状态构造：独立CDB、素材宿主、通常召唤／次数与已识别限制；未知限制拒绝依赖。查询认证绑定请求及实际双方前缀。
- [x] 定向自主Scythe展开、原动作受阻和实际灰后自主Boots替代线路：两次三组原生实验均72／43／55次，成功线路及查询独立重放。
- [x] 更新公开查询后的12项原生回归及新增Scythe灰响应案例；独立认证92次，6项成对规则资格／1项实际灰点资格，完整覆盖仍缺80项。
- [x] 首批自主线路新增依赖的指定分支资格：通常召唤／盖放、Decay展示特召、Boots、Rusty连接／送墓盖放及素材禁止；现有26案例、12项成对规则资格，完整覆盖仍缺74项。
- [x] 局部v1事前选择检查点、结构化候选比较、实际锚点和重算合同；篡改时点、资源差额、目标及失败类别被拒绝。
- [ ] 局部合同的全部预算／引擎失败降级；随后完整86规则、正式v6和48手评估。

当前为基础及局部自主恢复集成，不是整轮v6验收。实验范围见docs/FIRST_TURN_PILOT.md；执行计划见docs/superpowers/plans/2026-10-17-first-turn-v6.md。

## 2026-10-16 重新选定赛事原表（三阶段实施中）

- [x] 15条原始材料候选与18张照片；选择8月17日南国店冠军原表，主41／额外15，独立转录，Side未公开。
- [x] 官方10月207行规则与冻结快照无差异；原表主／额外合法，39个正式OCG卡号发行依据冻结。
- [x] 独立2026资产组、固定ZIP离线重建、依赖检查、ABI/doctor、新卡人工兼容线路及独立重放。
- [x] 102项规则分类清单；14项新增默认Python检查和1项可选真实资产检查。
- [ ] 第二阶段：86项场景内规则的完整语义、逐项正反例、动态灰点与v6。
- [ ] 第三阶段：冻结人工基准、16＋32手矩阵、持久调用账本、可恢复编排与最终干净部署。

详见docs/TOURNAMENT_RESELECTION.md。原先拒绝的10月4日来源保留历史；本轮未完成整体验收。

## 2026-10-16 赛事构筑来源关口（未通过）

- [x] 核对10月4日パピー弥富店原站、官方嵌入数据和原始照片。
- [x] 记录墓穴指名者24224830与冻结10月表Forbidden/0张的决定性冲突。
- [ ] 完整准确转录并取得符合冻结规则的赛事原表（当前原表不能通过）。
- [ ] 独立2026资产组、首回合效果验真与v6。
- [ ] 16手新功能矩阵、32手实战矩阵及完整验收。

按批准计划停在第一关，不改卡、不换规则、不自行换来源。证据与未确认项见docs/TOURNAMENT_SOURCE_GATE.md；上一轮v5验收状态继续保留。

## 2026-10-16 多响应点与稳健展开顺序

- [x] v5七类灰流丽策略、唯一发动、精确效果编号与旧版本分派。
- [x] 不响应条件下冻结两个不同首敏感效果的展开，2×8矩阵及每格512次共享账本。
- [x] 实际状态重建、素材/登场批次/限制、结算前理由及已验证终场基线。
- [x] 最坏结果排序、七类人工真实响应、Schema及合同篡改负例。
- [x] 最终检查、旧报告兼容、重复身份、独立干净部署及验收记录。

实现边界与用法见docs/ASH_STRATEGY_PLANNING.md；最终验收以docs/TESTING.md为准。

## 2026-10-16 单次灰流丽中断与恢复

- [x] 固定对方灰流丽资源、唯一响应点、双方完整决策与运行协议v4。
- [x] 无干扰、原方案受阻、实际锚点恢复三组；目标保持Rusty＋Fog。
- [x] 从原始事件恢复费用、次数、通常召唤机会与实例；既有历史进入恢复预测。
- [x] v4规划/分析、来源知识身份、每组512次账本及独立前缀见证。
- [x] 修复手牌发动源CHAINING后费用MOVE绑定；独立审查三项合同问题与回归。
- [x] 最终全量回归、旧报告兼容、重复身份和干净checkout部署验收：Rust默认104、真实引擎15、Python全量13项通过。

范围与使用见 docs/RECOVERY_PLANNING.md；最终结果以 docs/TESTING.md 为准。后续先比较同一手坑的响应时点与展开顺序，再进行固定样本评估和构筑诊断。


## 2026-10-15 通用目标与有界收益（已完成本轮验收）

- [x] ygo-goal：三值布尔、数量/等级/阶级/素材/历史、发动窗口和有界收益目标。
- [x] 规划v3、事前目标预测、原始提示/响应绑定、实际逐节点评估及辅助分支证据。
- [x] 共享调用账本、独立见证及外部重放预留，失败/未知与已有推荐保留。
- [x] v2/v3评分参数生效、旧版本分派与重放路径保留。
- [x] 修复批量召唤实例、历史素材时点和否定条件披露；升级 phantom-goal-v2。
- [x] 按原始事件核对 CHAINING/CHAINED 顺序；费用后源快照及同名复活定向真实断言通过。
- [x] 默认Rust98项、opt-in13项、Python全量11项；审查修复、干净checkout与部署验收完成。
- [ ] 后续：单次指定手坑与恢复 → 固定样本起手评估 → 构筑诊断。

范围和示例见 docs/GOAL_PLANNING.md；最终数据以 docs/TESTING.md 为准。


## 2026-10-14 Break Sword v2 与效果验真

- [x] 16个效果的人工真实操作案例、符号资源预测、结算后反例及独立前缀见证。
- [x] 协议v3、规划v2/分析v3及固定对方 Ryu-Ran 合成场景，保留旧版读取和重放。
- [x] 超量素材/取除/破坏事件、复活等级变化、召唤历史和暗属性限制。
- [x] 8个人工基准正例、4个资源受限、4个覆盖/预算降级固定起手回归。
- [x] 类型化失败、v2预测/素材/检查点/场景 Schema、伪造证据拒绝。
- [x] 独立审查三项重要问题回归修复；67项默认、9项真实引擎、Python9项全量通过。
- [x] 干净 checkout 重新构建部署、冻结哈希/线路 ID 一致、旧 Rabbit/v1 Phantom 重放通过。
- [ ] 可配置目标及第二目标；随后单次手坑、起手样本评估与构筑诊断。

说明见 docs/BREAK_SWORD_VERIFICATION.md；完整本轮验收状态见 docs/TESTING.md。

## 2026-10-14 语义规划首版交付（历史）

- [x] 本地源码基线 1db8cd8；外部资产保持忽略。
- [x] Python 3.14 全量 Schema/契约检查恢复。
- [x] 十二卡知识来源与测试引用校验，逐效果声明支持范围。
- [x] 预先生成目标方案，次数/资源/触发限制，原始提示位置与效果绑定。
- [x] 四个新 CLI、独立 v1 规划报告与旧 v2 兼容重放。
- [x] 真实引擎目标终场与独立重放，决策前缀局面见证。
- [x] 预算失败、解释改写和手牌洗牌实例回归。
- [x] 独立干净 checkout 离线构建/部署、冻结资产校验、doctor、固定节点分析与重放。
- [x] 固定输入/512 节点对照及线路 ID 一致性；验证记录见 docs/TESTING.md。
- [ ] 完善逐效果真实回归；补充当前 unsupported 的超量/破坏、保护和对手回合效果。
- [ ] 收紧部分嵌套观察消息及继承 v2 的 JSON Schema。
- [ ] 单次手坑及恢复、多起手评估、残缺构筑、HTTP/UI。

当前说明见 docs/SEMANTIC_PLANNING.md；下文保留 2026-10-07 验收历史。

状态审查：2026-10-07。M0–M4 本机首版已实现并在本机复验；细节见 docs/TESTING.md、docs/DEPLOYMENT.md。本文件区分已交付能力和仍待完成的工程工作。

## 已交付：M0–M4

- [x] M0 固定 Project Ignis core/Lua commit，构建 x64 Release DLL，ABI 11.0 布局探针和 SHA-256 manifest；独立本机配置与 engine doctor。
- [x] M1 只读导入本机官方 cards.cdb 并生成内容寻址快照；固定 OCG 列表及生效日期；未知卡、别名、规则区域和起手校验。
- [x] M2 真实决斗生命周期与回调、协议 v2 长度分帧、类型化提示响应、决策记录、End Phase 终场处理及隔离超时/崩溃回收。
- [x] M3 预算 beam search、完整前缀缓存、启发式终场评分与覆盖说明、稳定线路排序、候选独立重放。
- [x] M4 导入/状态/牌组/搜索/重放 CLI、中文摘要、本机部署脚本和 CI 合同检查。

## 历史验证状态（2026-10-07）

- [x] cargo fmt --all -- --check。
- [x] cargo clippy --workspace --all-targets --offline -- -D warnings。
- [x] cargo test --workspace --offline：35 passed、0 failed、1 ignored。
- [x] opt-in live_engine 本机测试：1 passed。
- [x] 本地 engine doctor、catalog/banlist status、Rabbit 牌组校验、engine smoke、combo analyze 与 combo replay。
- [x] 本轮可运行的 Python focused tests：4 passed。
- [ ] Python unittest 全量发现及 JSON Schema 测试：本轮被缺少 jsonschema 和临时文件 PermissionDenied 阻断，需在可写测试环境复验。
- [ ] 从干净 checkout 执行完整本机重建/部署流程；本轮工作区没有做该操作。
- [ ] 审阅并建立源码 Git 基线。当前 HEAD 仍为 Initial commit，大量项目文件未跟踪；本审查没有暂存或提交。

## 历史待办：M4.1 可复现交付（已由本轮完成）

- [ ] 维护者审阅 Git 跟踪范围；纳入实现源文件、脚本、文档、schema、CI 和可分发 fixture。
- [ ] 排除本机引擎二进制、卡库/卡图、个人配置、运行数据与报告。
- [ ] 解决 Python test extra 安装限制并通过完整 Schema/契约测试。
- [ ] 确保报告能记录请求、搜索预算、引擎/API、catalog、banlist 和评分规则版本。

## 待办：后续产品能力

- [ ] M5 扩大正式卡组、消息/提示解析、效果和评分覆盖；所有支持范围有真实引擎回归。
- [ ] M6 指定手坑、先后攻、对手响应与后攻解场；输出中断和恢复线路。
- [ ] M7 固定 seed 的随机起手统计、终场分布、失败原因和不确定性评估。
- [ ] M8 字段检索、用户约束、合法候选生成与不完整卡组补全。
- [ ] M9 HTTP/API、网页任务体验；基于已验证轨迹评估学习型排序。

原型静态排序和 ApiService 类型仍在仓库中作为兼容代码；当前产品入口是 CLI，不提供 HTTP 服务。启发式评分不代表胜率或已证明最优。
