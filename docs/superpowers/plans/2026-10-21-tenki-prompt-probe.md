# 天玑opcode 13六次验真实施计划

**目标：**从已交付静态候选发现天玑激活菜单与13提示，验证false/true两个响应并分别独立重放。

**方案：**专用Rust单阶段runner及PromptProbeBatch封装CallJournal/JournaledAdapter；Python冻结来源、请求与依赖，逐阶段串行调用。技术栈沿用Rust workspace及Python标准库。

## 固定边界

已验收源码56524e90…0c7b993b、382文件，历史累计24、未知0。保留未提交工作和全部历史证据。新scope tenki-prompt-probe-v1，最多6次、2小时，每worker30秒；所有旧窗口封存。不运行14/24、命令6、完整检索/终场、求解器、doctor或48手评估，不切换部署或提交推送。所有完整动作、概率及最优性资格false。

## 顺序交付

1. 先失败测试，实现独立原始13校验（10字节、player0、description59877851398144、响应0/1小端）、六槽位收费门禁及不可覆盖收据。Rust门禁独立验证父结果、派生请求、阶段/用途、资产与剩余时间，禁止Python绕过。旧预算接口不改。
2. 新native-prompt-probe入口参数preparation/cases/baseline-dir/runner/worker/build-record/identity/window-start/output及prepare-only；独立manifest/stage/summary合同。绑定准备来源、天玑40/3/0及seed1，协议2无干扰无终场采集。普通/赛事身份分离，仅普通执行。
3. 六槽位固定：Probe空前缀→Probe唯一天玑激活到13→Execution false到己方idle→Replay false→Execution true到己方15单卡选择（两张69247929）→Replay true。后续请求仅从父resolved_decisions与公开菜单派生；true分支始终来自第2槽，不从false分支派生。没有唯一匹配或出现额外提示即停止，不搜索或重试。
4. decision_required为预期暂停状态，请求决策必须消费；额外己方自动决策只能来自原始单动作提示。重放比较事件/提示/checkpoint/steps/已解决决策/脚本/版本，归一化仅清除内存统计。不继续检索，不要求终场绑定。
5. TDD覆盖原始帧、描述/Choice/字节/序列、阶段顺序、第7次、错误用途、未知消费/到期/重开、失败后零后继调用、恢复不改旧收据、来源漂移、输出覆盖与兼容。独立审阅、Python全套、fmt、全目标Clippy、默认串行workspace及examples全部通过后才冻结构建。
6. 使用独占忽略目录data/runtime/p1-tenki-probe-native-2026-10-21。先构建及完整源码归档，再在首次候选资产扫描前独占写窗口起点，采集双身份，冻结manifest及首请求，prepare-only后原生。每阶段请求首次收费前独占写入；冻结后只写忽略证据，任错误、未知提示、漂移、重放差异或未知消费即停。
7. 收尾验账本和保护文件，零调用恢复，TASKS当前状态、TESTING实跑，保存原生/最终文档两个时点构建记录与完整源码归档、清单、耗时体积、验收及断点。按24+实际消费报告，不预填30；原查询数量未统计保持未知。无论成败暂停。

## 验收口径

前两次仅为发现证据，不补签重放。两分支执行和独立重放均通过、六次消费完成且无未决才整体成功。遇到中间区域等额外提示时，保存真实消费并以受阻批次收尾，不在原预算内调整线路。只授予冻结天玑13提示及对应响应的局部证据，不升级完整性、正式v6或全卡资格。
