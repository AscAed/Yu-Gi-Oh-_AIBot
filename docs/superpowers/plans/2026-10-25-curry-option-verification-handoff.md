# Curry V3预留绑定的七阶段验证：本批断点

## 当前结论

本批 `curry-option-verification-v1` 在stage 2失败后停止，**不重试、不运行stage 3–7，也不复用剩余6个槽位**。stage 1通过并完成一次收费请求；stage 2 runner在账本检查后、`batch_call`前以退出码2退出，stderr为Windows共享冲突`os error 32`。stage 2没有收费receipt。

`--verify-only`执行0次原生调用，确认新账本`consumed=1, completed=1, unknown=0`；报告为`valid=false`、诊断`incomplete_saved_stage_files`，因为stage 2只有冻结请求、输入、失败report和进程诊断，没有receipt。此结果如实表达未完成批次，不证明stage 2请求执行成功，也不把全部剩余额度改成消费0。

## 冻结来源与会计

- scope：`curry-option-verification-v1`；额度7次，窗口7200秒，worker超时30秒；窗口起点`1792898169`。
- 固定V3预留：报告SHA256 `14c13e4992673115c0211259dd7d035d968b9c36518c28b4b4ea159ff06ad43f`，delivery acceptance SHA256 `704a72b2ad65ba95874030f199158a673ce18e19901b29d9bfb63f3fb8d78318`，reservation ID `09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63`。
- 原生时点源码身份`50bc44ed37aefdc39f33a61afaca021a8dfbe037869f118b5ad3e129d4011b24`，544项。构建记录SHA256 `6d4b079ab3fd3971b8c1ecf41a974b93171d5872c89aa576019688d87444ce66`，前后源码一致、退出码0；`reproducible_build_proven=false`。
- 原生源码归档SHA256 `d8058a5043a8367be32fc76d966c84c1089e5369fc826c8e56b17fbdb7b1f600`，清单SHA256 `4a87cbcf5173ff854e7aa7df1afedf0c89d01e72efbe0745e41d6130a3bd1463`，544个成员。CLI/worker/runner SHA256依次为`44bd5206609d021781a5029232d751bd519524876e770084c03314a180426f48`、`79c65f276d34097c11eb3dfa4efed5c3850ba2a760415fb0af7064909af7b9d3`、`aae876badfe006098dbffa98b61b8f76818cc5dbaab142cc3d499f354eec8952`；`native-artifacts/`复制件逐项匹配。
- manifest SHA256 `60106527e484763dd8b9f323b847a7ed051e0302dffabf8f48f0f71a3347e44b`，context `5cc1f424c3d263cac0d1df335520ba58938589d8509aec98cef1cc193fe083e0`，21个输入角色。prepared SHA256 `7f94f982f89ca1c2b720f32250f8e4f9451ec0eb99ba5a4afcec7dd7fc23c5ee`，`prepared=true`、`execution_ready=true`、`native_calls=0`。
- stage 1 report成功，收费账本最终SHA256 `7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`（2,726字节）；summary SHA256 `21f7818aae8595f2ee1fb18b23be39ad5802d26e257c225fa1fa26a33f1b73e9`。stage 2 report为失败`runner_output_invalid_or_nonzero`。
- 根级stage 2进程诊断引用SHA256 `be2e52a1dc689304830802ca74a8fa30436b53879863ff120170344810f492c2`，引用的进程元数据文件SHA256 `378349a926c131a6c22cd2fe003425dffd0440ebe6eefd6efa79cacf18fcd108`。原stderr为528字节，SHA256 `f7a73b6c29c00e90778b0dda4521e468817aa74184289768f25f4e61b1549227`；stdout为空流SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。原始stderr包含固定Windows共享冲突文本；没有记录到`batch_call`。
- 根级stage 1/2进程诊断引用分别为`3b134ea8b3d24db2b26856b618a03df1a2b94051831fe87645b5c86e5e9a3ede`和`be2e52a1dc689304830802ca74a8fa30436b53879863ff120170344810f492c2`；stage 2诊断解析得到的稳定错误码仍为`runner_output_invalid_or_nonzero`，更具体的OS error 32保留在原始stderr侧车中。
- 零调用恢复报告SHA256 `831201cd9166bf271c17fd8f6adbee4afa1964b9d1b7087a3119d42edced1a8a`，位于`target/curry-option-verification-checks/14a607e5e6a744fd95229e81403c98ca/verification.json`。

| 口径 | 本批结果 |
|---|---:|
| 已认证旧历史子集 | 32次，未知0 |
| V3政策风险预留 | 7次 |
| 原规划基数 | 39次 |
| 本scope认证消费 | 1次，未知0 |
| 认证子集合计（旧＋本批） | 33次 |
| 规划总数（原基数＋本批） | 40次 |
| 旧confirmation实际消费 | `null` |
| 全部历史实际累计 | `null` |

`proof_ready`、`complete_action_coverage`、`global_optimality`和`native_probability_verified`均为false。stage 2未通过，因此本批不证明区域18选择、opcode14发现或任一选项结果；stage 4/5回复方、LP与重放对照也未触达。

## 验证及限制

原生前检查已完成：63个显式顶层Python测试文件，494 passed、9 skipped、166个subtests passed；Rust fmt与全目标Clippy通过，串行workspace 328 passed/36 ignored，examples 47 passed/1 ignored。跳过原因列在[`TESTING.md`](../../TESTING.md)原生前记录。独立只读审阅在原生前通过，审阅没有覆盖这次真实Windows共享冲突。

准备和阶段执行日志位于`target/curry-option-verification-python-tests/`；完整原始请求、收据、账本及诊断位于忽略目录`data/runtime/p1-curry-option-verification-native-2026-10-25/`。普通部署、active资产、九份历史账本及旧V3预留保持各自来源绑定；本批没有运行doctor、48手评估或额外查询，没有提交或推送Git。

## 后续续接门禁

1. 保持本scope、窗口、请求、账本、stage报告和原始诊断只读封存；不得通过恢复、换路径、换scope别名或改写summary继续收费。
2. 下一批先以保存源码归档和诊断定位OS error 32的具体文件操作，使用合成/只读测试复现与修复；禁止借此执行normal。
3. 修复后的`verify-only`只能用于只读核对已存在证据，不会把本批`valid=false`改为成功，也不能恢复这6个槽位。
4. 任何新的原生验证都必须另行确定固定输入、scope与预算，并在离线门禁完成后重新获得授权；旧confirmation实际消费及全部历史实际累计仍为`null`，不得用7次预留代替实际收费记录。

文档冻结后的构建记录、源码归档、文件清单及最终验收保存在本scope忽略目录`data/runtime/p1-curry-option-verification-native-2026-10-25/final-build/`；其中验收文件给出该时点源码身份、文件数、构建与证据清单。该后处理产物不改变或替代原生时点绑定。
