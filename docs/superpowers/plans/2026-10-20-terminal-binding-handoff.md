# 终场绑定批断点交接

恢复顺序：先读docs/INDEX.md、TASKS.md和TESTING.md顶部，再核对本机`data/runtime/p1-terminal-2026-10-20/acceptance.json`及delivery-checkpoint.json。保留全部未提交修改，不从HEAD恢复，不覆盖原部署或历史证据。

本批工具提供research_capture v1、terminal_observation v1、独立terminal-evaluate、evaluate-snapshot显式v2、research-problem候选和独立6次scope。正常边界是核心发出首个下一回合NEW_TURN的处理返回点，包含部分新回合初始化，phase未知。旧请求默认省略新字段，旧评价器v1不变。

原两账本9+8保持不变；本批只消费Rabbit执行1次，completed1、未知0，累计18次。边界事件63/批60已取得，但首查询因遗漏核心固定附带IS_PUBLIC失败；计数和效用均未知，重放和后两组未运行。563秒窗口包含资产扫描。原生源码身份2bdeaa40305a768dd1fc9631b289eca906568e455be07bb788ffd8b7cf15f69a，与后续离线修复和文档收尾源码不同。

`native-source.zip/json`、`native-artifacts`、build-native.json/workspace-native.json保存原调用环境。research/native保存不可覆盖请求、付费结果、原失败报告和收据；failure-diagnosis.json解释原始43字节查询。zero-call-resume.json及native-receipts-native.json记录不再扣费的恢复。最终评价/构建/归档另存，不重写原pair或原诊断。最终源码完整身份由acceptance和delivery-source.json确定，避免文档自引用身份。

两条查询解析器已独立离线修复可选IS_PUBLIC，校验长度5、布尔0/1及唯一性；失败结果分类修正为execution_failed。修复后的worker没有原生资格。后续先审阅该修复和手写正反例，核对最终构建及双资产，再单独制定原生验真预算；原6次窗口剩余5次不得自动继续、重开、换ID或退款。原prompt ID/Choice不调整重试。

纯读取入口：`python -m ygo_eval.research validate-problem --problem <research/rabbit-problem.json>`；v2快照评价使用最终terminal-evaluate.exe和新输出文件。复核原原生收据只能使用保存的native-artifacts/terminal-regression.exe及原input哈希并带`--verify-recorded`，该模式零调用。不要把原完整编排当作启动下一实验的入口。

剩余门禁：首先需要新预算确认最终worker的完整14查询、绑定及独立重放；然后才细化剩余提示、信息/概率、循环和P1.2证明合同。候选六项条件均未解决，proof_ready、complete_action_coverage、global_optimality始终false。不实现求解器，不自动启动后续P2/P3/P4工程，不提交或推送Git。
