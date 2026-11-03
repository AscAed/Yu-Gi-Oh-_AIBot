# W2旧草稿导入与profile升级合同

## 当前事实

当前可读的旧格式只有两个不同边界：用于人工导入的裸`Deck` JSON和YDK交换文本；它们不是工作台profile目录格式。裸JSON兼容形状要求且只接受`main`、`extra`、`side`三个字段，顺序和重复卡号保留，导入后归一成`DeckDocumentV1`并使用默认标题`Imported deck`。本文件中的“v0”只是测试夹具标签，不表示仓库曾发布过该版本。

正式草稿JSON是`schema_version: 1`、`kind: deck_draft`，字段与[deck-document-v1.schema.json](../../../schemas/deck-document-v1.schema.json)一致。缺字段、额外字段、重复JSON键及未知schema版本都失败关闭。YDK只带分区和卡号，不保留标题及其它元数据；导入时使用`Imported YDK deck`。这些输入都不核验卡片规则、卡片身份或牌组合法性。

CLI `deck draft import`将用户显式选中的裸JSON/YDK写成版本化V1文件；目标存在时默认拒绝覆盖，只有显式`--replace`才替换，解析或校验失败时保留原目标。工作台HTTP `/api/import`只返回`saved:false`的草稿；它不会自动写入profile。

工作台profile文件有另一层存储合同：目录内`<32位小写hex id>.json`保存`StoredDeckDraft { id, revision, draft }`。`revision`按V1草稿内容计算，目录由`.ygo-workbench.lock`独占锁保护。当前格式没有profile级版本清单或旧profile迁移器；不能把裸Deck导入器当作整目录迁移器，也不能在服务运行时复制/替换profile。

## 兼容夹具与已实现的导入门禁

`tests/fixtures/deck-draft-legacy-bare-v0.json`定义带重复卡号和分区的最小旧JSON输入；配套`*.expected-v1.json`定义精确归一结果。Rust domain测试核对解析、所有分区顺序和重复值，并验证V1 JSON可再次读取；CLI测试核对命令输出、隐式覆盖拒绝、`--replace`下坏输入失败时源文件与目标文件字节不变。Python schema测试确保预期迁移结果通过V1 schema。测试结果见[TESTING](../../TESTING.md)的2026-11-03 W2迁移合同记录；命令、结果、输入源码/fixture和测试二进制身份另存于忽略目录`target/w2-migration-20261103/verification-results.json`。

## 未来profile升级协议（尚未实现）

在存在可识别的旧工作台包前，本合同只定义门槛，不声明升级成功：

1. 旧包必须给出确切版本、profile格式、CLI/worker身份和配置路径；旧格式来源不明或混合格式时停止迁移。
2. 用户先停止服务。迁移器核验目录已解锁，对源profile做只读清点并生成逐文件路径、字节长度、SHA-256和格式分类清单；保留原目录及字节备份。
3. 在同卷的全新staging目录转换副本，逐个验证ID、revision、V1 schema、字段完整性、分区顺序、重复卡号和迁移映射。未知文件、损坏JSON、重复ID或未支持版本均阻断切换，不自动丢弃或猜测字段。
4. 预检要证明每个输入对应且仅对应一个输出；未改变的字段逐值相等。生成迁移前后哈希、版本、计数、失败列表和候选CLI/catalog身份报告。普通启动不自动迁移。
5. 通过验证后才允许进入可恢复切换：先持久化journal和备份位置，再切换目录；任何中断或身份不一致都保留源、备份、staging及journal并停止写入。恢复只能按journal明确的阶段完成切换或回滚；不能判定时等待人工处理，不重试、不覆盖。
6. 独立重开后逐文件核验新profile，确认revision一致、原profile备份仍可读、第二次重开不再产生变更。只有新旧package、profile、配置和catalog身份一致且回滚门禁通过，才可评估W2升级验收。

旧`dist/ygo-local`没有workbench命令，也没有可迁移的工作台profile，所以第1项前提不存在。实际旧包升级、profile迁移、干净Windows用户/虚拟机安装以及回滚仍是开放门禁；本合同和格式夹具不授予部署切换。
