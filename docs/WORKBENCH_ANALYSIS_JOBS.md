# 工作台分析任务合同 v1

W1-B1只实现Rust库中的无路径记录、严格JSON读取及纯状态转换，没有任务文件存储、HTTP任务接口、队列或界面。源码入口为`ygo_cli::workbench_analysis::jobs`，结构合同见[workbench-analysis-job-v1](../schemas/workbench-analysis-job-v1.schema.json)。原[W1-A冻结接口](WORKBENCH.md#分析接入设计状态)、分析请求和分析报告保持可用。

## 记录与输入

`AnalysisJobRecordV1::new(job_id, &frozen, scoring, now_ms)`从W1-A冻结对象提取白名单，创建revision 1的`queued`记录。job/report ID均为服务生成的32位小写十六进制标识；构造函数校验形状，不承担ID生成、唯一登记或可信来源认证。调用方传入Unix毫秒时间，不读取系统时钟。

记录固定`schema_version=1`、`kind=workbench_analysis_job`，含ID、revision、创建/更新时间、input、state及必须显式存在的可空`report/error_code`。input保存草稿ID及内容revision、自有`ComboAnalyzeRequest`、`FrozenAnalysisIdentity`、有限数值的`ScoringConfig`及`binding_sha256`。牌号次序、重复卡、起手、seed、日期、规则及预算不重排；catalog/banlist必须是已解析的内容ID，不接受`latest`。协议v1记录固定当前协议2与`ocg-mr5`；core/initializer版本标签限128个ASCII字母、数字、点、下划线或短横线，保留现有空标签，不接受本机路径。

不会保存`ProcessEngineConfig`、`RunDuelRequest`、完整catalog、草稿标题或资产路径，也不会给`FrozenAnalysisInput`增加serde实现。构造时核对runtime的版本、协议、牌组、起手及seed与冻结白名单一致。读取时重查完整牌组的结构限制、起手多重集、合法日期及预算范围；它没有完整catalog/banlist内容，不能重新证明卡片支持范围或禁限语义。

`validate()`校验记录，`encode_json()`输出UTF-8 JSON字节，`read_json(bytes)`是正式严格读取入口。记录内部不可写；通过只读accessor获取输入、ID、revision、state、报告引用和错误码。不要用嵌套数据类型的serde读取代替记录校验。递归拒绝重复键、未知或缺失字段、截断/尾随JSON；旧请求类型原有的默认字段在此必须全部出现。整数必须使用JSON整数字面量，拒绝bool、`1.0`和指数形式冒充整数；评分允许有限浮点数。`ygo-cli`启用serde_json的`float_roundtrip`，避免有限评分往返改变位值或摘要。

## 摘要与身份

SHA-256覆盖固定顺序的类型化UTF-8紧凑JSON元组：

```text
["workbench-analysis-job-input-v1", draft_id, draft_revision,
 request, identity, scoring]
```

request、identity和scoring的成员顺序分别使用当前Rust类型声明顺序，不依赖输入JSON对象顺序。修改编码需要新的版本标识。另用已保存白名单重算W1-A的`input_sha256`：请求、重建的`RuntimeVersions`、worker hash、engine manifest hash、catalog/banlist source hash、草稿ID/revision。请求与identity的rules、catalog及banlist必须一致，各角色SHA256独立保留。

两种摘要用于内容完整性检查；可自行重算摘要，不等于来源认证或资产新鲜度证明。W1-B3执行前仍须认证服务输入、核对实时资产及报告绑定，不能凭任务JSON生成执行或重放凭证。schema只表达结构、范围及部分状态约束；跨字段关系、真实日期、双摘要和top_k关系由Rust补充。schema测试额外启用词法整数与有限number检查，标准JSON Schema的数学integer本身允许`1.0`。

## 状态矩阵

`transition(expected_revision, event, now_ms)`先校验旧记录，失败不修改输入。所有成功转换revision加1，时间不得小于上次更新时间；同一毫秒内转换允许。除以下单元外均拒绝，包括全部终态的重复事件。

| 当前状态 | 事件 | 新状态 | 报告/错误 |
|---|---|---|---|
| queued (1) | Start | running (2) | 均null |
| queued (1) | Cancel | cancelled (2) | 均null |
| queued (1) | ClassifyRestart | interrupted (2) | service_restarted |
| running (2) | ReportPublished，exhausted | completed (3) | 报告引用 |
| running (2) | ReportPublished，node/time/depth_budget | budget_limited (3) | 报告引用 |
| running (2) | Fail(AnalysisFailed) | failed (3) | analysis_failed |
| running (2) | ClassifyRestart | unknown (3) | completion_uncertain |

这是当前无中间更新事件的完整v1图，因此记录校验也限制相应revision为1/2/3，不接受任意高revision跳转。queued创建/更新时间必须相同。`unknown`不说明调用或消费为0，重启分类不自动重发。

报告引用仅含`report_id/sha256/termination/verified_lines`，不含路径或报告正文。`termination`原文必须是四种既有原因之一；已验证线路数为0时必须保留`:no_verified_lines`，非0时不得带该后缀，并且不得超过冻结的top_k。`exhausted:no_verified_lines`仍可表示completed，但不表示找到解；预算截断、启发式或任务完成均不表示搜索完整或全局最优。

`ReportPublished`只检查记录关系，**不认证报告存在、哈希真实、线路可信或落盘成功**。W1-B3必须在报告校验、输入绑定及实际持久化成功后才发此事件。这里的任务revision也不替代后续存储的并发控制。

## 失败边界与下一关口

| 失败类别 | 稳定错误码 | 原记录/副作用 |
|---|---|---|
| JSON语法、重复/未知/缺字段或错误数字类型 | job_json_invalid | 不构造记录 |
| schema/kind/状态及字段配对 | job_record_invalid | 不推进 |
| 输入结构、解析身份、预算或日期 | job_input_invalid | 不推进 |
| W1-A身份、runtime白名单或新摘要不一致 | job_binding_mismatch | 不推进 |
| 非有限评分 | job_scoring_invalid | 不推进 |
| 陈旧revision | job_revision_conflict | 不推进 |
| 时间倒退 | job_time_invalid | 不推进 |
| 非法边/终态再推进 | job_transition_invalid | 不推进 |
| 报告ID/hash/原因或空线路配对 | job_report_invalid | 不推进 |

所有路径不调用adapter、进程或研究账本，不写任务文件。W1-B2另接单运行加单排队、取消和容量；W1-B3另接持久化、报告发布及重启；W1-C另做真实本机分析验收。验收与当前断点见[W1-B1交接](superpowers/plans/2026-10-30-w1b1-analysis-job-handoff.md)。
