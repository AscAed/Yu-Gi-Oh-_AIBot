# W1-B1 无路径任务合同与纯状态机交接

日期：2026-10-30。实施基线为`main / d3bc212ccdc782d6988162f2030de00836df315c`，保留开始时已有的路线与文档修改。没有提交、推送、切换部署或active资产。本批只实现任务合同和纯转换；任务存储、HTTP接口、队列及界面均未增加。

## 实现范围

- 新增`ygo_cli::workbench_analysis::jobs`和独立[JSON Schema](../../../schemas/workbench-analysis-job-v1.schema.json)。白名单从真实W1-A冻结对象复制，运行配置、本机路径和完整catalog不进入记录。
- `new/validate/read_json/encode_json/transition`提供构造、关系校验、严格读写及纯转换。记录内部不可修改，调用方提供服务ID和Unix毫秒时间；返回稳定错误码。
- 两层摘要区分W1-A冻结身份和任务输入完整性，评分参数单独入新摘要。启用serde_json `float_roundtrip`，修复有限评分编码后再读取可能改变位值的问题；没有增加依赖包或改变旧请求结构。
- [状态矩阵与失败边界](../../WORKBENCH_ANALYSIS_JOBS.md)限定queued→running/cancelled/interrupted、running→completed/budget_limited/failed/unknown；终态不可重发。空线路保留`:no_verified_lines`，报告只存ID/hash/原因/线路数，不认证文件实际存在或发布成功。

## 红测与审阅

全部运行材料和日志位于忽略目录[`target/w1b1-analysis-job-tests`](../../../target/w1b1-analysis-job-tests/)。最初新增Rust模块测试因未实现而编译失败（`red-contract.log`）；schema缺失红测见`red-schema.log`。边界扩展中实际复现有限浮点位型`0x723f4114006c08c7`往返`BindingMismatch`，见`finite-patterns-first.log`；修复后固定种子4096个bit样本中的有限值均逐位往返。Python非法NaN曾被默认解析器接受，红测见`nonfinite-python-red.log`；现已拒绝NaN、Infinity及溢出数值。

独立子任务执行只读审阅，未运行引擎或自行重跑测试，未发现确定的生产回退；指出非有限JSON数字、线路超过top_k及部分错误revision负例的隔离不足，均已补齐。审阅与处置保存在[`read-only-review.json`](../../../target/w1b1-analysis-job-tests/read-only-review.json)。审阅不替代行为测试，也不认证历史原生材料。

## 验证与暂停

实跑计数、忽略明细及最终检查以[TESTING的本批记录](../../TESTING.md#2026-10-30-w1-b1无路径任务合同与纯状态机)和[`verification-summary.json`](../../../target/w1b1-analysis-job-tests/verification-summary.json)为准。共享语料采用独立手写数据和Python hashlib黄金摘要；Rust与schema读同一批121项用例，明确区分schema结构约束与Rust双摘要/跨字段关系校验。

合成fixture通过真实W1-A冻结接口，在任务创建后更新草稿并移除默认快照，任务字节保持不变；资产文件仅为合成字节，从未执行。兼容回归包含非GET同源门禁、草稿读写/导入导出、卡表/语言状态及旧分析接口。未重跑Python全套及已知Tenki历史pin失败，原pin和原记录保留。

本批新增原生研究、真实runner、worker和引擎FFI调用为0；未运行真实分析、doctor、真实资产opt-in或48手评估。认证消费子集40、政策预留7、规划47不变；旧confirmation实际消费和全部历史实际累计仍未知。合同不包含执行、重放或最优性凭证。

完成后暂停。下一批仅规划W1-B2单运行加单排队、取消和容量/同源回归；W1-B3再落实持久化顺序、报告验证后发布和重启分类。实现报告发布时必须先验证实际报告、绑定冻结输入且完成落盘，再调用`ReportPublished`。真实本机分析仍由W1-C独立验收，不自动复用旧scope或槽位。
