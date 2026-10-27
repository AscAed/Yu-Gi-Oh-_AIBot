# 天玑完整路径回归与新scope六阶段验真

## 冻结范围

本批使用独立scope `tenki-placement-validation-v1`，目录为`data/runtime/p1-tenki-placement-validation-native-2026-10-23`，最多6次worker请求、7200秒墙钟、单worker顺序执行、每请求30秒。历史累计26次、未知0；所有旧scope与未使用槽位封存。本批只触达固定天玑前缀的区域18、区域0响应、opcode13 false/true及两个分支的独立重放，不完成检索或终场，不提升四项证明、完整动作或概率资格。

## 实施关口

1. 先修复stage5/6局部导入和父收据决策尾继承；自动响应必须绑定原始帧、Choice和字节，并由独立oracle确认唯一合法动作。Rust以专用第三种`batch_kind`固定scope、路径、seal和收据；旧模式字节与合同保持兼容。
2. synthetic workflow必须经过生产分派、共享预检、收费门禁、资产扫描、worker适配与收据保存。覆盖双分支/重放、超时与恢复、失败父阶段阻断及唯一自动响应。
3. `verify-only`只以冻结提示和保存材料复算，不重新解析实时资产。新scope首次候选资产读取前独占保存窗口起点；窗口起点检查先于候选请求的CDB验证，资产扫描、预检与核验均计时。
4. 通过Python、Rust格式、全目标Clippy、串行workspace测试和examples后，冻结源码及计划文档，隔离构建CLI/worker/runner，保存构建关联与源码归档。重算最新runner修复交付、八份旧账本、blob、请求、结果和保护文件。
5. 仅在上述检查完成且会话剩余额度足以收尾时创建窗口。首次身份采集后冻结stage1请求、manifest、输入和seal，运行prepare-only及只读preflight；新增调用必须为0，收费账本必须不存在。
6. 原生阶段按固定顺序1到6执行：opcode18五个区域响应；按坐标0/8/0到opcode13；false执行及重放；true执行并停于含两张同名目标的opcode15及其重放。每个后继请求只从认证父收据和公开菜单派生。任何异常立即停止，不修改线路、不重试、不续开窗口。

## 证据与暂停

原生整体成功要求六阶段通过、消费6次、未知0。`verify-only`只复核已存在材料，不补发缺失阶段、不扫实时资产、不改写收据或汇总。报告分别保存源码、构建、输入、资产身份、收据、runner原始输出、耗时、消费和缺口；原生失败不回写历史scope结论。普通部署和active资产不切换，不提交或推送Git。每批结束更新`TASKS.md`，向`docs/TESTING.md`顶部追加实测，并保存可恢复断点。

## 执行状态

本计划已于2026-10-23执行完成：六阶段消费6次、未知0，stage4与stage6独立重放通过；只读verify-only再次验证有效且新增调用0。实测边界、构建/归档哈希、测试结果和交接约束见[本批断点](2026-10-23-tenki-placement-validation-handoff.md)及[`docs/TESTING.md`](../../TESTING.md)。该结果仅是冻结前缀的局部证据；四项资格保持false。
