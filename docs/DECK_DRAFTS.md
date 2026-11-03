# 牌组草稿

`DeckDocumentV1`是本地编辑格式，不替代运行请求中的`Deck`，也不表示牌组已符合完整性、禁限表、额外卡组或引擎支持要求。草稿允许为空、不完整、重复卡号及有意义的卡序；主卡组、额外卡组和Side分别保序。

文件与本机工作台共同使用`ygo-storage`中的草稿读写能力。CLI和工作台都采用独占创建；覆盖必须由CLI显式`--replace`确认。替换先同步同目录临时文件，Windows替换过程保留备份并在失败时尝试恢复。工作台还以目录独占锁阻止两个服务同时写同一草稿目录，并用内容revision拒绝多标签页陈旧更新。

## CLI

```text
cargo run -p ygo-cli -- deck draft create --output draft.json --title "我的草稿"
cargo run -p ygo-cli -- deck draft show --input draft.json
cargo run -p ygo-cli -- deck draft edit --input draft.json --output updated.json --zone main --operation add --card 89631139 --count 3
cargo run -p ygo-cli -- deck draft import --input deck.ydk --output draft.json --format ydk
cargo run -p ygo-cli -- deck draft export --input draft.json --output deck.ydk --format ydk
```

写入默认采用独占创建；目标已存在时拒绝覆盖。只有明确附加`--replace`才替换文件。替换先在同目录写入并同步临时文件，再切换目标；发生失败时保留或恢复原稿，并返回`deck_draft_*`结构化错误码。

`edit`通过`--zone main|extra|side`选择分区，`--operation add|remove`选择操作，`--card`为非零u32卡号，`--count`为正数量。移除数量不足时拒绝写出。JSON导入识别带版本的`deck_draft`及现有裸`Deck`格式，并拒绝重复JSON键。YDK只保存分区和卡号/数量，不保存标题；读取时逐行解析`#main`、`#extra`和`!side`。

`show`可选接收`--store`与`--catalog-id`来对指定本地catalog检查未知卡号。未指定catalog时状态明确为“未核验”；检查只报告未知卡号，不自动删除或替换。输出中的legality恒为`not_checked`，分析仍由原有完整牌组和规则门禁负责。

## 导入兼容与profile升级

裸`Deck` JSON只接受`main`、`extra`、`side`三个字段；导入会保留每个分区内的顺序和重复卡号，将它归一成`DeckDocumentV1`并使用`Imported deck`标题。测试夹具把这种无版本输入标为legacy bare v0；这个标签仅说明输入形状，不代表曾发布过v0应用或profile。

带版本JSON必须符合V1合同；未来schema版本、重复键、缺失/额外字段或非法卡号均失败关闭。YDK是牌组交换格式，不保存标题和其它元数据；导入时使用`Imported YDK deck`。CLI显式`deck draft import`会生成规范V1输出，默认拒绝覆盖现有目标，只有`--replace`明确替换；转换失败时保留原输入和目标。工作台`/api/import`只返回未保存草稿，必须由用户另行保存。

工作台profile里的文件不是上述裸JSON文件，而是`StoredDeckDraft { id, revision, draft }`包装记录，按32位ID文件名存储并用revision校验内容。当前没有profile级版本清单或profile迁移器；不能把文件导入能力当作升级整个profile的支持。停止服务、备份源profile、分阶段转换、版本/资产身份校验、回滚journal和独立重开都必须纳入未来的安装包升级验收，具体合同见[W2迁移合同](superpowers/plans/2026-11-03-w2-draft-migration-contract.md)。

JSON合同位于[`deck-document-v1.schema.json`](../schemas/deck-document-v1.schema.json)。

浏览器工作台的启动方式与HTTP边界见[WORKBENCH](WORKBENCH.md)。
