# W1-C 单次 Rabbit 本机分析执行范围

状态：本范围的单次本机W1-C运行于2026-11-03完成；本文件只覆盖这一次人工发起的操作和一个任务，不延伸为后续调用授权。

## 目的与资格边界

使用已实现的显式工作台执行路径，对固定Rabbit起手和固定本机资产完成一次有限搜索，验证冻结输入、持久任务链、worker执行和报告读取能否在当前候选包上贯通。此范围不建立或使用ResearchBatch收费账本，不计入R1b-3，不测真实恢复或独立原生重放，也不代表原生研究消费已核算。worker请求、报告`engine_calls`及底层FFI调用分别记录；没有独立证据的计数写`未独立计量`，未知消费保留为未知。

该执行允许启动一个本机workbench服务和其实际需要的worker子进程，并允许一次ocgcore/FFI分析路径。所有草稿、任务、报告、日志及采样证据只写入被忽略的`target/w1c-execution-20261103/`。不运行doctor、runner或其他研究实验；不改快照、活动指针、原始牌组、部署目录、Tenki归档或历史pin；不自动重试、不并发提交，不提交或推送。

## 固定输入和产物

- 输入仅为`tests/fixtures/rabbit.request.json`与`tests/fixtures/rabbit.ydk`，哈希及牌组/起手定义以[W1-C设计](2026-11-02-w1c-single-rabbit-local-analysis-design.md)为准。
- 使用catalog `catalog-1b0564fd61eec4730828fea1d48391aa1598bca3157c255454a8dcf487485d6d`、banlist `banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783`，effective date `2026-10-01`；所有资产哈希必须与本机设计和隔离候选清单一致。
- CLI和worker固定为隔离构建`target/w1c-executor/cargo/debug/`中的候选。配置使用`configs/w1c-analysis.example.toml`，在服务启动和认领前重新核对包、配置、快照及完整资产身份。
- 牌组经本机API从固定YDK导入并保存为新的隔离草稿；记录实际`draft_id`、内容revision及草稿文件哈希。提交使用单独分配的operation ID及服务预分配job ID。

## 预算与停止规则

- 恰好一个人工分析操作，最多一个持久任务；搜索参数固定`top_k=5`、`node_budget=10000`、`beam_width=32`、`max_depth=64`、`time_limit_ms=60000`，单次引擎worker超时`30000 ms`。
- operation提交后最多观察`240000 ms`。这是外层停止界限，不是服务端端到端时限保证。出现终态即停止轮询。
- 任何输入/资产身份差异、固定profile拒绝、服务或worker错误、超时、连接中断、持久化不确定或报告认证失败时，保留原始ID和证据，停止本次执行；不分配替代ID、不重复提交、不重放、不把未见记录解释为零调用/零消费。若结果为`unknown`，只按原ID受控重开和认证，不重跑分析。
- 仅当操作/任务链可认证且任务为`completed`或有效`budget_limited`、报告合同通过并呈现终止原因/统计时，记录为“单次有限分析已验收”。其他结果均如实记录为未验收。

## 执行计数和证据

记录CLI服务PID、HTTP操作与任务revision、报告摘要、`nodes`、`engine_calls`、`replay_ms`、总耗时、终止原因、worker错误/超时及服务进程退出状态。`ProcessEngineAdapter`每次adapter运行会尝试启动一个worker子进程；报告`engine_calls`是调用计数，不是操作系统进程创建审计。`replay_ms`不提供重放次数。底层FFI函数调用数和独立消费账本均未计量，因此不得从报告计数推导其值。无论结果如何，都不声称完整搜索、全卡覆盖、一般策略、可比研究账本或全局最优。

候选包清单、身份报告、独立草稿/任务存储、原始查询响应、最终报告、哈希清单、服务stdout/stderr及本范围执行记录均置于隔离target目录。源代码、assets和普通`dist/ygo-local`不作为输出目标。

## 执行记录

运行时间：2026-11-03 01:23:00.883至01:24:50.761（Asia/Shanghai；UTC 2026-11-02 17:23:00.883至17:24:50.761）。提交后观察用时`83776 ms`，低于240秒上限。启动前有两次未提交操作的预检/启动尝试：第一次发现本范围脚本中banlist期望哈希录入错误，实测固定资产未改变；第二次服务进程已启动，但Windows锁定`Start-Process`重定向日志，无法读取令牌，在任何API写请求前停止。两项原始失败证据已保留并脱敏，之后修正为管道读取；无worker/FFI分析发生在前两次尝试。

最终使用源码HEAD `672e5a823fcad60e9413d79cac810b68a2bb003c`、build-input state SHA-256 `dffc6c5f84a71c7f8e2031f8f6f868f25e10a53839e43e6da4bc06aaf4de4f3a`，CLI SHA-256 `0baf2b338aa4eeee64a0b5b533da8e178e2b3c4b7d93ef5a78e43b7362b05c28`，worker SHA-256 `fbbe554d85afbe0f3f3396c2e540a31e1af10e7f72d1f566f0f1fe5053f8550d`，配置SHA-256 `07b7debb9a7d18d86ee55851d466b764e254dfb93d1d1c57801b0ca572efe744`。启动前完整资产身份为`consistent=true`；固定输入和资产哈希与W1-C设计一致。

YDK导入后保存草稿`520f9d91de54a312cb1e8a3aea520655`，草稿revision `20f9703917d62920db575118ba1cae8303c545e138da8de1f89ef440892731e0`；主卡40、额外卡3、Side 0。唯一操作ID `d9c94519880097bb0ef5213580f14e68`，最终accepted revision 4，指令SHA-256 `c7b26d30c7bdaf2854a01491db7ddf237979288e7060e5f06d98c055fd5fbb7b`；唯一任务ID `70e9a8f132e88ff2334b269603363ab6`，最终`budget_limited` revision 3；冻结`binding_sha256`为`f3a3e2d1faa102aabdf108bf1d25b4f35535c0739d8a89eb35004346b9d0e16d`。

实际终止原因`time_budget`。报告统计：160 nodes、165 `engine_calls`、55,775 ms `elapsed_ms`、1,658 ms `replay_ms`、28条`completed_lines`、返回5条线路；5条均为`engine_verified`且报告`replay_verified=true`。这些是本次报告给出的逐线路状态，不是独立原生重放。操作、任务和结果HTTP材料分别通过`workbench-analysis-http-v1.schema.json`（解析其job引用schema后）校验。报告ID `fccc8baf6f3178a511a9e9d45d7b26d7`，报告SHA-256 `52f6b0e2707d86b92e63906f7d03fa8352960904e603f1690dee4782fc0c6bbe`；重开后结果投影字节SHA-256 `8287e8231683145e490776f312898edcd9a78d11494f1ba9c59d476defc7632c`。

服务停止并以同一隔离配置重开后，操作、任务和结果响应字节稳定；草稿/分析存储共11个文件的哈希清单重开前后完全相同。未观察到遗留CLI或worker进程。报告明确`report_contract_validated=true`、`report_origin_authenticated=false`、`search_complete=false`、`global_optimality=false`。

本次没有ResearchBatch账本或独立消费记录；底层FFI函数计数、worker OS进程创建数及消费量均未独立计量，未知不等于零。一次有限本机分析按本范围验收；任务只到time-budget截断，不代表全局搜索完成、全卡覆盖、可比研究会计、报告来源独立认证或最优性。

隔离运行目录为`target/w1c-execution-20261103/`；重点材料：[execution.json](../../../target/w1c-execution-20261103/execution.json)、[最终结果](../../../target/w1c-execution-20261103/result.after-reopen.json)、[哈希清单](../../../target/w1c-execution-20261103/artifact-hashes.json)、[预检报告](../../../target/w1c-execution-20261103/preflight.json)。
