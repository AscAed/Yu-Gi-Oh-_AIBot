# 四次终场验真：离线交付与原生前阻断

先读docs/INDEX.md、TASKS.md、TESTING.md顶部，再核对本机`data/runtime/p1-terminal-followup-2026-10-20/acceptance.json`、delivery-checkpoint.json及preflight-blocked.json。当前工作区未提交，保留全部历史文件和部署。

本批已实现terminal-followup入口、Rust固定两案例4次构造器、严格14查询零值门禁、Python固定顺序/失败停止/收据前缀恢复及独立v1报告合同。默认6次和旧2/16/4096模式保留。独立审阅及离线总检见TESTING；工具通过不代表两线路已原生通过。

## 阻断与预算

历史累计9+8+1+2=20次、未知0，账本与保护文件未改。8/1/2次的原生时点runner已带verify-recorded零调用验证。最早9次的原生audit哈希为：

- 首次：b6c68c92414e1fed0b46ef4d2e5c2be3a6b5aa797e0f8261481bfa90034bc4c3。
- 续办：b111cf5f5f015299517f80295a22c002b19efbb0c8cc685298f8d46794c3b7c7。

两份原构建记录哈希已核对，17份本机research-audit候选匹配0。该旧runner接口使用--recover，没有本计划要求的纯--verify-recorded入口。不能重编当前源码冒充原产物，不能仅凭报告自声明获得历史收据资格。

新入口在创建manifest、具体请求和收费之前拒绝old9_runner_unavailable。没有开始候选资产扫描，没有创建window-start或新账本，新4次授权全部未用；也没有“已耗尽的新窗口”。本批无目标FFI查询，legacy查询总数未知。build-offline仅表示离线工具构建，不能标作原生时点构建。两套候选配置未扫描、未切换，最终产物不继承Rabbit原产物资格。

## 下一入口

1. 从可靠备份找回上述两份原二进制；固定各自原构建及来源哈希。即使找到，也须单独设计旧--recover兼容的纯只读收据校验，确认不会调用worker、写旧目录或改变旧账本；目前代码明确阻断该未解决条件，不能直接删除门禁。
2. 重新审阅来源方案与本批冻结输入，保留既有父报告公开prompt7命令8、prompt9命令7及赛事48决策。不得调整线路或用隐藏牌序决策。
3. 通过全部前置门禁后，沿用既有交付目录恢复准备；不要调用首次建目录脚本、自动换名或新造预算。首次候选资产扫描前独占保存窗口，重新冻结源码/构建/双资产/两请求，先prepare-only再执行。
4. 仅赛事执行/重放通过后进入洗手牌后结束执行/重放，总计最多4次、2小时、每worker30秒。第一组收据保留消费2前缀，最终汇总当前4；任一失败即停止，不重试、不退款、不重开旧窗口。

无论原生后续是否成功，proof_ready、complete_action_coverage、global_optimality均false。没有正式v6、全卡或求解器资格提升；不自动提交或推送Git。
