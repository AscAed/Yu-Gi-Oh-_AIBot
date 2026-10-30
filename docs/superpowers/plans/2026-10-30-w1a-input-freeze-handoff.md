# W1-A交接：工作台同源保护与分析输入冻结

## 范围与结果

本批在W1设计上交付两项离线能力：工作台API对所有非GET请求执行同源门禁；Rust库提供基于服务管理草稿revision的分析输入冻结。当前基线为分支`codex/w1-workbench-analysis-design-20261030`、HEAD `8315232`，已有未提交文档更新予以保留。

没有新增分析任务HTTP路由、持久化队列、取消处理或结果页面。冻结函数只调用现有`ygo_api::combo::prepare`完成输入门禁及版本身份采集，不构造进程适配器，不启动worker、FFI、研究入口或收费账本。

## 实现边界

- `handle_connection`对`/api/`的非GET请求，在路由分派前依次要求本机Host、Bearer token和精确同源Origin。请求头/请求体大小、连接并发和路径约束维持原值。
- `DeckDraftStore::load_at_revision`在同一内部互斥锁持有期间读取草稿、验证存储内容和比较期望revision；返回独立拥有的结构。编辑发生在返回后不会改写已复制内容。
- `ygo_cli::workbench_analysis::freeze_analysis_input`接收托管草稿ID/revision、起手、seed、规则、快照选择、日期与`SearchBudget`。草稿作为唯一牌组来源，不接受浏览器提供的任意牌组或路径。
- 函数将revision绑定的牌组写入现有`ComboAnalyzeRequest`，解析固定catalog与banlist快照ID，再通过`prepare`执行完整牌组、五张起手、`ocg-mr5`、日期/禁限、预算和catalog/CDB哈希门禁。返回冻结请求、运行请求、自有catalog及`FrozenAnalysisIdentity`；快照ID、来源哈希和请求参数随冻结身份保存。
- `FrozenAnalysisInput`仅是进程内执行对象，不实现serde序列化/反序列化：其中`runtime_request`含本机资产路径，`catalog`含完整本地卡表副本。W1-B若持久化任务，应另定义仅含规范化请求、无路径版本身份、任务状态及必要报告引用的存储合同；HTTP响应不得序列化冻结对象、暴露路径或返回整份catalog。进程重启后按既定规则将无可认证完成报告的任务标为中断/未知，并在任何真实执行前重建运行请求和复核当前资产。
- 引擎配置要求的文件/目录存在。核心、CDB、脚本manifest、worker和engine manifest在`prepare`前后采集哈希；运行时采用已有的引擎/CDB/脚本manifest哈希交叉比对，采集期间变化会拒绝冻结。稳定错误码不会向调用者暴露本机路径。
- 冻结结构驻留内存也不是实时资产仍有效的证明。未来执行前必须针对当前资产重新核验；本批没有执行冻结的runtime request。

## 验证记录

- 跨站DELETE测试先在旧代码上失败；修复后跨站或缺少Origin的DELETE被拒绝，同源请求进入路由，本机Host/token仍按原门禁校验。现有POST/PUT草稿、导入/导出、catalog和语言状态回归通过。
- 合成冻结测试覆盖有效牌组；冻结后修改草稿并移除选中快照文件仍不改变冻结对象；过期revision、39张牌组、错误起手数量、日期错误、未生效banlist、越界预算、catalog/CDB不匹配及缺失worker资产均以稳定代码拒绝。
- 日志：[`fmt.log`](../../../target/w1a-workbench-freeze-tests/fmt.log)、[`ygo-cli-tests.log`](../../../target/w1a-workbench-freeze-tests/ygo-cli-tests.log)、[`clippy.log`](../../../target/w1a-workbench-freeze-tests/clippy.log)、[`workspace-serial.log`](../../../target/w1a-workbench-freeze-tests/workspace-serial.log)。
- `cargo fmt --all -- --check`通过；`cargo test -p ygo-cli --offline --locked --target-dir target/w1a-isolated -- --test-threads=1`为25 passed、0 ignored；workspace全目标Clippy `-D warnings`通过；workspace默认串行测试为366 passed、36 ignored、0 failed。36项均为仓库标记的冻结资产、显式原生研究、人工准备或本机报告opt-in；未运行这些测试。
- 红测、Cargo日志和合成材料位于忽略目录`target/w1a-isolated`及`target/w1a-workbench-freeze-tests`。本批未运行Python、真实分析、浏览器、doctor、真实资产opt-in、部署或原生实验。

## 当前状态与续接

将`TASKS`中的W1-A标记完成；W1-B任务队列与结果接口、W1-C真实本机分析验收继续开放。需要补充合成错误分类或revision并发压力时，应留在W1-A回归，不添加用户可提交路径或分析HTTP路由。

会计状态保持认证消费子集40、政策预留7、规划47；旧confirmation及全部历史实际累计消费仍未知。已知Tenki历史pin与本机Python旧保护哈希失败记录没有重写。本批新增原生研究、真实runner、worker、FFI及收费调用为0；没有切换部署、提交或推送Git。
