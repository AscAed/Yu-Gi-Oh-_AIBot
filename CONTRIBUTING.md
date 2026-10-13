# 贡献指南

- 规则、卡片效果和 banlist 行为必须有可重复测试。
- 外部引擎输出先转换为统一事件，再进入搜索层。
- 不把卡图、未确认许可的完整卡库或第三方二进制提交到仓库。
- 搜索结果必须携带规则、卡库、banlist 和引擎版本。
- 未支持的卡效或协议不得静默当作已验证成功。

常用检查：`cargo fmt --all -- --check`、`cargo test --workspace`、`py -m ygo_data.cli validate --input tests/fixtures/cards.sample.json`。
