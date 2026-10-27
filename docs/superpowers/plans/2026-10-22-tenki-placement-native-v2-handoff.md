# 天玑区域18与opcode13验真：v2迁移执行断点（2026-10-22）

## 当前状态

本批的v2单文件迁移、隔离构建、双资产身份采集和`prepare-only`已通过；原生阶段未通过。固定六阶段runner在stage 1产生`runner_failed`，没有阶段收据，账本只记录启动header和零消费起点检查点。经保存runner的只读`--stats`复核，新增消费0、未知0；累计仍为26次。按计划停止，不重试、不调整请求，也不使用旧scope剩余4槽。

原生时点源码身份为`ebd4d89356b32398a492d900ff9b604e7b03f072d5f24142300e19ba23bf2287`、401份源码文件；HEAD为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，工作区未提交改动均予保留。窗口在2026-10-22 17:45:49（Asia/Shanghai）独占创建，固定6次/7200秒；不得重置或在该scope重试。完整报告和恢复证据位于忽略目录`data/runtime/p1-tenki-placement-native-2026-10-22/`。

## 已完成且冻结的输入

- 六份旧账本消费9/8/1/4/2/2，合计26、未知0，哈希与原记录一致；366项保护文件中365项匹配。
- 唯一获准迁移是`target/debug/ygo-engine-worker.exe`从`a384b35aff160049b3381f15bfc35e17cf373a1ada54986b8c884bde09c78c7e`登记为`4f2b5a7c73914f07b0bce39ed01b7f74ed9c335dba329ef3a3bf1803a6db7680`。该文件当前来源仍未知；迁移不为旧二进制补签构建来源或重放资格。v2记录在`baseline-transition.json`，其哈希进入manifest输入集合及context。
- 本批隔离build记录绑定上述源码。CLI、worker、runner副本SHA256分别为`142fd2993a4425f060fa6dfd06fd6e96ec329c8a5827e41c229cbd76ba288fc5`、`0cdf7e8748c3ca6e68f942d005ae0078f1b19cfc5facf29e70994e91fff39c53`、`e7a71e508af12779129756b9f95e47562dde1ef8954fc17df7c4486ea70364bc`。普通`dist`、标准`target/debug` worker和active指针未切换。
- 第一次`prepare-only`在`data/runtime/banlist.json`缺失处退出。已核对active banlist id对应的`data/snapshots/banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783.json`，其SHA256为冻结案例要求的`a6344cd77c4db6dcfab02d03110954fa1c2717422f71da302970f427564506c9`；随后只在忽略目录生成同字节验证副本，没有修改快照或active指针。第二次`prepare-only`成功，明确报告新增原生调用0，并冻结stage 1请求及seal。
- manifest context为`773bafe50501dd0e093b7396d24bb2198a94503212a31d6407bdcfad8f7b1d37`。stage 1请求SHA256为`e6b111354986fc1e0237c7a001d0b7dc233af59e9653bfca6e0176a60767c53e`，stage input SHA256为`61277129f00905d5a96c007a0a568e3758ce4d8f691c2b7d3eecc87fb3b8adb3`。普通与赛事身份一致，执行角色为普通资产。
- 原生前检查：Python 251项（244通过、7跳过）；Rust格式检查、workspace全目标Clippy通过；workspace串行292通过/36忽略；examples 22通过。命令日志在同一忽略目录的`verification/`。

## 原生停止证据

唯一常规原生入口于窗口内调用一次，汇总`diagnostic=runner_failed`、`stages=[]`、无stage收据。`calls.jsonl`只有2条账本记录（header及`consumed=0`的起始checkpoint），大小674字节，SHA256为`0c274d01a40bb1f225409346b8d2f377fe84246f5bb367672ebcf25d74760767`。只读`--stats`返回`native_calls=0`、`consumed=0`、`completed=0`、`unknown=0`、`reserved=0`、`abandoned=0`、`limit=6`。六份旧账本和365项未迁移保护文件未变；迁移worker保护值仍为`4f2b…7680`。

原生摘要没有保存底层runner的具体错误文本，失败原因尚未定位。stage 1请求文件已冻结但没有执行收据。独立只读复核确认此状态未产生收费调用。证据记录为`verification/native-attempt.json`，summary为`research/summary.json`；不要把该次runner失败解释成opcode18、区域响应或worker行为的验真结果。

## 后续断点

本批到此暂停。下一步只能先离线定位stage 1 runner的未收费拒绝原因，并为诊断补齐可审计错误输出；不能调用普通runner模式、worker或doctor，也不能重新运行该六阶段请求。该固定窗口不可重置，旧scope余4槽继续封存。任何后续原生尝试都须在原因修复、重新测试/隔离构建后另行制定并授权新的scope与预算。

保留v2迁移、manifest、准备报告、账本、summary、失败前缀、身份、native artifacts、`banlist-source.json`及本断点。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均保持false；不切换部署、不提交或推送Git。
