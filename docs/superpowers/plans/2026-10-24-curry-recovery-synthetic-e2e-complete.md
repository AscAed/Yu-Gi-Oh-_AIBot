# Curry公共审计合成验收完成交接

## 本批结论

2026-10-24完成Curry v2只读审计的公共合成来源树验收。本批只证明合成输入可经过生产公共校验链；没有重新运行真实v2审计，也没有改变真实历史或原生资格。

来源路由修复将旧Curry归档及其允许差异绑定到`asset_audit_scope`，把来源资产审计的九账本链绑定到`historical_chain`。通用最近节点查找保持不变。生产来源描述有完整树黄金摘要及显式子树归档哈希、清单哈希、源码身份、文件数和消费数回归。

合成公共入口成功路径由`audit_to_output`执行，贯通七项检查、真实账本解析与报告验证。九份合成账本消费为`9/8/1/4/2/2/0/0/6`，总计32；最早账本37条记录。旧confirmation范围仍是`new_consumed=null`、`cumulative_consumed=null`、`unknown=null`，七个槽位保持封存。

## 验证

- 全量Python：显式列举59个顶层测试文件，461通过、8跳过、130子测试通过，497.48秒。首轮发现一个历史账本合成来源夹具未提供逐账本计数；修正夹具后同一文件清单完整复跑通过。
- 8项跳过：目录符号链接不可用（OSError）；v3报告、v4报告、本机引擎资产、真实快照/报告、实际v2报告、完整策略报告、独立2026赛事配置均为opt-in。
- 独立只读代码审阅通过：生产哈希锚点未放宽，子树路由明确，无公共CLI合成来源绕过。
- Rust/Cargo本批无改动；依据工作区认证记录引用前批159项清单及已经通过的格式、Clippy、workspace和examples检查。

合成报告：`data/runtime/p1-curry-recovery-synthetic-e2e-offline-2026-10-24/synthetic-success-report.json`，SHA256 `45d127bed0f27870167c042a23f8f253c88fb4338edc17ca73a9dc6443578812`。它的来源是隔离合成仓库，并通过`curry-input-recovery-audit-v2` schema；报告声明`native_calls=0`及`execution_ready=false`。首轮与复跑日志、逐项跳过原因和负例列表同目录保存。

测试时源码身份为`72b411d19cc6cf1e8115ac526ae06f735483490148ad7bb49c5385312536f728`、528个文件。文档定稿后的源码身份、归档和文件清单见该批`final-build/`。正式证据目录的文件数、字节数和访问失败记录见`evidence-size.json`（该清单不计入自身）；既有ACL受限临时目录没有遍历、清理或改权限。

## 保持不变的历史边界

- 真实v2报告SHA256仍为`67c6332310aed1e77ccc9eb4394b700f4169837b198a50de20d422dc01da757b`；旧验收`data/runtime/p1-curry-v2-validation-2026-10-24/final-delivery-after-docs-v2/acceptance.json`SHA256仍为`20654b7d09247f5f71acd038c6f72546b50a8bfa85f0a3bb9041fc297b1c69e0`。本轮对两者做了纯字节核对，没有重跑旧审计。
- 已认证真实历史为9份账本、32次消费、未知0。
- 旧Curry confirmation收费账本缺失，新增、累计和未知消费保持null；不把缺失解释为0。
- 没有运行真实审计、runner、worker、FFI或doctor；没有创建实验窗口、scope或账本。本批原生调用固定为0。
- `proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`继续为false。
- 不切换部署，不提交或推送Git。保留所有未提交源码、历史报告、旧断点和受限目录。

## 后续断点

本批合成验收到此完成并暂停。若继续Curry原生工作，必须先独立处理旧confirmation消费状态仍未知这一门禁；须另行确定新的scope和预算，不得使用旧七个封存槽位，也不能把本批合成报告当作历史消费或原生重放证据。
