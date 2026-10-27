# Curry v2风险预留恢复：断点交接

## 当前状态

本批V2合同、合成恢复流程、独立审阅和Python全套测试均已完成；真实只读验收已按固定停止规则失败。本轮新增原生调用为0，不创建scope、窗口或收费账本。

只执行了一次固定真实命令：

```text
python -m ygo_eval.research prepare-curry-consumption-reservation --report-version 2 \
  --baseline-dir data/runtime/p1-curry-recovery-synthetic-e2e-offline-2026-10-24 \
  --output data/runtime/p1-curry-consumption-reservation-v2-offline-2026-10-25/reservation.json
```

退出码1。报告SHA256为`5fb0cd2e10d3477fd09544e85e02b5234386b60668721ba33bc85ccb1db745da`，5,338字节；通过V2 Python合同和JSON Schema。`previous_failed_attempt`通过，首个业务检查`latest_delivery_chain`失败，稳定诊断为`independent_review_invalid`，其后`real_v2_report`、`old_confirmation_scope`、`historical_ledgers`和`input_stability`均为`not_run`。

### 阻断根因

真实审计引用的固定`independent-review.json`哈希匹配，但其内容没有`public_cli_bypass_found`字段。当前交付校验器明确要求该字段为`false`，因此真实输入按严格门禁失败。原review材料同时记录`kind=curry_recovery_synthetic_e2e_independent_review`、`result=passed`、`native_calls=0`和`real_audit_run=false`，但不能通过推断补上缺失字段。

该失败表示审计器与被固定的历史review合同不兼容；它不证明历史review失败，也没有完成本轮对业务报告、confirmation冻结输入或九份账本的核验。不得改写锚定review、弱化门禁后覆盖报告，或把未运行阶段解释为成功。

## 固定记账与资格

- 本次原生调用：0；`execution_ready=false`。
- 本次预留：`recorded=false`，reservation ID为`null`。
- 规划基数：`null`；本次没有发布39。
- 旧confirmation实际消费、累计消费和未知消费仍为`null`。
- 此前已认证的历史子集仍是9份账本、32次消费、未知0；本批没有重新核验，故只作为既有基线引用。
- 全部历史实际累计仍为`null`；保守政策预留7次尚未记录。
- 旧七个槽位继续封存。`proof_ready`、`complete_action_coverage`、`global_optimality`和`native_probability_verified`继续为false。

因为报告失败，本批没有运行`--verify-only`。报告及其工具源码归档、文件清单保留在正式忽略输出目录；旧V1失败报告SHA256仍为`17dd4b3f08c4c13c1d440bf6641a3fa4b9c9ae498e652c5d852156c8891ee3e7`。新V2报告SHA256、原V1报告SHA256及V2 schema验证结果已在[TESTING](../../TESTING.md)记录。

## 审计源码与验证证据

审计前完整源码冻结位于忽略目录`target/curry-consumption-reservation-v2-tests/real-audit-source/`：身份`be9414a756ab436ba12221f178ea23bbb55ac00bfa0ff55c170ca69647bafc98`、535项；完整ZIP SHA256 `8104ee889d2ae0a686fb5b5a3cba8add1076ad22f29e029f871ee825eea9eb67`；文件清单SHA256 `08dd2255a19eea71b1a8d92c03051e1d7b20717265044b91ce7f4005dfb180c9`。V2实际报告还包含七个工具源成员的独立归档和清单。

文档收尾后的源码身份、完整归档及清单另存于忽略目录`target/curry-consumption-reservation-v2-tests/final-doc-source-final/`；其`freeze.json`记录对应哈希和身份，避免把文档收尾源码误当作审计时源码。

本批机器可读验收状态和最终证据体积分别见`target/curry-consumption-reservation-v2-tests/acceptance-v2.json`及`evidence-size-final.json`。验收状态明确为阻断，不将本次失败改写成预留成功。

全量Python测试显式列举60个顶层测试文件：472通过、9跳过、147个子测试通过（772.47秒）。日志`target/curry-consumption-reservation-v2-tests/pytest-full-v2.log`保留`-ra`逐项跳过原因；空输入精确错误码收紧后的V2公共路径另有1项聚焦测试通过。独立复核为只读，检查V1/V2成员集、V2成功态非空输入约束、V1兼容和失败门禁；记录位于`target/curry-consumption-reservation-v2-tests/independent-review-v2.json`。

证据体积记录`target/curry-consumption-reservation-v2-tests/evidence-size.json`统计了本批测试/冻结目录与V2失败输出目录：分别为13,230个文件、65,267,339字节，以及3个文件、352,946字节；本次遍历未遇访问错误。该统计仅覆盖上述两棵本批证据树，不代表对旧历史材料或ACL受限目录的全仓遍历。

## 后续续接约束

正式V2输出路径已被失败报告占用，不能在原路径重试、覆盖或删除。下一批必须先制定新的版本化恢复合同及独立输出锚点，说明如何兼容固定的旧review材料；保留本次V2失败报告和旧V1报告原字节。不能仅通过替换路径、修改profile哈希或跳过字段来绕过来源门禁。只有新合同下全部固定来源、冻结输入和九份账本核验通过，才能记录政策预留7次并发布规划基数39；在此之前实际总消费与旧confirmation消费均保持未知。

本批未运行runner、worker、FFI或doctor，未改变部署、active资产及Git提交状态。
