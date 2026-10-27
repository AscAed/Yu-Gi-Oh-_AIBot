# Curry预算风险预留：续接断点

## 当前状态

**离线工具、合成验收与完整Python回归已通过；真实冻结材料的预留记录未完成。**本轮新增原生调用为0，没有创建原生scope、窗口或收费账本。

固定输出目录为`data/runtime/p1-curry-consumption-reservation-offline-2026-10-24/`。本次真实只读尝试严格只运行一次，生成并保留`reservation.json`，SHA256为`17dd4b3f08c4c13c1d440bf6641a3fa4b9c9ae498e652c5d852156c8891ee3e7`。结果为`status=failed`、`failure_checkpoint=latest_delivery_chain`、诊断`delivery_anchor_mismatch`、`native_calls=0`、`execution_ready=false`。报告中历史账本统计均为`null`，预留未记录、预留ID为`null`、规划基数未发布。

根因已由只读字节比较确认：实现中的固定acceptance SHA256字符串少了一个字符，长度为63；delivery引用的文件和实际acceptance文件均为以下64位值：

```text
f6f5a88664252f9fb0f7d94c7251dba2e8859fbf1d19e9a45396070efce84835
```

源码常量已修正，并新增固定来源回归。修正发生在真实失败报告生成之后。**不得重跑真实审计、不得删除/移动/覆盖现有失败报告，也不得将该失败改写为成功。**原CLI固定输出路径被这次失败结果占用；后续如要重新审计，须先制定版本化恢复方式和新的独占输出契约，不能自动换目录续跑。

## 预算与历史语义

- 已有认证历史基线：9份账本、32次消费、未知0。此次真实审计在`latest_delivery_chain`失败，未重新核验该历史子集。
- 旧`curry-option-confirmation-v1`仍是7次额度；实际新消费、累计消费及未知消费均保持`null`，七个槽位继续封存。尝试时charge ledger在开始与结束存在性检查中均缺失，但这不认证历史实际消费为0；失败报告的scope消费状态仍为未知。
- 本次政策预留尚未记录：无reservation ID、`recorded=false`。规划基数39仅是通过来源审计后才可发布的`32 + 7`预算规划数；当前不得报告为有效预留或实际累计消费。
- 全部历史实际消费仍为`null`。四项资格`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均为false。

## 代码与验证

交付实现位于`python/ygo_eval/curry_consumption_reservation.py`、`python/ygo_eval/research.py`、`schemas/curry-consumption-reservation-v1.schema.json`及`tests/test_curry_consumption_reservation.py`，合成支持文件在`tests/support/curry_reservation_e2e.py`。确定性预留ID不依赖时间戳；verify只核验已保存记录，不执行外部引擎。

最终固定来源篡改回归覆盖delivery、真实v2报告、旧manifest和历史账本四个门禁，修正后的源码常量也有断言。显式枚举的60个顶层Python测试文件最终结果为**469通过、9跳过、145个子测试通过，602.21秒**。日志及清单位于`target/curry-consumption-reservation-tests/`。跳过项为：两个Windows环境无法创建目录符号链接的测试；v3报告、v4报告、本机引擎资产、快照/报告、实际v2报告、完整策略报告和独立2026赛事配置等7项opt-in检查。Python `py_compile`通过。独立只读审阅确认修复没有放宽生产锚点或资格门禁。

Rust及Cargo源码未改变，与既有159项认证清单一致；沿用上批Rust格式、Clippy、workspace和examples验证，没有在本轮重跑。此次没有构建或替换worker，也没有运行runner、worker、FFI或doctor。

## 恢复顺序

1. 先阅读`docs/INDEX.md`、`TASKS.md`、`docs/TESTING.md`及本文件，核对本工作区未提交改动并保留全部既有材料。
2. 保持失败`reservation.json`原字节。可对其做只读SHA/schema核验，但本实现的`--verify-only`仅接受成功且已记录的预留，因此不得把它当作失败报告恢复或补写接口。
3. 若需要生成成功预留，先另立恢复计划：明确新版本CLI/合同或经用户确认的独占新输出位置，并把修正后的源码归档、来源及失败尝试绑定起来；在此之前不再次运行固定真实审计。
4. 获得明确的新恢复范围后，才重新核验固定delivery、真实v2报告、旧scope冻结材料及9份历史账本；全部通过后方可生成唯一ID并发布规划基数39。旧scope消费仍须保持`null`，政策预留不得写入收费账本或伪装成begin/complete记录。
5. 后续Curry原生实验必须引用经核验的预留记录，并单独获得新scope、窗口和请求额度。旧7个槽位不能复用。

本断点只记录事实和后续门禁；不授权重新执行原生实验、切换部署、切换active资产、提交或推送Git。
