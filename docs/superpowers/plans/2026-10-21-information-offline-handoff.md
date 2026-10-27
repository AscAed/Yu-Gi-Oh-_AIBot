# P1信息与概率离线批：续接断点

先读docs/INDEX.md、TASKS.md、TESTING.md顶部，再核对本机`data/runtime/p1-information-offline-2026-10-21/acceptance.json`和delivery-checkpoint.json、源码清单及归档。保留全部未提交工作、外部原始资料和部署；本批已经暂停，不自动提交/推送。

## 已交付及范围

audit-information绑定独立information-study-v1、冻结Rabbit输入、五份历史报告及三份静态核心文件。原始NEW_TURN/SHUFFLE_HAND/NEW_PHASE/初始化HINT/idle独立解析，首次idle及洗手牌后idle合计10个执行/重放视图，跨来源仅2个观察键。16条合成策略样本形成3个policy_id及观察键分组；同策略相同观察的精确分布一致，不执行策略代码。

观察阶段来自原始事件（MAIN1=4），不是legacy checkpoint的512。来源哈希、seed、完整checkpoint、精确牌库顺序、内部标签和绝对prompt序号留在视图外；菜单位置/索引/Choice/字节和己方有序手牌保留。第三份终场报告只读取早期原始前缀，不反推状态。

报告有4条范围缺口：洗手牌终场两个run的第二idle以后未适配，完整Rabbit/赛事各1条整线路缺口。未知消息停止后续投影；范围缺口不改写为非法动作。数学夹具120个标签排列各1/120、20个卡号顺序各1/20，两层质量1；标签仅在数学审计内部。静态核心哈希不认证真实PRNG条件分布、拒绝采样或后续随机行为。反向选卡/区域响应只证明编码可区分，原生合法性未验证、顺序等价未证明。

## 验证与保护

格式、workspace全目标Clippy通过；Rust串行默认280通过/36忽略，examples 19通过；Python153发现、146通过/7跳过。逐项跳过及原因见忽略目录skipped-tests.json。独立复审31项聚焦测试及9项篡改探针通过；历史类别重标、损坏嵌套元数据和运行时/schema差异已先复现再修复。真实资产opt-in及48手评估未运行。

工具实跑时点源码`7b8458bd5cf70b976f4e7b7da1a4f4a43facf1fc046d46ccb0de87bd190ffe0d`、363份文件，tool-source.json/zip逐项核对。文档后另存最终源码及归档，精确身份以acceptance为准。非法响应失败报告保存且退出1，覆盖旧输出退出2且旧字节不变；两种报告均通过合同检查。

237个历史/资产/部署保护文件保持原样，其中五份账本9+8+1+2+4=24，未知0。新增原生调用0，不创建新实验窗口或收费账本；合成测试的临时账本不是实验消费。普通dist、原worker及active资产不切换；本批无需交付新worker。

## 下一入口

先审阅受限观察与4条范围缺口，再单独冻结后续任务。完整信息模型、真实条件概率、必要动作、动作顺序、循环和可检查树规模等条件仍阻断证明；不能把有限策略样本、理想模型或同seed重放当作完整研究定义。提示13/14/24、命令6与自然结束仍缺原生触达资格。若需原生实验，另定明确新预算和时间窗，所有旧窗口封存。

proof_ready、complete_action_coverage、global_optimality、native_probability_verified均false；不提升正式v6或全卡资格，不实现求解器或生产搜索接入。
