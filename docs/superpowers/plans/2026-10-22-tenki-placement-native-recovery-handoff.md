# 天玑区域18与opcode13验真：迁移恢复断点（2026-10-22）

## 当前状态

六阶段实现仍处于离线状态。旧保护文件的精确单文件迁移入口和有效映射已实现；本次新增的计数兼容修复也通过测试。原生实验未开始，新增消费0。新scope目录、窗口、manifest、具体请求和账本均未创建。不要覆盖或继续普通构建目录，也不要扫描候选资产。

文档变更前的源码身份为`674988ca4c168e44f86e037a91fcd621a759c7f58fe11e450787df71f782b776`，399份文件。HEAD仍为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，工作区修改保持未提交；最终文档后的源码身份尚未生成归档。

## 已验证事实

- 六份旧账本SHA与固定manifest匹配，消费分别为9、8、1、4、2、2，累计26、未知0。旧实验scope继续冻结，不使用其余4槽。
- 366项旧保护文件有365项匹配。唯一差异为`target/debug/ygo-engine-worker.exe`：旧保护值`a384b35aff160049b3381f15bfc35e17cf373a1ada54986b8c884bde09c78c7e`；本次计划仅允许记录该文件当前值为`be6aae6ec2d03ae3293f2954fb84be211483bd9c5b57e4ac3b546b7239db9eba`；实际现场值是`4f2b5a7c73914f07b0bce39ed01b7f74ed9c335dba329ef3a3bf1803a6db7680`。
- 只读检索了工作区、runtime worker副本、相邻checkout、配置的ProjectIgnis安装根目录及保留ZIP，没有找到SHA为`be6aae…`的可验证文件。目标worker与`target/debug/deps/ygo_engine_worker.exe`当前同为`4f2b…`。Cargo标准target指纹显示普通worker及test harness约在2026-10-22 06:13 UTC生成；未找到记录能确定触发命令或该二进制来源。隔离目录`target/tenki-placement-offline`的worker为其他哈希，不能替代迁移目标。
- 上批恢复验收的`remaining_slots_sealed`是整数4。代码先前错误使用`is True`拒绝该值；现已添加严格整数计数检查，布尔`true`不会被当作4。该修复没有改写任何历史报告。
- 原生时点runner和worker仍按既有哈希保存在上一批目录；其先前四项`--verify-recorded`/`--stats`零调用结果只引用原验收。本次没有再调用旧runner。
- 独立只读审阅确认普通CLI路径、迁移报告重算和逐阶段保护回调都使用同一有效映射，无法绕过当前哈希拒绝。

## 本次检查

- `py -m unittest tests.test_native_tenki_placement`：19项通过。
- `py -m unittest discover -s tests`：233项，226通过、7跳过，用时99.525秒。跳过项为明确的opt-in冻结资产、引擎或本机报告用例。
- `cargo fmt --all -- --check`、Python `compileall`：通过。
- Rust代码未因本次恢复修改；使用隔离target的Clippy、workspace串行292通过/36忽略及examples 22通过，引用上一条同批运行记录。
- 迁移CLI在输出写入前返回`historical_protected_input_changed`。没有运行worker、doctor、收费runner，未发出新请求，也没有扫描候选CDB/资产。
- 固定新实验根目录`data/runtime/p1-tenki-placement-native-2026-10-22`仍不存在。账本、pause/recovery验收和旧保护文件没有被本次代码改写。

## 续接门禁

当前哈希`4f2b…`不属于批准的单文件迁移。不要把它直接替换进保护清单、转换成成功迁移报告或复制其他构建产物覆盖它。继续前必须满足以下一种经明确确认的路径：

1. 找到并验证计划允许的`be6aae…`原始文件与其可信来源，再确认标准target保护路径确实回到许可状态；或
2. 由用户/维护者另行批准新的、范围明确的基线迁移方案，记录其来源状态、实际哈希及其余365项不变，并相应更新测试和版本化合同。

恢复后先运行迁移审计和保存原runner的零调用收据检查，再创建固定新scope；在首次候选资产扫描之前独占写入窗口起点。重新采集普通/赛事身份、冻结stage1请求并执行prepare-only。其后才可按原计划顺序执行最多6阶段、最多6次、2小时窗口：区域18固定区域0、opcode13 false执行/重放、true执行/重放。任一门禁失败立即停止，不重试、不续窗，不使用旧4槽。

证明、完整动作、全局最优和原生概率资格保持false；不切换部署、不提交或推送Git。
