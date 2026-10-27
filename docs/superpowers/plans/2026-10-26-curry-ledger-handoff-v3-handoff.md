# Curry V3来源角色修复与单次零调用验收：断点交接

日期：2026-10-26

## 当前结论

本批V3来源角色、归档语义及Python/schema合同修复完成；合成测试、全量Python测试和独立审阅通过。唯一一次真实V3只读审计在`stage1_parent_receipt`失败，未启动新隔离runner；依照计划不重试、不覆盖报告，交付时暂停。没有新增原生调用，没有创建scope、窗口或收费账本，也没有运行worker、FFI、doctor或真实normal。

固定审计报告为[`audit-report.json`](../../../data/runtime/p1-curry-ledger-handoff-v3-offline-2026-10-25/audit-report.json)，SHA256为`b0c8aa022a02b00ad546a37d04890a36c14eeeb29082447aef4def35b6fe10bf`，大小11,194字节。Python合同及V3 JSON Schema复核通过。状态`failed`，首个失败点`stage1_parent_receipt`，稳定诊断`curry_saved_stage_process_output_invalid`；前六个来源检查均通过，后续阶段为`not_run`。报告记录`native_calls=0`、`execution_ready=false`、`runner.process_attempted=false`，四项资格为false。

## 失败原因与边界

失败发生在复核旧stage 1成功收据的既有进程输出时，早于本批saved-input runner。只读检查发现旧runner的stdout是成功对象，包含`successful=true`、`native_calls=1`和账本前缀，并附加了V3预留相关的认证会计字段（已认证32、预留7、规划基数39、stage 1后认证33和规划40、预留ID及旧scope/全历史实际消费`null`）。当前`_verify_curry_stage_artifacts`把stdout与仅含`successful`、`native_calls`、`ledger`的三键对象做严格相等比较，因此拒绝了真实V3扩展字段。检查点测试夹具此前只使用三键对象，没有覆盖真实V3 stage输出形状。

这是审计器与已保存runner输出合同不一致的证据，不能解释为父收据损坏或新的原生失败。V3本批runner未启动，`process-diagnostics/`目录未创建。原stage 1的已存进程侧车仍留在原实验目录，未更改。stage 2 saved-input审计没有运行，stage 2收据继续缺失。

## 验收记录

- 顶层Python全套显式枚举71个测试文件，收集608项：599通过、9跳过、0失败，用时1,022.86秒。日志：`target/curry-ledger-handoff-v3-tests/full-python-20261025T185658Z/pytest.log`。跳过原因逐项在`-ra`日志：两个Windows目录符号链接能力限制；v3/v4报告、本机引擎资产、快照/实际v2报告、完整策略报告、独立赛事配置的opt-in条件。
- 最新V3合同与公共E2E聚焦复跑48通过、0失败、83.01秒；其中包含本轮新增的“无不利稳定性复核不得伪装为input_stability失败”正/反例，以及V2不出现V3专属进程字段的兼容断言。
- Rust/Cargo源文件151项（140个`.rs`、11个Cargo文件）与已认证V2文件清单完全一致，缺失/新增/变化均为0。未重跑Rust；引用此前fmt、Clippy及workspace 380通过/37忽略的验证。
- 两位独立只读审阅未发现V3 runner根目录、版本分支、固定锚点、正向历史修复确认或V1/V2兼容问题；未运行runner/worker/FFI/doctor。
- 隔离runner构建状态`recorded`，审计时源码身份`148a8df98a314db571c3825f5cf472fa410801097d9daeb4d3645a5d2d847da0`、563项；构建记录SHA256 `b87073c899124942148c623fe1f26e412172f10f38dd1d1009a897bb3f5e08b7`，构建记录identity `16a5bcfb380180c1c8af7686e9ab6a6abe1d1bee316f32dceecc4abf70da69b0`。runner SHA256 `6f6cc47b090525f49fe4c443a91a0a63889d4b4284a1bad3b38d65086f2a7c44`；源码ZIP SHA256 `80366616585ca58e59fac4fbabc793c66ce90bd0611e5da3558bff5c66255deb`；源码文件清单SHA256 `7d05667aed55f0c1b03c0be0073afb3f45a2236bde5471975cceeecd48d5964c`。runner只构建、未执行。
- 失败报告确认历史9账本子集32次、未知0及政策预留7、规划基数39；本批及旧confirmation的消费、规划增量、unknown和全部历史实际累计均保持`null`。原Curry账本SHA256仍为`7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`，既有stage 1为1次消费/完成、未知0，stage 2 receipt缺失。旧V1/V2报告哈希分别仍为`4b3a802cb26097ec2bdf48ef59ffe56103ac87fc3b0842209feb3a7c89e0ec2e`和`9d74b97e6553ba141537bae414e0f60740220de48e0b031fdb6bff0bad0928c1`。

## 后续恢复边界

不得在本固定V3目录重跑或覆盖真实审计。下一批应先为验证scope的stage stdout增加精确、角色限定的V3会计扩展合同：除基础三字段和账本前缀外，只接受与该冻结预留一致的固定字段和值；错误预留ID、会计值、空值语义或额外字段均拒绝。用真实输出形状的合成正例和篡改反例贯通公共入口及Python/schema后，创建新的不可覆盖审计输出版本，再由用户计划单独授权一次只读尝试。不得重新收费或修改历史stage 1收据。

保留V1/V2失败报告和本V3失败件原字节；旧六个收费槽位继续封存。不切换部署、active资产或Git提交状态，不提交或推送。`proof_ready`、`complete_action_coverage`、`global_optimality`和`native_probability_verified`保持false。
