# Ground Collapse opcode24离线准备：本批交付与续接断点

## 当前结果

本批完成FIELD_DISABLED解析、独立opcode24/HINT_ZONE/区域oracle、公开选区规则、合成来源链及固定来源准备报告。真实准备报告位于`data/runtime/p1-ground-collapse-preparation-offline-2026-10-27/preparation.json`，SHA256为`5354438945079d9df4f2867e272e2420d71605909c772f0a874b6c21b8319d74`，25,131字节；六项检查通过，`execution_ready=false`。新增原生、真实runner、worker、FFI调用均为0，没有创建scope、窗口或收费账本。

准备使用的Curry交付锚点为`75598ee09563b02f897d8109f3088e57aa0da134f3dbbf987f5215012acd7731`。经认证的既有账本消费为40、政策预留7、规划基数47；旧confirmation消费与全部历史实际累计仍为`null`。所有资格字段保持false。

文档前源码工具冻结身份为`c96a9e5ec6e6aef5a24cf218b11cc18140be01cdbd4fd4e95d59ab12deee8862`、602项；源码ZIP SHA256为`70cda05d86ac361172afdc209dc14d785e526d121dc3874c23039e3590a303fe`，文件清单SHA256为`fc23e6fba0205eda569147ba8e91979508dc044b6f0899033d835cd9b90a99fe`。对应冻结元数据位于`target/ground-collapse-preparation-tests/audit-source-freeze-cache-final-20261027/freeze-metadata.json`。

## 实现与验收

- Rust通用decoder对opcode56严格解析5字节`[56,u32 LE]`，输出`disabled_mask`，拒绝截断与尾部，不硬编码Ground Collapse的掩码。
- 独立Python oracle直接读取opcode24、HINT_ZONE和FIELD_DISABLED原始字节，验证区域位、菜单坐标、Choice与响应编码绑定。选择规则为唯一激活90502999；若出现opcode18，选择唯一`player0/location8/sequence0`；opcode24按序选择`player1/location4/sequence0`和`sequence1`。对应固定响应为`[1,4,0,1,4,1]`。
- 合成opcode24使用帧`[24,0,2,224,255,224,255]`、掩码`0xffe0ffe0`；规范无序组合45种、有序编码90种。合成HINT_ZONE为`[2,11,0,0,0,3,0,0,0,0,0]`，FIELD_DISABLED为`[56,0,0,3,0]`，选中掩码`0x00030000`。这些是合成或静态推导，不是原生结果；反序编码保持可区分，未判定为等价或非法。
- 固定输出此前独占创建一次。真实prepare命令退出0、耗时357.287秒；stdout为单一JSON，180字节，SHA256 `acfebec454437161277b74741ef5f192f651817f5bfa70f387a73b4339f86920`；stderr为空。文档前verify-only退出0、耗时313.189秒，`valid=true`，stdout 130字节、SHA256 `25574f811e30c8b3e295e4b0834eee463e3d1551a55b675dd6325c4b12e9edc1`；正式报告前后哈希相同。两次原始进程字节分别保存在`target/ground-collapse-preparation-tests/real-prepare-attempt-final/`和`verify-before-docs-final/`。
- Python完整套件显式枚举88个顶层测试文件：734 passed、9 skipped、200个子测试通过、0失败，用时1,695.86秒。逐项跳过原因和原始日志见`target/ground-collapse-preparation-tests/pytest-full-after-cache-tightening.log`及`test-exclusion-inventory.json`。Rust隔离验证：fmt、全目标Clippy通过；workspace 382 passed/37 ignored；examples 52 passed/1 ignored。Rust末次验证后未再改Rust源码。独立只读审阅未发现协议、来源或输入稳定性阻断。

本批真实准备的原始输出、报告、测试日志和合成材料均在正式忽略目录或`target/ground-collapse-preparation-tests/`。只读审阅确认固定来源和候选哈希没有因合成测试放宽。既有ACL受限临时目录保留，未调整权限或删除。

## 离线与原生资格边界

opcode24的实际原生提示、掩码、prompt ID、可达性、响应接受及后继消息序列均未知。FIELD_DISABLED56支持只认证通用帧解析；不能证明它在Ground Collapse线路中出现。Tenki opcode13与Curry opcode14的局部执行及重放只属于各自冻结案例，不代表完整动作覆盖。`execution_ready`、`native_reachability_verified`、`response_acceptance_verified`、`proof_ready`、`complete_action_coverage`、`global_optimality`和`native_probability_verified`均为false。发行依据仍为unknown。

## 后续续接

固定准备目录已存在；恢复时不得重跑prepare、覆盖报告、换名或把准备合同直接交给worker。先核验本交接指向的[最终交付记录](../../../target/ground-collapse-preparation-tests/final-release/delivery.json)、源码归档、文件清单、正式报告哈希及最后生成的体积/访问失败清单。文档定稿后的`--verify-only`只读结果及原始stdout/stderr/退出状态由delivery记录绑定。

下一步若要原生发现opcode24，必须另立新scope、请求预算和窗口；在首次候选资产扫描前保存窗口起点，冻结worker/build/identity/request/seal，并逐阶段收费。公开选区只能按上述坐标唯一匹配，不可因缺失或重复而改选。任何未知提示、掩码变化、额外消息、响应失配、资产漂移、到期或未知消费均停止，不重试、不续开旧窗口。

本批不切换部署或active资产，不提交或推送Git。任何未来原生预算不改变旧窗口封存状态。
