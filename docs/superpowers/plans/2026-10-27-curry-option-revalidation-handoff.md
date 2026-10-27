# Curry七阶段再验真交接（2026-10-27）

## 状态

本批已完成并暂停。固定scope `curry-option-revalidation-v1` 的七个worker请求均成功收费并完成，独立只读 `--verify-only` 返回 `valid=true`。未运行终场、求解器、其他提示实验、doctor或48手评估；未切换部署或active资产，未提交或推送Git。

## 固定范围和来源

- 原生预算：7次请求、7,200秒；worker超时30秒，串行执行。窗口起点为Unix时间`1793031889`（2026-10-27 00:24:49 +08:00）。
- 输出根：`data/runtime/p1-curry-option-revalidation-native-2026-10-26`。prepare-only新增收费为0，保存的收费账本在normal前不存在。
- V3恢复delivery SHA256：`dbc0db354846fdc772305970c90f7dbcee0d10804aded678845dd7bdaffd7a55`；恢复报告SHA256：`69d2af394169d5773394e775718840ef9a3df22eac12167d2e7ba3c79484c468`。本轮重新运行来源校验通过。
- 预留ID `09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63`，政策`curry-unknown-reserve-seven-v1`。manifest固定22个输入角色，context为`e69be83d9eb082488a83b4c1b092fc29ecf05d7299116d9b099683be12c0eee4`。
- 原生时点源码身份`cb9d709e728366dae890258e71e00586ea360b4438662495c2988050aa11f5d0`，593项。构建身份`098981a0821f41d9a0cc609945555e2f8a9e0fe5c57016eeb7cc54057812b79b`；原生源码ZIP SHA256 `44b88010f9d589fe94005153f9ed456b65416df29f120ed1aa4267298060d03c`，文件清单SHA256 `c0d0067eb51e4aba5bd85324c7fa3f5cda2909114059b03325cf500c51f58744`。
- 原生runner、worker、CLI分别绑定SHA256：`d92d4dd4cb6d3475a67e7284c8548d7efac3bfeeaf312bfbe12299bafe6eb9d6`、`f2dc5ffe44676714b3b2c97de9a8ddb7c3ad17decd2ca0a41bf3f3f0ec3b5e48`、`87e24174c15ca7363f6a0c11628b80be49e31020f766b46db7feb5598741e852`。它们仍绑定原生时点build record，不因文档后源码变化而转移构建资格。

## 七阶段结果

每阶段均有`successful=true`、完整的收费前缀、`unknown=0`及匹配的独立响应校验。收据和报告位于正式根的`research/`下；阶段原始stdout/stderr和进程状态保存在`process-diagnostics/`。

| 阶段 | 检查点 | 收费前缀 | 结果 |
|---|---|---:|---|
| 1 Probe | 己方idle；卡号58074572唯一command 5激活 | 1 | 通过，单一激活项，停在己方idle |
| 2 Probe | 继承实际解决决策并激活 | 2 | 通过，停在opcode 18 |
| 3 Probe | 公开菜单唯一匹配区域`0/8/0`，响应`[0,8,0]` | 3 | 通过，停在opcode 14；两项描述按冻结顺序匹配 |
| 4 Execution | opcode 14选项0，响应`[0,0,0,0]` | 4 | 通过；RECOVER为player 0、200，LP `[8200,8000]`，停在己方idle |
| 5 Replay | 独立重放阶段4原请求 | 5 | 通过，`independent_replay_matches=true`，LP相同 |
| 6 Execution | opcode 14选项1，响应`[1,0,0,0]` | 6 | 通过；RECOVER为player 1、200，LP `[8000,8200]`，停在己方idle |
| 7 Replay | 独立重放阶段6原请求 | 7 | 通过，`independent_replay_matches=true`，LP相同 |

七个结果的响应oracle均为真，额外自动决策均经单一合法动作规则绑定；所有收费请求消费并完成。normal进程退出0、耗时954.67秒，单份stdout 3,559字节、SHA256 `3b64fad1a14845c92e8a422fa509d186fa4e74a0238d9d92d6362bf2b3d6e4fd`，stderr为空。其诊断保存于`target/curry-option-revalidation-tests/normal-execution-640ec24fca2d4262953d742672b9d0e0/`。

最终summary SHA256为`fcc3d1aebe8b97f6c954a56593c86461afd7b71613669e47c6c8e1ba0e0d9098`，报告整体成功，消费7、完成7、未知0。原认证历史33加新scope 7为认证子集40；风险预留7只用于规划，规划基数40加新scope 7为47。旧confirmation实际消费和全部历史实际累计始终为`null`。

## 零调用verify与保护

verify-only在独立目录`target/curry-option-revalidation-checks/0efeaf7cfe5041eaa809120c356f70fc/`保存原始stdout/stderr和退出状态，退出0，`valid=true`、`native_calls=0`，耗时80.499秒。输出SHA256为`c7845e0f303d0c21efaa213a1b94c8407e216d4883d750f85cd7ab8cb8ea7c97`；stderr为空。验证包括七份保存收据及账本，不补发阶段，不扫描实时资产。

复验V3来源和固定保护成功，保护映射89项，摘要SHA256 `e0014e127e6261db99128eef1f1ca26e00d4a6731155a0ab36611ae2ed7d791f`。新scope账本统计为7/7/0；原有认证来源未被改写。

## 验证记录

- 聚焦Python回归：66 passed、37 subtests passed，8.85秒。公共CLI合成E2E 1 passed，约100.07秒；覆盖prepare-only、完整七阶段调度、双分支重放及verify-only。
- 全量Python：显式枚举84个顶层测试文件；685 passed、9 skipped、181 subtests passed，0 failed，1,640.66秒。清单及`-ra`日志在`target/curry-option-revalidation-tests/python-test-files-92847bcb-3305-45f8-81a5-e45e87271db5.txt`和`pytest-full-c61a53dc-9e22-4462-ad53-f573b192d71b.log`。跳过原因：Windows目录符号链接能力限制2项；其余分别为v3报告、v4报告、本地引擎资产、本地快照/报告、实际v2报告、完整策略报告和独立2026赛事配置的opt-in或缺少环境材料。
- Rust `cargo fmt --all -- --check`、全目标offline/locked Clippy（`-D warnings`）、串行workspace及examples均通过。workspace汇总329 passed、36 ignored；examples汇总52 passed、1 ignored。忽略测试逐条原因保存在相应cargo日志。格式、Clippy、workspace和examples日志均在`target/curry-option-revalidation-tests/`。
- 独立只读审阅未发现阻断项。指出一个P3范围偏差：Rust合成runner fixture 使用既有的`target/curry-option-validation-tests/tmp/runner-e2e-*`，目录仍处忽略区且只含合成材料；源码保持冻结，未为移动该测试临时目录而改写已验真的构建身份。
- 测试跳过项均未用于推断本批失败或成功；真实资产opt-in、doctor和48手评估没有运行。

## 资格与下一断点

本批成功只授予此冻结Curry前缀的区域选择、opcode 14两个响应、RECOVER/LP结算及对应独立重放证据。它不证明完整Curry线路、全部动作覆盖、发行资格、概率、求解器或全局最优性。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均为`false`。

本批在此暂停。后续实验需基于剩余研究缺口另定scope和预算；旧scope槽位保持封存。当前正式结果和文档后最终交付索引见`data/runtime/p1-curry-option-revalidation-native-2026-10-26/final-build/delivery-final.json`。最终源码归档、文件清单及文档变化后的verify应与本文件及TASKS/TESTING/INDEX冻结后生成；不可覆盖原生时点归档、build record、收据或诊断。
