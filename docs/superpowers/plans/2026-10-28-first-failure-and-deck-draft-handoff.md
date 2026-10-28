# 首次失败诊断与牌组草稿基础交接

日期：2026-10-28

## 基线与边界

开始时位于`main`，HEAD为`6e5fade1fcff6c090de391bb35f401475bb43df1`；当时工作区源码身份为`b9fcac0b…885121d8`、551项且缺失0。该身份是本批实施前基线；本批修改后没有生成新的发布身份或部署包。保留既有工作区/历史证据，未提交、推送或切换部署。

## 本批交付

- A1：将首次调用结果级失败（`DuelResult.error`及`QueryWitness::capture`失败）接入v2诊断验证。验证器从收费账本认证首次请求、用途、预算、结果及失败分类，保留已收费结果；不生成可信查询、成功资格、收据或可恢复前缀。传输错误和预算拒绝仍走原路径。
- B1：新增独立`DeckDocumentV1`及schema；支持空/部分草稿、有序三分区、重复卡号、JSON/YDK导入导出和分区增删。草稿始终不代表完整合法牌组。
- CLI新增`ygo deck draft create|show|edit|import|export`。默认独占创建；显式`--replace`才替换，并先同步同目录临时文件。未知卡在无catalog时标为未核验，有catalog时只报告未知，不修改卡号。

## 验证

聚焦命令与结果追加到[`TESTING.md`](../../TESTING.md)。完整workspace串行测试运行记录在`target/a1-b1-implementation/workspace-test.log`。本批不执行引擎worker、FFI或原生研究调用；部署、Git提交及推送均未执行。

## 下一步

后续可独立推进B2本机中文浏览器工作台与C1既有39卡中文字段核验。A3真实执行持久化和安全续跑仍在A1回归之后另行计划。Ground Collapse opcode24的原生发现、接受和重放仍需新scope、预算与窗口。
