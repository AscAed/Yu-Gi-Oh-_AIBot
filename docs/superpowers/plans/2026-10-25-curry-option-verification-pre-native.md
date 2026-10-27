# Curry option verification：原生前离线验收

## 固定范围

本轮绑定Curry V3风险预留，准备并执行独立的`curry-option-verification-v1` scope：最多7次worker请求、7200秒、单worker串行、每次worker超时30秒。固定输出根为`data/runtime/p1-curry-option-verification-native-2026-10-25/`。旧Curry七槽位及其他scope均不复用。

V3预留报告SHA256为`14c13e4992673115c0211259dd7d035d968b9c36518c28b4a4ea159ff06ad43f`，reservation ID为`09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63`。认证历史子集为9账本、32次、未知0；政策预留7次、规划基数39。旧confirmation实际消费和全部历史实际累计仍为null。

固定七阶段为：1) 空前缀找到唯一Mooyan Curry command 5；2) 激活后到区域18；3) 选择坐标0/8/0、响应`[0,8,0]`到opcode14；4) 选项0到下一己方idle，RECOVER 200且LP `[8200,8000]`；5) 独立重放第4步；6) 选项1到下一己方idle，RECOVER 200且LP `[8000,8200]`；7) 独立重放第6步。任何未知提示、错误、资产漂移、输出失配、未知消费或过期立即停止，不改线路、不重试。

四项资格`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`始终为false。本轮不验证终场、全卡、求解器或完整游戏树。

## 离线实现及验收结果

新增第三种固定Rust批次`curry-option-verification-v1`及独立Python入口、报告合同和schema；它使用V3 acceptance与reservation角色、21项输入绑定、独立scope/目录/seal/收据类型，并保留旧validation与confirmation分支。`--verify-only`先于身份扫描及窗口/请求/账本创建分派，只能核验已保存材料并将零调用诊断写到独立target子目录。

独立审阅发现并修复verify-only成功提升漏洞：现核验器从经哈希绑定的process diagnostic读取原始stdout，要求严格单JSON，并将成功状态、消费增量、ledger和V3会计字段与收据精确比较。损坏stdout的失败记录可保留；伪造为成功在调用只读runner之前被拒绝。另有回归保证部分输出的合法`runner_timeout`保持原失败语义，未知消费继续未知。两项修改仅影响`python/ygo_eval/native_curry_option_validation.py`及其测试。

最终全套Python测试显式枚举63个顶层文件，命令为`py -m pytest <target/curry-option-verification-python-tests/top-level-test-files.txt所列文件> -ra -q -p no:cacheprovider`：494通过、9跳过、166个子测试通过，677.40秒。跳过项为两项Windows目录符号链接能力限制，以及v3/v4报告、本机引擎、真实快照/报告、实际v2报告、完整策略报告和赛事独立配置等opt-in。完整日志SHA256为`df283c53e20cc84afdd89930e3ac6426a694c0d03ff91e65919ce81f6a0813c2`；测试文件清单SHA256为`3ded520041821aeb951f3f63c9a17508b72338d7ea334737a37994568d6aeae4`。修复后聚焦组89通过、58个子测试通过。

Rust总检在隔离target`target/curry-option-verification-rust-target`完成：`cargo fmt --all -- --check`通过；workspace all-targets Clippy通过；串行workspace为328通过、36忽略、0失败（87套）；examples为47通过、1忽略、0失败（9套）。所有Cargo编译检查均为offline/locked并显式指定同一隔离target。日志分别保存在`target/curry-option-verification-python-tests/rust-fmt.log`、`rust-clippy.log`、`rust-workspace.log`、`rust-examples.log`。本机真实资产opt-in、doctor及48手评估未运行。

第三种Rust scope由独立审阅通过；Python stdout/timeout修复经第二轮独立只读审阅通过。最新V3报告`--verify-only`于2026-10-25复验`valid=true`、`native_calls=0`，reservation ID及报告SHA仍与固定值匹配。未运行新scope runner、worker、FFI或资产扫描；尚未创建新窗口或收费账本。

## 收费前固定顺序

后续实施必须先冻结源码及本计划文档，再建立隔离build记录和CLI/worker/runner副本并核对哈希；只读复验V3预留、九份旧账本及保护材料。首次候选资产扫描之前才独占持久化新窗口起点，随后采集普通/赛事身份、冻结manifest和stage1请求并执行prepare-only。prepare必须记录native_calls=0且不存在收费账本，才可执行七阶段。源代码与原生产物在实验期冻结。

同一实验期仅使用本scope、原窗口、原收据和原账本；完成后运行只读verify-only，不补发缺失阶段。最终文档、身份和final-build另行保存，普通部署、active资产和Git提交状态不变。
