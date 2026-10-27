# 基线与可行性审计工具

本页说明首批工程工具的使用边界。当前完成状态见[TASKS](../TASKS.md)，逐次实跑身份、命令、结果和消费见[TESTING](TESTING.md)。目标与方法依据[产品愿景](PRODUCT_VISION.md)、[最优性研究](OPTIMALITY_RESEARCH.md)及[首批实施计划](superpowers/plans/2026-10-19-baseline-audit.md)。

## 身份和构建记录

`ygo engine identity --config <toml> [--output <json>]`只读采集配置对应的实际资产，按逻辑角色记录worker、DLL、CDB、脚本和清单。沿用当前运行时的相对路径规则：相对路径基于进程工作目录，不基于配置文件目录。报告不嵌入个人绝对路径或完整配置。

`python -m ygo_data.identity capture`直接调用该CLI重查两套运行配置，汇总Git、实际工作区、工具链和CLI。它不会把外部JSON中自行声明的身份当作已验证输入。工作区身份与提交身份分别表达；时间戳不参与内容身份。

`python -m ygo_data.identity build-record`包装实际构建命令，记录执行前后源码、工具链、退出码和产物。已有二进制来源仍为未验证；一次成功命令及哈希关联只是一份构建记录，不证明构建可复现，也不独立证明每个产物一定由该命令重新生成。

以下命令在仓库根目录执行；输出文件采用独占创建，重复运行请使用新的证据文件名：

```powershell
$env:PYTHONPATH='python'
py -m ygo_data.identity build-record --repo . --artifact cli=target/debug/ygo-cli.exe --artifact worker=target/debug/ygo-engine-worker.exe --output data/runtime/baseline-2026-10-19/build.json -- cargo build --offline --locked -p ygo-cli -p ygo-engine-adapter --bins
py -m ygo_data.identity capture --repo . --cli target/debug/ygo-cli.exe --ordinary-config configs/engine.toml --tournament-config data/runtime/tournament-2026/engine-development.toml --output data/runtime/baseline-2026-10-19/workspace.json
```

现存dist中的`ygo.exe`是部署脚本复制后的名称，不能直接当作新CLI来调用新增命令。

普通运行配置和赛事配置须分别采集。`doctor`仅用于资产/ABI诊断，不证明构建来源或规则覆盖；相同二进制哈希也不能替代源码关联记录。

identity中的`consistent`限定为文件齐全、双采样稳定及脚本清单与实际字节一致。引擎manifest在此按原始字节散列，不解释其中的构建/ABI声明；这些声明及DLL可加载性仍由doctor和实际执行另行核验。

## 覆盖清点和中文显示数据

`python -m ygo_data.coverage inventory`只读打开显式指定的CDB，结合发行依据和脚本清单清点声明范围。首批截止日期为2026-10-19。发行、区域、预发行、规则生成物、alias及身份未决项分别记录；未知不补成正式发行。统计分母是已声明且有证据的范围，不是卡库行数。

普通无效果卡没有专用脚本不必然是缺失；alias委派、动态加载或证据不足应保留相应未知。静态脚本依赖只能说明已发现的引用，不能自签运行覆盖。

中文来源、版本、原始字节哈希、取得方式、许可依据和限制单独登记。名称、正文、名称别名和字段各自保留来源及核验状态；引擎alias和中文名称别名不是同一关系。中文层不改变现有catalog、知识或旧报告身份。来源未通过时仅形成候选/缺口报告，不启用正式中文资格。

## 研究和动作审计

案例输入需冻结完整合法牌组、五张实际起手、资产/规则/禁限、双方可见信息、对手资源、随机分布，以及正常终场和提前胜/负/平的目标评价。seed只用于复现，不作为决策信息。协议验证不等于已证明所有游戏分支完整。

动作审计用独立协议oracle对照响应字节；不复用被测解析器生成期望集合。提示可解析、协议响应一致、原生可达、搜索完整及最优性是不同结论。未知提示、组合上限、未触达和beam裁剪保留为缺口。

v1仅定义一个目标分量`terminal_utility`，正常/提前胜/负/平均须有整数评价；多目标求解未实现。`proof_input`只是用途声明，结构通过仍为`proof_ready=false`。当前原生入口只执行冻结标准场景，不执行概率分布或隐藏信息策略。完整参数、支持矩阵及预算负例见[RESEARCH_AUDIT](RESEARCH_AUDIT.md)。

原生批次上限是8案例、每例512请求、总4096请求及2小时实验墙钟，单worker超时30秒。执行、查询、失败、审计和独立重放均计入；重开不退款、不重置旧消费或批次起点。不必用满预算；触限只说明截断，不说明无解或最优。

## 运行和保留规则

- 先设置`$env:PYTHONPATH='python'`；新证据写入忽略目录`data/runtime/baseline-2026-10-19/`。
- 不修改active快照、不覆盖普通dist、不更新冻结资产，不将本批审计消费混入未来48手矩阵。
- 外部原文、卡库、脚本、DLL及个人配置不进入Git；可提交来源元数据和合成测试夹具。
- 外网终端命令必须在同次调用配置127.0.0.1:7897代理。基础清点和冻结资产上的实验可离线运行。
- 证据应保留请求、原始帧、独立响应对照、实际账本和失败，不能只保留成功摘要。

本批工具不提供HTTP/UI、正式v6、全卡支持、通用证明或普通用户可迁移安装包。对应后续关口见[路线图](ROADMAP.md)。

原窗口到期后的续办必须取得明确用户授权，并以同账本不可覆盖的追加窗口记录限定新增次数；不得修改原起点或清零总消费。2026-10-19用户批准的例外仅为赛事执行/重放两次，见研究审计文档。
