# CLI 服务合同

产品入口是 `ygo combo analyze --input request.json --output report.json` 与 `ygo combo replay --input report.json`。ComboAnalyzeRequest 包含完整 deck(main/extra/side)、opening_hand(5)、seed、rules=ocg-mr5、as_of、catalog_id、banlist_id 和 search。具体默认值与范围见 schemas/combo-request.schema.json。

AnalysisReport schema_version=2 记录解析后的不可变数据 ID、运行资产版本、卡名、scoring/budget/stats/termination/diagnostics，以及每条线路的 decisions、steps、checkpoint、raw/events、evaluation 和 replay_verified。result.status engine_verified 与 evaluation.kind heuristic 是独立维度。partial 表示存在未解析信息，不能称完整引擎验证。

读取报告的 replay 使用当前本机配置、原始数据版本和完整前缀，再比较轨迹、终场、脚本及评分；任何版本／内容偏离返回失败。HTTP/网页不在首版本机交付中。旧 ApiService::handle 原型不构成 HTTP 能力。
