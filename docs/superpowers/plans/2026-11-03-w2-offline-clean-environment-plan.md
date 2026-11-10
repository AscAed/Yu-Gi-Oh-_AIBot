# W2离线工作台候选包与干净档案验收

## 范围

本批按W2门禁验证当前源码构建的工作台CLI、候选包内的catalog路径、干净草稿目录、牌组草稿保存/重开、JSON/YDK往返及进程重启恢复。候选只放在忽略目录`target/w2-clean-20261103/package-candidate-02`，未覆盖`dist/ygo-local`、未创建正式发布或安装包。测试在同一Windows主机上的隔离目录完成，不等同于干净虚拟机或另一用户账户验收。

## 已完成

1. 只读检查确认`scripts/deploy-local.ps1`会重建workspace、覆盖固定`dist/ygo-local`、导入全局快照并运行`engine doctor`，不适用于本批隔离候选，因此未运行。
2. 使用`cargo build -p ygo-cli --offline --locked --target-dir target/w2-clean-20261103/cargo`构建源码CLI，成功。未联网补依赖。
3. 在候选目录放置CLI、`workbench.cmd`和catalog快照`catalog-1b0564fd61eec4730828fea1d48391aa1598bca3157c255454a8dcf487485d6d`。快照SHA-256为`3c0fa6249f4e5172488bf325f8d659070cfefb3d93115b7ec690e0486da4cbf7`；CLI SHA-256为`1d1dda980cdbe220f3ea2c3b3193791b02b35bb5548840fa2bf1c84357b16021`。`workbench.cmd`以包内相对路径定位草稿和快照，未配置分析。
4. `package-candidate-02`从空草稿目录启动；首页和本地catalog卡号检索可用，检索仍标记译文`unverified`。保存并重开含重复卡号及三分区的草稿后，JSON和YDK导入/导出保持顺序与分区；停掉服务并从同一候选包重启后，草稿ID、revision和牌组内容不变。逐项机器记录见`target/w2-clean-20261103/package-candidate-02-evidence/clean-profile-acceptance.json`。
5. 验收后将临时草稿、导出文件和运行日志移至独立证据目录，候选包恢复为空用户profile。ZIP候选`target/w2-clean-20261103/ygo-workbench-candidate-20261103.zip`已解压到带空格的路径并重新启动；新profile、包内catalog检索、写入及重启重开通过，证据见`target/w2-clean-20261103/package-candidate-02-evidence/archive-extract-acceptance.json`。

首次候选`package-candidate-01`的自动化脚本在异常清理阶段遇到Windows进程树权限错误，不能据此判定产品成功或失败；候选进程已按精确可执行路径停止。该次记录和脚本错误保存在`target/w2-clean-20261103/package-candidate-attempt-01-failure.json`，随后以修正清理方式完成候选02验收。

本批未启动引擎、worker、FFI、doctor或分析请求。身份文件绑定HEAD、脏工作树diff、Cargo.lock、CLI源文件、CLI产物、候选包文件及catalog快照，见`target/w2-clean-20261103/package-candidate-02-source-identity.json`。ZIP SHA-256与所有文件身份也记录在该身份文件中。

## 仍开放

- 当前旧`dist/ygo-local`不含`workbench`命令，因此没有旧工作台发布包可用于真实升级和旧草稿迁移。legacy bare Deck JSON导入只证明一种文档格式能读入，不能替代安装包升级验收。
- 本批是同一主机上的隔离目录和profile；尚未在干净Windows环境验证系统运行库、安装、卸载、资产搬迁、升级后用户数据保留或回滚。
- 候选二进制及冻结catalog只用于本地候选验收；没有授权或执行发布切换。P4-R5双资产及可比研究账本门禁仍独立开放。

## 下一步

裸Deck JSON→V1兼容夹具和[profile迁移合同](2026-11-03-w2-draft-migration-contract.md)已单独交付，但不代表曾存在可升级旧包。下一步先定位旧工作台包/实际profile版本；若不存在，则在独立干净Windows用户或虚拟机复核启动、资源路径、草稿往返和默认`analysis_not_configured`，再交付安装/配置约定。只有真实升级和回滚证据绑定同一源码/产物/资产身份后，才能评估是否满足W2；本记录不关闭W2。
