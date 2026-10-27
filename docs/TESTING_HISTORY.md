# 本机验证记录

## 2026-10-27 项目环境自检与清理

在现有未提交工作区上复核，HEAD为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，未提交或切换部署。清理前，Ground最近交付的603个归档成员和15个带路径/大小/哈希引用均匹配，509个非Markdown成员与当时工作区一致；本次修改后其中只有`Cargo.lock`、两个crate的`Cargo.toml`和`pyproject.toml`四项变化。归档和原报告没有改写。

- 普通发布包和赛事开发配置各运行一次`engine doctor`：均退出0，`ready`、`abi_ok`、`assets_ok`为true，`issues=[]`、`smoke_ok=null`。这是两次worker ABI探针，单独属于本次环境自检，不是决斗smoke、规则认证或既有研究scope消费。普通CLI/worker哈希与其包内清单一致；包仍为2026-10-19构建。
- `cargo fmt --all -- --check`、workspace全目标offline/locked Clippy `-D warnings`通过。隔离target的`cargo test --workspace --offline --locked -- --test-threads=1`为330 passed、36 ignored；另执行adapter examples为52 passed、1 ignored。日志在`target/workspace-audit-2026-10-27-codex/`。测试运行与本机发布worker隔离；忽略项未因此获得真实资产验收。
- Python仅针对pytest缓存配置运行`tests/test_ground_collapse_protocol.py`，8项通过；预建`target/pytest-cache`后无缓存警告。完整Python套件未在本次重跑；下方734 passed/9 skipped属于Ground批次。
- 经提升权限逐个检查路径与内容后，非递归移除222个空pytest缓存目录、四个空`.v5-package-test-*`及三个空`tests/tmp*`目录；清单和首次空值判断导致零删除的记录也保存在上述target目录。未修改ACL，清理后`git status --porcelain=v1 --untracked-files=all`退出0且无访问警告。Ground归档中61个非空合成测试文件保留原位。
- 删除两个未被各自crate直接使用的`toml`/`sha2`依赖声明，offline更新的锁文件只移除相应直接依赖；其他crate仍使用它们。`.gitignore`是Ground固定工具包成员，本次未改。
- 文档检查验证本机相对文件目标存在；指向忽略的`target/`和`data/runtime/`的证据在干净checkout中仍需单独提供。历史原生预算、规则资格及未知累计消费没有由本次检查增加。

本次未运行新的收费研究实验、正式v6、16+32手评估或最新源码干净双资产部署；环境路径与保留范围见[环境审计](ENVIRONMENT_AUDIT.md)。

## 2026-10-27 项目再规划：仅文档静态交叉核对

本记录是后续文档重整的只读核对，不是下面Ground Collapse批次的实跑复验。开始编辑时，最新最终源码清单的603项与工作区逐项一致；完成文档修订后，完整工作区已变化，旧清单的完整源码身份不再描述现在的工作区。HEAD为 `8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，既有未提交/未跟踪改动保留；HEAD不等于完整工作区身份。

从仓库根目录运行以下纯Python标准库检查，结果为 `archive=603, nonmarkdown=509, delivery_references=15: OK`，退出0。它复核旧归档成员及其清单、当前工作区范围内509个非Markdown文件，以及交付记录中15个带路径、大小和SHA256的引用；**不证明清单之外所有忽略文件或不可读路径均未改变**。

```powershell
@'
import hashlib,json,pathlib,zipfile
h=lambda b: hashlib.sha256(b).hexdigest()
d=json.loads(pathlib.Path('target/ground-collapse-preparation-tests/final-release/delivery.json').read_text(encoding='utf-8'))
s=d['final_documentation_source']; files=json.loads(pathlib.Path(s['file_list']['path']).read_text(encoding='utf-8'))['files']
nonmd={p:v for p,v in files.items() if not p.lower().endswith('.md')}
assert all(pathlib.Path(p).is_file() and h(pathlib.Path(p).read_bytes())==v for p,v in nonmd.items())
with zipfile.ZipFile(s['archive']['path']) as z:
 assert len(z.namelist())==len(files)==603 and set(z.namelist())==set(files)
 assert all(h(z.read(p))==v for p,v in files.items())
refs=[]
def walk(x):
 if isinstance(x,dict):
  if {'path','sha256','bytes'} <= x.keys(): refs.append(x)
  for v in x.values(): walk(v)
 elif isinstance(x,list):
  for v in x: walk(v)
walk(d)
assert len(refs)==15 and all(pathlib.Path(r['path']).is_file() and pathlib.Path(r['path']).stat().st_size==r['bytes'] and h(pathlib.Path(r['path']).read_bytes())==r['sha256'] for r in refs)
print(f'archive={len(files)}, nonmarkdown={len(nonmd)}, delivery_references={len(refs)}: OK')
'@ | py -
```

其他核对：普通dist的CLI及worker与其发布哈希清单一致，普通/赛事配置引用路径存在；未由此推定可执行或已更新。以本轮受修改文档的相对Markdown路径作静态存在性检查、比较旧归档INDEX与新INDEX/HISTORY目标，并将愿景16个需求编号与差距评估和原产品演进计划比对：未发现缺失链接、旧导航目标遗漏或编号遗漏。检查只覆盖文件路径与编号存在性，语义另经独立只读审阅。`git diff --check`退出0，Git提示既有CRLF转换警告；`git status --porcelain=v1`的229行权限警告来自既有不可读路径，未调整ACL或删除证据。新增/修改限于Markdown，旧的工作区改动保留。

独立只读审阅重点核对40/7/47与未知消费、历史来源及合同、Ground资格、P4开放门禁、双轨依赖、16项需求和旧导航；发现的doctor权限泛化、旧runner来源泛化、递归测试发现和历史记录顶部链接问题已修正。未执行doctor、原生runner/worker/FFI、历史业务prepare或verify、构建、全套测试、部署、资产切换或Git提交；旧测试数量与耗时仍只属于其原记录。

## 2026-10-27 Ground Collapse opcode24离线协议与公开选区准备：离线准备及verify通过

本批仅完成离线协议支持与候选准备，新增原生/runner/worker/FFI调用均为0。生产decoder的FIELD_DISABLED56帧严格为5字节`[56,u32 LE]`，不写入Ground Collapse特定值。独立oracle解析opcode24、HINT_ZONE和FIELD_DISABLED原始字节，验证字段、区域位、菜单坐标、Choice和响应编码之间的绑定。静态/合成菜单为45个无序区域对、90种有序编码；这些不是原生提示或引擎响应接受证据。固定公开规则为唯一激活90502999；若出现opcode18，唯一选择`player0/location8/sequence0`；opcode24按`player1/location4/sequence0`再`sequence1`选择，响应`[1,4,0,1,4,1]`。任何缺失、重复或不可用位置均停止，实际mask、prompt ID、可达性、响应接受、反序等价和后续消息保持未知。

缓存竞态修复先由测试复现：账本二次核验在输入检查后短暂替换再恢复请求文件时，旧裸路径读取会拒绝/失配；修复后只保留七个stage request的原始字节供账本校验，其他输入仍全量路径/哈希检查但不留在内存。聚焦组44 passed、19个子测试通过；独立复审确认哈希与最终稳定性检查保持有效。

Python全套显式枚举88个顶层文件，`734 passed, 9 skipped, 200 subtests passed`，0失败，用时1,695.86秒。日志及清单为[`pytest-full-after-cache-tightening.log`](../target/ground-collapse-preparation-tests/pytest-full-after-cache-tightening.log)和[`python-test-files-review-final.txt`](../target/ground-collapse-preparation-tests/python-test-files-review-final.txt)。9项跳过逐项为：`test_curry_consumption_reservation.py:555`、`test_curry_optional_source_path.py:39`（Windows目录符号链接能力不足）；`test_goal_schemas.py:41`（opt-in v3 reports）；`test_recovery_schemas.py:24`（opt-in v4 report）；`test_runtime_build.py:9`（未提供本机引擎资产）；`test_schemas.py:77`（opt-in本机快照/报告）；`test_schemas.py:52`（opt-in实际v2报告）；`test_strategy_schemas.py:22`（opt-in完整策略报告）；`test_tournament_gate.py:95`（未提供独立2026赛事配置）。完整结构化排除清单见[`test-exclusion-inventory.json`](../target/ground-collapse-preparation-tests/test-exclusion-inventory.json)。

本批Rust修改的隔离验证：`cargo fmt --all -- --check`通过；workspace all-targets offline/locked Clippy以`-D warnings`通过；串行workspace 382 passed、37 ignored；examples 52 passed、1 ignored。唯一examples忽略项要求固定历史genesis证据；workspace 37项及逐项忽略原因列在同一[排除清单](../target/ground-collapse-preparation-tests/test-exclusion-inventory.json)，原始日志分别为[`workspace-tests-serial.log`](../target/ground-collapse-preparation-tests/workspace-tests-serial.log)和[`adapter-examples-tests.log`](../target/ground-collapse-preparation-tests/adapter-examples-tests.log)。此后仅改Python缓存与文档，Rust源码未变。

真实固定来源准备命令退出0，耗时357.287秒，保存[`preparation.json`](../data/runtime/p1-ground-collapse-preparation-offline-2026-10-27/preparation.json)（SHA256 `5354438945079d9df4f2867e272e2420d71605909c772f0a874b6c21b8319d74`，25,131字节）。六项检查通过：最新Curry delivery与双时点源码/账本来源、历史保护材料、冻结候选、CDB/禁限/脚本/核心来源及输入稳定性。认证历史消费40、政策预留7、规划47；旧confirmation和全部历史实际总消费仍`null`。report `execution_ready=false`，所有资格标记为false。原始stdout 180字节SHA256 `acfebec454437161277b74741ef5f192f651817f5bfa70f387a73b4339f86920`；stderr 0字节，退出0。文档前verify-only耗时313.189秒，退出0、`valid=true`、native/runner/worker/FFI=0，stdout 130字节SHA256 `25574f811e30c8b3e295e4b0834eee463e3d1551a55b675dd6325c4b12e9edc1`；报告哈希前后均不变。进程原始字节及状态在`target/ground-collapse-preparation-tests/real-prepare-attempt-final/`和`verify-before-docs-final/`。

文档前源码身份为`c96a9e5ec6e6aef5a24cf218b11cc18140be01cdbd4fd4e95d59ab12deee8862`（602项），归档ZIP SHA256 `70cda05d86ac361172afdc209dc14d785e526d121dc3874c23039e3590a303fe`，list SHA256 `fc23e6fba0205eda569147ba8e91979508dc044b6f0899033d835cd9b90a99fe`。这是代码冻结，不是本批文档定稿后的最终身份；最终身份、源码归档、访问失败清单和交付记录见本批handoff及外部delivery材料。ACL受限临时目录保留，未调整权限或删除。下一批须另建scope/预算；本准备报告不得直接启动原生实验。

## 历史状态（2026-10-27）：绑定V3恢复证据的Curry七阶段再验真：七阶段与双分支重放通过

固定scope `curry-option-revalidation-v1` 完成7次执行、消费7、完成7、unknown 0；使用V3恢复来源、22角色manifest及确定性风险预留ID。窗口起点为2026-10-27 00:24:49 +08:00。总summary为`data/runtime/p1-curry-option-revalidation-native-2026-10-26/research/summary.json`（SHA256 `fcc3d1aebe8b97f6c954a56593c86461afd7b71613669e47c6c8e1ba0e0d9098`）。

阶段收据的冻结校验均通过：1识别唯一58074572命令5激活；2停在opcode18；3使用唯一`player0/location8/sequence0`选择及`[0,8,0]`响应到opcode14；4选项0字节`[0,0,0,0]`，RECOVER player0回复200且LP `[8200,8000]`；5重放阶段4原请求且匹配；6选项1字节`[1,0,0,0]`，RECOVER player1回复200且LP `[8000,8200]`；7重放阶段6原请求且匹配。两项重放均为`independent_replay_matches=true`。各阶段决策消费、响应oracle、资产前后扫描及预算前缀通过。

normal外层进程退出0，耗时954.67秒、timeout为窗口剩余6647.104秒；单一stdout 3,559字节、SHA256 `3b64fad1a14845c92e8a422fa509d186fa4e74a0238d9d92d6362bf2b3d6e4fd`，stderr为空。原始进程侧车位于`target/curry-option-revalidation-tests/normal-execution-640ec24fca2d4262953d742672b9d0e0/`。prepare-only stdout 790字节、SHA256 `6c1ad68cddc9520227a81df15ce2bf9d03b0a52ec90bfe26fe210954276da6bf`，native_calls 0；侧车在同测试根的`prepare-only-4c1f6eecc3e242788c458aea737868fc/`。

只读verify-only耗时80.499秒、退出0、`valid=true`、`native_calls=0`，账本7/7/unknown0；raw stdout 4,177字节、SHA256 `c7845e0f303d0c21efaa213a1b94c8407e216d4883d750f85cd7ab8cb8ea7c97`，stderr为空。证据在`target/curry-option-revalidation-checks/0efeaf7cfe5041eaa809120c356f70fc/`。verify后的V3固定来源与89项保护映射核验通过；保护映射SHA256 `e0014e127e6261db99128eef1f1ca26e00d4a6731155a0ab36611ae2ed7d791f`。原native build record、归档和产物均保留；当前完整源码归档与最终构建记录指向[最终交付](../data/runtime/p1-curry-option-revalidation-native-2026-10-26/final-build/delivery-final.json)。

Python聚焦组66 passed、37 subtests passed（8.85秒）；公共CLI合成E2E 1 passed（100.07秒）。完整Python套件显式枚举84个顶层文件，`685 passed, 9 skipped, 181 subtests passed`，0 failed，用时1,640.66秒。清单和`-ra`日志为`target/curry-option-revalidation-tests/python-test-files-92847bcb-3305-45f8-81a5-e45e87271db5.txt`及`pytest-full-c61a53dc-9e22-4462-ad53-f573b192d71b.log`。9项跳过：Windows目录符号链接能力限制（2）；v3报告opt-in、v4报告opt-in、本地引擎资产未提供、本地快照/报告opt-in、真实v2报告opt-in、完整策略报告opt-in、独立2026赛事资产配置未提供（各1）。

Rust验证使用隔离Cargo target及offline/locked：`cargo fmt --all -- --check`通过；`cargo clippy --workspace --all-targets --offline --locked --target-dir target/curry-option-revalidation-build/cargo-target -- -D warnings`通过；串行workspace合计329 passed、36 ignored（87个测试harness）；examples合计52 passed、1 ignored。忽略原因逐项见`cargo-workspace-2282a7b4-f750-4473-b1fa-d649c968f3d9.log`及`cargo-examples-final-8e1826d0-aa7d-47d0-b51c-89a33c8c67c4.log`；fmt和Clippy标准输出/错误日志为`cargo-fmt-final*.log`与`cargo-clippy-final*.log`。examples唯一忽略项需要固定历史genesis证据，workspace忽略项为引擎资产/原生收费或明确opt-in。

独立只读审阅确认阶段顺序、实际输入/输出、LP、重放、来源、摘要和verify一致，无阻断发现；一项P3指出合成Rust runner fixture使用旧的ignored临时目录`target/curry-option-validation-tests/tmp/runner-e2e-*`，不影响验证，仅使用合成文件。真实资产opt-in、doctor、48手评估、其他提示实验未运行。部署和active资产未变；四项资格仍为false。完整交接见[本批交接](superpowers/plans/2026-10-27-curry-option-revalidation-handoff.md)。

## 2026-10-26 Curry V3真实来源角色适配与零runner恢复：恢复和只读verify通过

修复V3预留来源角色绑定：固定集合只接受已认证的`v3_source_workspace_identity`，不接受V2失败报告中的`v3_source_confirmation_summary`；V1六成员、V2七成员工具包和原报告合同保持不变，V3使用八成员工具包。补齐失败报告的有序六blob后缀约束及发布重建时的工作区身份绑定；发布签名包含`tool`，verify-only仍允许文档更新后的工作区变化。独立只读审阅确认上述绑定；随后针对显式`allow_saved_workspace_identity_change=False`和工具身份签名的聚焦测试为2 passed（1.68秒）。

聚焦合成回归通过：恢复V3模块及V5公开兼容路径17 passed（209.30秒），V1/V2恢复与V3/V4/V5公共审计回归5 passed（367.45秒）。显式枚举81个顶层Python文件运行完整套件：671 passed、9 skipped、0 failed，用时1,461.55秒；`-ra`跳过明细在`target/curry-ledger-handoff-recovery-v3-tests/python-full-suite-v3-final2.log`，测试文件清单`pytest-files-v3-final.txt`。跳过项为两项Windows目录符号链接能力限制，以及v3/v4 schema、本机引擎资产、本地快照/报告、真实v2报告、完整策略报告、独立2026赛事配置的opt-in或缺少材料。Rust/Cargo 151项与V2最终源码归档完全一致：140个Rust源文件和11个Cargo清单/锁文件无增删改。本批未改Rust/Cargo，引用既有fmt、全目标Clippy及workspace 380 passed/37 ignored记录，未重新构建。

唯一一次真实V3恢复命令为`py -m ygo_eval.research recover-curry-ledger-handoff --report-version 3 --baseline-dir data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26 --output data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26/recovery-report.json`，纯Python退出0、耗时35.541927秒。V2失败报告SHA256 `7496f981438bdca15f768eb38c6402cf15cc8ff88401d661fae7ee554dc476d6`、V2 delivery SHA256 `c3bf0aa851b5cd6b39045ee5b8897d3c53f934de4ab31a5ec0cf1dc93fb7ccfe`及V5 delivery SHA256 `3c689f9ae6860da3b42a0ea4f6f0e5e3b100fdc2c548f91f2e288268bd071278`均匹配固定锚点。V3报告SHA256 `69d2af394169d5773394e775718840ef9a3df22eac12167d2e7ba3c79484c468`（51,891字节），Python合同和保存工具包schema通过；9项检查全部通过，输入角色恰为187。

V2来源静态读取确认其归档七成员完整、报告中实际100角色集合含`v3_source_workspace_identity`而不含`v3_source_confirmation_summary`；没有执行旧归档代码，也未要求不存在的585项完整审计工作区归档。V1/V2前次失败来源、V5交付与归档、历史来源、冻结输入和父链、保存进程证据、scope账本语义、稳定性及发布复验均通过。原stage 2 input/prepared/request/seal和原账本保持固定哈希；stage 2收据仍缺失。

报告重新认证原scope为消费1、完成1、未知0、limit7；既有历史32、含scope认证33、风险预留7、规划40。旧confirmation实际消费和全部历史实际累计为`null`。V3工具身份`56f967190b3333f8bd0d5b323577149c577e1c34bbb6b158ba7c013e33a8cc31`绑定工作区身份`b84db687415eb990692e19c4385443e08ab478f9b5160d2cc11a9b44f1899954`（588项）。恢复原始stdout 51,891字节、SHA256 `6c1da8f3207603cee38202323c37e77ff1fdc893b7bad40cc296956e21645cf7`，stderr为空，CLI退出记录和原始字节保存在`target/curry-ledger-handoff-recovery-v3-tests/real-recovery-attempt/`。

首次零调用verify通过，验证结果`valid=true`、187项输入；V3报告SHA256前后相同，输出树未变化，工作区核验前后稳定，`native_calls=0`、`runner_process_calls=0`。文档定稿后的最终verify、完整源码归档、最终文件清单及交付记录列于[`delivery-final.json`](../data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26/final-build/delivery-final.json)。本批新增原生/runner/worker/FFI均0；没有构建、doctor、live asset scan或收费账本写入。stage 2仍为历史失败且无收据，四项资格持续false。交接见[本批断点](superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-v3-handoff.md)。

## 2026-10-26 Curry V2精确来源恢复与零runner验收：离线通过，真实恢复在输入角色门禁失败

V2固定来源profile、V1失败源六角色、真实V5来源链及181角色合成成功路径完成。聚焦回归33 passed（144.74秒）；独立审阅通过。完整Python测试显式枚举`tests/`顶层80个`test_*.py`文件：655 passed、9 skipped、166 subtests passed，耗时1,311.87秒。命令由`target/curry-ledger-handoff-recovery-v2-tests/top-level-python-test-files.txt`中80项明确传入，使用`py -B -m pytest -p no:cacheprovider -q -ra`；完整日志为`target/curry-ledger-handoff-recovery-v2-tests/pytest-full.log`。9项跳过明细：Windows目录符号链接限制2项、v3/v4报告opt-in、本机引擎资产未提供、本地快照/报告opt-in、真实v2报告opt-in、完整策略报告opt-in、独立2026赛事资产配置未提供。Rust/Cargo未改动，151项源码与已认证清单保持一致，引用既有fmt、全目标Clippy及workspace 380 passed/37 ignored结果。

真实纯Python恢复命令按固定V2目录执行一次，退出码2；没有runner/worker/FFI调用。失败报告`data/runtime/p1-curry-ledger-handoff-recovery-v2-offline-2026-10-26/recovery-report.json` SHA256 `7496f981438bdca15f768eb38c6402cf15cc8ff88401d661fae7ee554dc476d6`，47,789字节，通过保存的V2工具包schema和运行时校验。`failure_checkpoint=scope_ledger_semantics`，`diagnostic=recovery_success_input_set_incomplete`。报告有181个输入角色；保存的V3来源角色实际为`v3_source_workspace_identity`，而固定期望集要求`v3_source_confirmation_summary`，所以恢复报告未认证原scope统计，全部派生会计值保持null。报告的V1前次失败绑定、V5交付链、历史来源、冻结输入/父链和已存进程证据门禁均通过；input stability未运行。

恢复CLI原始stdout为77字节、SHA256 `552d1bcfa2ba3ae2837fae98bc70105acb8c5ff3f79622bf92883dbfca54ba27`；stderr 0字节、SHA256为标准空流哈希。report/工具包及外部原始输出的哈希保存在本批交接。失败后按一次尝试门禁不重试、不换目录、不执行verify-only。恢复前后锚点检查确认V5/V1材料、原scope ledger哈希、stage 2 input/prepared哈希不变，stage 2 receipt与V5正式audit report仍缺失。已认证历史子集32、预留7、规划39仅沿用此前证据；旧confirmation实际消费与全部历史实际累计继续为null。详见[本批恢复交接](superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-v2-handoff.md)。

## 历史验证（2026-10-26）：Curry V5已存证据恢复与报告发布诊断

报告发布错误路径修复、七行scope账本及六个blob的纯Python认证器、完整公共CLI合成路径通过。聚焦组48 passed（70.85秒）；独立审阅通过，最后复核写后来源重建失败会记录`written_unverified`与实际报告SHA，且不改写报告。

完整Python套件显式枚举79个顶层`tests/test_*.py`文件，命令为`py -B -m pytest -p no:cacheprovider -q -ra <top-level-tests-final.txt中的79项>`：651 passed、9 skipped、166 subtests passed，1,276.76秒。清单`target/curry-ledger-handoff-recovery-tests/top-level-tests-final.txt`，最终日志`pytest-full-final2.log`。9项跳过明细由`-ra`记录：两个Windows目录符号链接能力限制；v3/v4报告、实际v2报告、完整策略报告、快照/本地报告为opt-in；缺本机引擎资产；缺独立2026赛事配置。先前被审阅打断的全套运行不是最终验收。Rust/Cargo本批未修改；引用既有fmt、全目标Clippy、workspace 380 passed/37 ignored验证。真实资产opt-in、doctor及48手评估未运行。

审计时工具源码工作区身份`d2307e164d2a949841f79a90715e12108b4c17b24be1275b37ea6a4700f4ddcf`（582项），工具身份`9b29faec4ac18ba8cdb718a7cba5a5efe637759a98f027044954baf5f2a02078`。工具源ZIP SHA256 `a1c04170b571eef44c6379036ea0824c02cdd6c776488729c0aa165a8ba4bebb`、清单SHA256 `f078d9d3fc781a9b3577873f5bf67b0bfbd493596ead1a9b5fa5a22497491f1b`；冻结包与工具归档均留在恢复目录及`target/curry-ledger-handoff-recovery-tests/audit-time-tool-freeze/`。

真实命令只执行一次：`py -B -m ygo_eval.research recover-curry-ledger-handoff --baseline-dir data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26 --output data/runtime/p1-curry-ledger-handoff-recovery-offline-2026-10-26/recovery-report.json`，退出码2。PowerShell侧车碰撞检查语句发生语法错误后shell继续执行；该事实不作为恢复报告诊断的原因。报告SHA256 `bf85a81f7d6a204e4a960b2ffb8449e2f1a17d857ca5fcf7e5e2303f5285270d`（3,891字节），Python合同和JSON Schema验证通过；状态`failed`，首个检查点`v5_delivery_and_archives`，诊断`recovery_v5_source_delta_invalid`，余下检查为`not_run`、输入行为空。native_calls=0、runner_process_calls=0。失败后不运行verify-only、不重试、不换目录。

失败后只读保护复核：V5 delivery仍为固定锚点，正式V5报告仍缺失；原scope ledger哈希与冻结值相同，stage 2 input/prepared哈希相同且stage 2 receipt仍缺失。因恢复首门禁未通过，恢复报告中的原scope和派生会计字段保持null；不发布33/40。既有认证子集32、预留7、规划39仅沿用历史证据；旧confirmation实际消费与全部历史实际累计仍为null。完整恢复断点和未认证边界见[本批恢复交接](superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-handoff.md)。

## 2026-10-26 Curry V5干净交付与单次零调用验收：runner只读检查通过，正式报告未发布

V5版本配置、V4真实来源适配、164角色合同、四项离线打包布局及公共CLI合成路径已完成。独立只读审阅未发现材料绑定或兼容阻断。Python完整总检显式传入77个顶层测试文件：637 passed、9 skipped、166个subtests passed，1,146.60秒；命令为`py -3 -m pytest -q -ra -p no:cacheprovider --basetemp target/curry-ledger-handoff-v5-tests/pytest-all-basetemp <top-level-test-files.txt中的77项>`。文件清单`target/curry-ledger-handoff-v5-tests/top-level-test-files.txt`，日志`pytest-all.log`，SHA256 `217454fe4889674463afb3b8eb1039d3e9c70c63e30a4896b49f621e4f783239`。9项跳过：`test_curry_consumption_reservation.py`与`test_curry_optional_source_path.py`的Windows目录符号链接不可用；`test_goal_schemas.py` v3报告opt-in；`test_recovery_schemas.py` v4报告opt-in；`test_runtime_build.py`缺本机引擎资产；`test_schemas.py`快照/真实v2报告opt-in（两项）；`test_strategy_schemas.py`完整策略报告opt-in；`test_tournament_gate.py`缺独立2026赛事配置。聚焦V5/打包/兼容组82 passed；公共CLI完整合成E2E 1 passed、72.83秒。Rust/Cargo的151项源码选集与V4最终清单变化0，本批未改Rust/Cargo，引用已完成的fmt、Clippy与workspace 380 passed/37 ignored记录。

固定V5包`data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26/`经共享布局校验恰有四项：runner、build-record、source ZIP、file list。源码身份`c37902c3e949fe6759df7ec0a6c30a54fa08dc3099cd638d5cb5833bbab5515f`、576项；runner SHA256 `2ef1a214fa16e9f4a3ba666ec614165a016eadc739a4eadcdc2c9e4cdd0338af`；build-record文件SHA256 `b6f1e120e6eb3057f421f8747992865e387767e55f7af7063f09d6cd3a292951`、身份`e67bd1a7d18d69777e7af29b425dfc84dc38a37fc594433ad7be17b87dae81e5`。源码ZIP和清单SHA256分别为`ce194380f6d2bb6c587e96009382cac6d9ed03f24af4fe660873da4b5d3480fa`和`c776edf40bcab67da85e011770d9c3ffdb27806c9aca8f72ed39ccc49df512f6`。

对冻结stage 2输入执行的唯一V5真实审计命令退出2，CLI输出`audit-curry-ledger-handoff refused: fixed source, runner, or output check failed`；没有`audit-report.json`，内部检查点因异常被CLI隐藏而未认证。runner本身已启动一次，退出0；其JSON为`saved_input_audit_passed=true`、父收据和请求派生有效、stage 2收据缺失、`native_calls=0`，ledger为消费1/完成1/未知0/额度7。stderr含4阶段共8条trace，其中只读资产扫描耗时149.918秒。原始元数据、stdout、stderr均先独占保存至`process-diagnostics/`，哈希列于[V5断点](superpowers/plans/2026-10-26-curry-ledger-handoff-v5-handoff.md)。命令观察记录在`target/curry-ledger-handoff-v5-tests/real-audit-attempt-observation.json`。不重跑CLI，不补造成功或失败schema报告；V5整体审计结论为未完成。

原scope账本哈希仍为`7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`，stage 2 receipt仍缺失。历史认证子集32、政策预留7、规划基数39保留此前证据口径；旧confirmation实际消费及全部历史实际累计仍为null。新增原生调用0；未启动worker/FFI/doctor、未创建新scope/窗口/收费账本。四项资格保持false。文档后归档及最终状态索引见`data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26/final-build/delivery.json`。后续须先做报告保存错误路径离线修复，再以新版本/输出根制定恢复方案；本V5固定根不可重试。

## 2026-10-26 Curry V4精确stdout合同与单次零调用验收：真实只读审计在来源根门禁失败

V4在共享旧scope读取路径中加入私有`verification-accounting-v1` stdout合同，仅由V4配置显式启用；validation、confirmation及旧三字段读取保持原语义。合成黄金对象独立手写14个字段，公共CLI成功来源树验证V4字段、真实预留绑定、账本/blob及stage 2派生，且保存时重新核验使用V4来源根。V3/V2/V1兼容测试保留。独立只读审阅确认没有生产CLI任意合同/profile参数，也没有绕过来源、账本或报告验证。

Python全套显式枚举`tests/`下73个顶层测试文件，`614 passed, 9 skipped, 0 failed`，另有166个subtests通过，用时1,141.41秒；命令使用`pytest -q -ra -p no:cacheprovider`。全量日志为`target/curry-ledger-handoff-v4-tests/pytest-full.log`，文件清单为`top-level-tests.txt`。9项跳过逐项记录于日志：`test_curry_consumption_reservation.py`和`test_curry_optional_source_path.py`因Windows目录符号链接不可用；`test_goal_schemas.py`、`test_recovery_schemas.py`、`test_schemas.py`、`test_strategy_schemas.py`对应报告/快照opt-in；`test_runtime_build.py`缺本机引擎资产；`test_tournament_gate.py`缺独立2026资产配置。V1–V4 handoff兼容聚焦集115通过、0失败，用时288.70秒，日志`target/curry-ledger-handoff-v4-tests/compatibility-rerun.log`。

Rust/Cargo集合159项与V3最终认证清单一致，其中151项为Rust/Cargo源码、8项为生成证据；本批无Rust/Cargo改动，未重复运行Cargo总检。引用已记录的fmt、全目标Clippy及workspace `380 passed, 37 ignored`结果。真实资产opt-in、doctor、worker、FFI、真实normal和48手评估均未运行。

V4审计时源码身份`a6fe4f17ffa0b3a030681d9c78b6e70c39263a45e89a18466e80cb62c72c7ae7`（568项）；源码归档SHA256 `bc73f2d8216c9553435844ed15f6b3845b60d898de57df9508fe8215abd55edb`，文件清单SHA256 `bad195d2875c7eb4a13bce054c18a83393e068308ba037de6cc291763394b1d3`。构建记录位于`data/runtime/p1-curry-ledger-handoff-v4-offline-2026-10-26/build-record.json`，隔离runner SHA256 `e92ff677fb10045acef6222c7ffac1ca73959b50502aa54b3cbd937959ec3853`；它仅被构建，未执行。

按固定命令运行的唯一一次真实V4审计，报告SHA256 `02f69485390c98cec677da83d3e9df3df70ffb9f238d38d3e8acf861968bad05`、5,522字节，通过V4运行时合同及`curry-ledger-handoff-audit-v4.schema.json`。报告`status=failed`、`failure_checkpoint=previous_v3_failed_source`、`diagnostic=curry_handoff_build_root_contents_invalid`、`native_calls=0`、`runner.process_attempted=false`。runner未启动，stage 2 saved-input没有调用；最早门禁拒绝固定V4根目录中计划外的`build-target/`和`build-command.json`，其余检查为`not_run`。报告保留原字节，不在固定V4目录整理后重试或覆盖。

原scope ledger固定哈希为`7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`；V4失败报告的ledger稳定性字段为`not_checked`。失败后另行进行的独立只读哈希保护检查与固定值相同；本批没有打开或修改账本。Stage 2 receipt仍缺失。已有认证子集32次、政策预留7、规划基数39；本批新增原生调用为0，旧confirmation实际消费、全部历史实际累计仍为`null`。固定input/prepared哈希分别为`b144701eeceafd8c8d7e827c7e6823213e401614f46488a9e3564c2735f604b8`和`7f94f982f89ca1c2b720f32250f8e4f9451ec0eb99ba5a4afcec7dd7fc23c5ee`，但本批未启动runner对其执行只读验收。四项资格仍为false。文档后源码归档、文件清单、交付及体积记录见V4目录的`final-build/`；权威文档后交付记录为`final-build/delivery-final.json`，不得将其与V4审计时源码或runner资格混用。

## 2026-10-26 Curry V3来源角色修复与单次零调用验收：真实只读审计在stage 1父收据检查失败

V3固定来源角色、归档和修复状态核验、完整来源树的合成回归及Python/schema合同已实现。独立只读审阅通过。Python全套显式枚举`tests/`下71个顶层文件，共608项：599通过、9跳过、0失败，用时1,022.86秒；文件清单见`target/curry-ledger-handoff-v3-tests/full-python-20261025T185658Z/test-files.txt`，完整`-ra`日志见同目录`pytest.log`。另在最后增加V3失败稳定性正例及V2字段兼容断言后，重跑V3公共E2E和合同共48通过、0失败、83.01秒。9项跳过逐项为：`test_curry_consumption_reservation.py`目录符号链接创建不可用、`test_curry_optional_source_path.py`目录符号链接不可用、`test_goal_schemas.py` v3 reports opt-in、`test_recovery_schemas.py` v4 report opt-in、`test_runtime_build.py`未提供本机引擎资产、`test_schemas.py`本地快照/报告及真实v2报告opt-in、`test_strategy_schemas.py`完整策略报告opt-in、`test_tournament_gate.py`缺独立2026资产配置。

151项Rust/Cargo源文件（140 Rust源文件、11 Cargo文件）与V2认证清单逐项一致，缺失、新增、变化均0；本批Rust/Cargo未修改，引用先前格式检查、workspace全目标Clippy和380通过/37忽略的workspace验证，不重复运行。真实资产opt-in、doctor及48手评估均未运行。独立审阅确认V3 runner按固定来源根解析，V1/V2语义保持独立；未发现新的来源绕过。

隔离runner使用`CARGO_TARGET_DIR=target/curry-ledger-handoff-v3-build`并以相同`--target-dir`执行`cargo build --offline --locked -p ygo-engine-adapter --example curry-option-validation`。源码身份为`148a8df98a314db571c3825f5cf472fa410801097d9daeb4d3645a5d2d847da0`（563项）；build-record SHA256 `b87073c899124942148c623fe1f26e412172f10f38dd1d1009a897bb3f5e08b7`，identity `16a5bcfb380180c1c8af7686e9ab6a6abe1d1bee316f32dceecc4abf70da69b0`，状态`recorded`。runner SHA256 `6f6cc47b090525f49fe4c443a91a0a63889d4b4284a1bad3b38d65086f2a7c44`，源码ZIP `80366616585ca58e59fac4fbabc793c66ce90bd0611e5da3558bff5c66255deb`，清单`7d05667aed55f0c1b03c0be0073afb3f45a2236bde5471975cceeecd48d5964c`。runner只构建，未执行。

唯一一次真实V3只读审计以固定命令运行：`py -B -m ygo_eval.research audit-curry-ledger-handoff --report-version 3 --baseline-dir data/runtime/p1-curry-option-verification-native-2026-10-25 --runner data/runtime/p1-curry-ledger-handoff-v3-offline-2026-10-25/native-artifacts/curry-option-validation.exe --build-record data/runtime/p1-curry-ledger-handoff-v3-offline-2026-10-25/build-record.json --output data/runtime/p1-curry-ledger-handoff-v3-offline-2026-10-25/audit-report.json`。退出码1，报告耗时19.671843秒，SHA256 `b0c8aa022a02b00ad546a37d04890a36c14eeeb29082447aef4def35b6fe10bf`（11,194字节），Python运行时合同及V3 JSON Schema通过。`failure_checkpoint=stage1_parent_receipt`、`diagnostic=curry_saved_stage_process_output_invalid`；previous failed sources、V2 final source、acceptance/delivery、dual-timepoint sources、reservation/history、frozen scope inputs六项通过。stage2 saved intent、isolated runner build、saved input audit均为`not_run`。本批runner的`process_attempted=false`，`process-diagnostics/`没有创建。

只读检查发现失败原因是已存stage 1进程的有效stdout包含三字段结果及V3预留会计扩展；现有通用stage输出验证严格比较三字段对象，导致真实V3输出的额外`certified_historical_consumed=32`、`certified_consumed_including_new=33`、`planning_base=39`、`planning_total=40`、`policy_reserved=7`、固定reservation ID及旧/全历史实际消费`null`触发拒绝。该阶段只读解析旧收据和侧车，没有修改它们。后续saved-input进程未启动，故没有新增消费，也不将失败报告解释为重新认证stage 1。

报告会计中认证历史子集32、政策预留7、规划基数39；本批消费、unknown、planning total、旧confirmation实际消费及全部历史实际累计均为`null`。原账本SHA256仍为`7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`，stage 2 receipt仍缺失。原V1/V2失败报告SHA256保持`4b3a802cb26097ec2bdf48ef59ffe56103ac87fc3b0842209feb3a7c89e0ec2e`和`9d74b97e6553ba141537bae414e0f60740220de48e0b031fdb6bff0bad0928c1`。新增原生调用0，未创建scope/窗口/收费账本；四项资格均false。详见[本批断点](superpowers/plans/2026-10-26-curry-ledger-handoff-v3-handoff.md)。不在此固定输出目录重试或覆盖，不切换部署，不提交或推送Git。

## 2026-10-25 Curry V2账本交接恢复审计：离线验收通过，真实只读审计首门禁失败，新增原生0

完成V2来源描述/schema约束、公共入口合成来源树回归及离线runner构建。合成成功和失败路径、固定角色唯一性及V3来源数量限制通过聚焦测试与V2 schema；独立只读审阅确认固定来源门禁没有放宽。Python全套显式列举68个顶层`tests/test_*.py`文件，555项共`546 passed, 9 skipped, 0 failed`，用时806.42秒。日志为`target/curry-ledger-handoff-v2-tests/pytest-full.log`，文件清单为`pytest-files.txt`；跳过明细由pytest `-ra`记录：两个Windows目录符号链接能力限制、v3/v4报告、本机引擎资产、快照/真实v2、完整策略和独立赛事配置opt-in。151项Rust/Cargo源码与已认证清单一致，本批未改Rust；引用既有workspace 380通过/37忽略、格式及全目标Clippy验证。真实资产opt-in、doctor、48手评估未运行。

隔离runner构建命令采用offline/locked及独立target，runner SHA256 `f3cd6148e62addb164e6efd1d613fbcfb6ec81f428ea77c273b436e5f98db8ac`。构建记录SHA256 `eef3a7c9519c7996c12b65ef04b0b93a22448a1902419d1e70b7428581307930`、identity `6020ab76de9a097ef28611ff439f061af313c20f6e259d47c222616a5ee2b961`；source identity `cf271cd66778dbc2f3ea066bb1be7df257163686745f8eafdc116a8a2fb52e6e`（557项），源码ZIP SHA256 `0f6851a7cb2dd9f03f96c730739b9ab6b57b966d8bc5a656a75acc71af570e2a`，清单SHA256 `3dd1eb14e80d97c7f1c6631c77b6817c75843e21d0d5fb721f7b02ac97558784`。

固定V2真实审计仅运行一次，退出码1。报告`data/runtime/p1-curry-ledger-handoff-v2-offline-2026-10-25/audit-report.json` SHA256 `9d74b97e6553ba141537bae414e0f60740220de48e0b031fdb6bff0bad0928c1`（3532字节），通过Python运行时合同及V2 JSON Schema，状态`failed`、首个失败检查点`previous_failed_source`、诊断`audit_failed`。其余检查为`not_run`，`inputs=[]`，runner return code、stdout/stderr及process capture均为null；没有进程诊断侧车，saved-input runner未启动。报告采集到baseline、reservation、ledger、runner build及workspace稳定，stage 2 receipt before/after均缺失。没有据此推断旧scope消费为零。

静态复核定位到V2前次失败包路径角色错误：代码要求`native-artifacts/curry-option-verification.exe`，V1审计交付实际的runner是`native-artifacts/curry-option-validation.exe`，SHA256 `cd5f294e99aa5c44935e2ef414865a6f46fa2c8bbb5230f018d31ad606365b8d`并与V1 build record匹配。若只改路径，下一项静态根因判定仍不成立：548成员V1源码归档中的`verify_parent_request`已经返回`Result<()>`并在独占打开前释放只读view，因而“归档仍包含父读视图跨独占打开缺陷”的断言会得到false。此第二项未由真实审计运行到；未修补后重试。

原V1失败报告仍为`4b3a802cb26097ec2bdf48ef59ffe56103ac87fc3b0842209feb3a7c89e0ec2e`。原scope ledger SHA256仍为`7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`；stage 1消费/完成1、未知0沿用既有认证，stage 2 receipt仍不存在。本批没有启动saved-input runner，故不声称重新验证了ledger。既有认证子集33/未知0、政策预留7、规划40保持既有口径；旧confirmation实际消费和全部历史实际累计仍为null。native_calls固定0，execution_ready=false，四项资格false。文档定稿后的源码归档、文件清单及最终完整性记录保存在忽略目录`target/curry-ledger-handoff-v2-tests/final-source-release-doc-final/`；两棵本批证据树的体积及访问错误记录见`target/curry-ledger-handoff-v2-tests/evidence-size-release.json`。该清点保留ACL受限临时目录的访问失败，不调整权限。下一断点及禁止重试/覆盖边界见[本批断点](superpowers/plans/2026-10-25-curry-ledger-handoff-v2-handoff.md)。

## 2026-10-25 Curry V3预留绑定的Curry七阶段验证：stage 2停止，新增消费1/7

固定scope `curry-option-verification-v1`、窗口起点`1792898169`、额度7次/7200秒。V3预留verify-only在收费前通过：预留ID `09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63`，预留报告SHA256 `14c13e4992673115c0211259dd7d035d968b9c36518c28b4b4ea159ff06ad43f`，delivery acceptance SHA256 `704a72b2ad65ba95874030f199158a673ce18e19901b29d9bfb63f3fb8d78318`。

隔离构建记录为`data/runtime/p1-curry-option-verification-native-2026-10-25/build-record.json`，SHA256 `6d4b079ab3fd3971b8c1ecf41a974b93171d5872c89aa576019688d87444ce66`；状态`recorded`、退出码0，构建前后源码身份均为`50bc44ed37aefdc39f33a61afaca021a8dfbe037869f118b5ad3e129d4011b24`（544项），可复现构建仍未证明。原生时点源码ZIP SHA256 `d8058a5043a8367be32fc76d966c84c1089e5369fc826c8e56b17fbdb7b1f600`，文件清单SHA256 `4a87cbcf5173ff854e7aa7df1afedf0c89d01e72efbe0745e41d6130a3bd1463`。CLI、worker、runner哈希分别为`44bd5206609d021781a5029232d751bd519524876e770084c03314a180426f48`、`79c65f276d34097c11eb3dfa4efed5c3850ba2a760415fb0af7064909af7b9d3`、`aae876badfe006098dbffa98b61b8f76818cc5dbaab142cc3d499f354eec8952`；复制件均与build record匹配。

`--prepare-only`通过：`prepared=true`、`execution_ready=true`、新增调用0；manifest SHA256 `60106527e484763dd8b9f323b847a7ed051e0302dffabf8f48f0f71a3347e44b`，21个输入角色；prepared SHA256 `7f94f982f89ca1c2b720f32250f8e4f9451ec0eb99ba5a4afcec7dd7fc23c5ee`。该步骤在首次普通/赛事候选资产身份扫描前固定窗口起点，随后完成双资产身份采集。收费前账本不存在。

七阶段normal仅完成stage 1并认证消费1次。stage 1 receipt SHA256 `14366ed0f61f0e38c13268535bea865b6aace084b11d3ab6943fa202785b1f4e`，stage report成功，消费增量1。stage 2的request/input/report及进程诊断均已保存；根级进程诊断引用SHA256 `be2e52a1dc689304830802ca74a8fa30436b53879863ff120170344810f492c2`，对应的进程元数据文件SHA256 `378349a926c131a6c22cd2fe003425dffd0440ebe6eefd6efa79cacf18fcd108`。runner退出码2；原始stdout为0字节（空流SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`），stderr为528字节、SHA256 `f7a73b6c29c00e90778b0dda4521e468817aa74184289768f25f4e61b1549227`，内容报告`The process cannot access the file because it is being used by another process. (os error 32)`。追踪记录已结束`ledger_check`，未记录`batch_call`；无stage 2 receipt。stage 2 report保留`runner_output_invalid_or_nonzero`，不将该异常解释为另一次消费。收费账本SHA256 `7f4f97e65bffbdf7ea9471b92b2ffa16fda06433972dd2c5c52b92ec7197251c`，2,726字节；summary SHA256 `21f7818aae8595f2ee1fb18b23be39ad5802d26e257c225fa1fa26a33f1b73e9`，记录消费1、未知0、认证历史子集含新增33、规划总数40、旧confirmation与实际全部历史仍null。

随后`--verify-only`只执行runner只读验证/统计，报告`native_calls=0`、消费1、未知0，但`valid=false`、诊断`incomplete_saved_stage_files`，因为stage 2没有完整receipt。报告SHA256 `831201cd9166bf271c17fd8f6adbee4afa1964b9d1b7087a3119d42edced1a8a`，保存在独立检查目录`target/curry-option-verification-checks/14a607e5e6a744fd95229e81403c98ca/`，未覆盖原summary或stage证据。按固定停止门禁，未执行stage 3–7、未调整线路、未重试；余6槽封存。文档冻结后的源码归档、构建关联及验收索引另存于该scope的`final-build/`，与原生时点产物分开绑定。

离线验证在本批原生前完成：显式枚举63个Python顶层测试文件，494 passed、9 skipped、166个subtests passed（677.40秒）；跳过项及Rust结果见本文件下一节历史原生前记录。原生前聚焦组89 passed、58个subtests passed。原生期间和收尾未运行doctor、48手评估、真实资产opt-in；未切换普通部署、active资产或提交Git。四项资格继续false。详细续接与停止边界见[本批断点](superpowers/plans/2026-10-25-curry-option-verification-handoff.md)。

## 原生前记录：Curry V3预留绑定的七阶段验证离线总检

完成`curry-option-verification-v1`第三种固定scope、Python入口及Rust runner实现。绑定V3 reservation SHA256 `14c13e4992673115c0211259dd7d035d968b9c36518c28b4b4ea159ff06ad43f`、ID `09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63`、认证历史32、风险预留7、规划基数39；旧confirmation实际消费和全部历史实际累计仍为null。

verify-only增加经哈希认证的runner stdout复核，并与receipt、消费增量和固定scope会计绑定。TDD覆盖损坏stdout报告被伪造成成功时拒绝，及带部分输出的合法timeout仍保存为失败、未知消费不归零。Rust scope实现由独立审阅通过；Python修复由独立复审通过。聚焦相关三个scope测试54通过、33个子测试通过；完整聚焦选择组89通过、58个子测试通过（8.35秒）。

显式枚举63个顶层`tests/test_*.py`文件运行全套：494 passed、9 skipped、166个subtests passed，677.40秒；使用`-ra`，跳过项逐条为：两个Windows目录符号链接测试不可用；v3报告、v4报告、本机引擎资产、真实快照/报告、实际v2报告、完整策略报告及独立2026赛事配置为opt-in。文件清单及日志位于忽略目录`target/curry-option-verification-python-tests/`：`top-level-test-files.txt` SHA256 `3ded520041821aeb951f3f63c9a17508b72338d7ea334737a37994568d6aeae4`；`final-full-pytest.log` SHA256 `df283c53e20cc84afdd89930e3ac6426a694c0d03ff91e65919ce81f6a0813c2`。

Rust：`cargo fmt --all -- --check`通过；隔离target下workspace all-targets Clippy通过；workspace串行测试328 passed、36 ignored、0 failed（87套）；workspace examples 47 passed、1 ignored、0 failed（9套）。所有编译命令使用`target/curry-option-verification-rust-target`、`CARGO_TARGET_DIR`和匹配的`--target-dir`，并加`--offline --locked`。不运行真实资产opt-in、doctor或48手评估。日志在同一忽略目录的`rust-fmt.log`、`rust-clippy.log`、`rust-workspace.log`、`rust-examples.log`。

V3预留verify-only再次通过，输出`valid=true`、`native_calls=0`、诊断空；原reservation字节SHA不变。新scope固定输出根、窗口和收费账本均仍缺失。此次没有调用新runner、worker、FFI或扫描普通/赛事资产，不能报告任何新scope消费。原生阶段待隔离构建与准备门禁；暂停边界和精确顺序见[前离线验收计划](superpowers/plans/2026-10-25-curry-option-verification-pre-native.md)。四项资格仍false。

## 2026-10-25 Curry V3风险预留：真实只读审计及verify通过，新增原生调用0

V3一次性真实审计命令：`py -B -m ygo_eval.research prepare-curry-consumption-reservation --report-version 3 --baseline-dir data/runtime/p1-curry-recovery-synthetic-e2e-offline-2026-10-24 --output data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25/reservation.json`。7项检查全部通过：两次失败来源、恢复源码归档、最新delivery链、真实V2审计、旧confirmation、九份历史账本和输入稳定性。报告SHA256 `14c13e4992673115c0211259dd7d035d968b9c36518c28b4a4ea159ff06ad43f`（36,306字节），schema校验通过。来源清单含100个输入绑定；confirmation保持64条角色行、43个物理路径、40个证据别名。天玑账本通过目录摘要、acceptance和保护清单绑定。

预留ID `09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63`，政策固定预留7次，规划基数39。九账本已认证32次/未知0；旧confirmation新增/累计/未知消费均为`null`，全部实际累计仍为`null`。报告记录历史观察声称退出码1、归档静态返回值2，历史真实退出码未认证。新旧输出树稳定，旧收费账本保持缺失。

随后执行同一固定命令加`--verify-only`，退出码0、`valid=true`、`native_calls=0`。V3报告前后哈希均为`14c13e49…06ad43f`，字节未变。

聚焦回归：19通过、1跳过、22子测试通过（242.08秒）。显式枚举`tests/test_*.py`顶层62文件运行`py -B -m pytest -p no:cacheprovider -q -ra <pytest-files-v3-2026-10-25.txt>`：480通过、9跳过、152子测试通过（830.55秒）。跳过项为两项Windows目录符号链接能力限制，以及v3/v4报告、本机引擎资产、真实快照/报告、实际v2报告、完整策略报告和赛事独立配置的opt-in。完整日志/文件清单：`target/curry-consumption-reservation-v3-tests/pytest-full-v3-2026-10-25.log`和`pytest-files-v3-2026-10-25.txt`。两次独立只读审阅均通过；其中一项可选改进是为V2输入索引显式增加外部acceptance缺席断言，现有V3成功路径及来源哈希测试已覆盖该数据形状。

审计前冻结源码身份`d76728dbd79ab42fcda13320c615683518fc70dd85a6219846244c6d02d0003d`、540项；ZIP SHA256 `dacf18ff0bb3ca0bee2a2ff79ddb2ee00b7ef5ead0184bee00f9632942ff1977`，清单SHA256 `f0dedaff625fac2c83edaaa8b4daa587165404f67cfe88f90b24facfdb40a96a`。真实审计使用的8成员工具归档身份`69efac5351abf120f111e697ee9c596f864512201ae3ecf4060f3d6f185772b8`，归档SHA256 `42d21e39eae265cecc95b37fd521fc8cd02b160123a51911f1220dcdb9a3ef82`。Rust/Cargo 151项与V2最终源码归档逐项一致；此前159项选集还包含8项生成证据，本批更正口径，不重跑Rust。

原V1失败报告、V2失败报告、V2 acceptance及所有旧材料保留原字节。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`继续为false。所有测试、审计输出、进程原始字节及证据归档见[本批断点](superpowers/plans/2026-10-25-curry-consumption-reservation-v3-handoff.md)及忽略目录`data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25/`。

## 2026-10-25 Curry v2风险预留恢复：合成验收通过，真实来源门禁失败，新增原生0

实现并保留独立`curry_consumption_reservation_v2`版本；V1缺省命令、合同及六成员工具归档不变，V2使用七成员工具归档并先核验V1失败来源。成功态V2报告在Python校验器与JSON Schema中均要求至少一条输入记录。新增空`inputs`负例先在schema层失败，随后加入精确断言`reservation_success_inputs_missing`；V1对应语义未修改。完整V2合成公共CLI路径覆盖V1失败材料、检查顺序、成功规划值和verify-only；本轮全套Python测试后再次运行修正过的关键负例，均通过。独立只读审阅记录见忽略目录`target/curry-consumption-reservation-v2-tests/independent-review-v2.json`。

全量测试命令通过PowerShell生成并显式传入60个`tests/test_*.py`顶层文件：`py -3 -m pytest -ra -q -p no:cacheprovider @pytest-files-v2.txt`。结果472通过、9跳过、147个子测试通过，耗时772.47秒；完整清单和日志位于忽略目录`target/curry-consumption-reservation-v2-tests/pytest-files-v2.txt`及`pytest-full-v2.log`。9项跳过为：reservation目录符号链接创建在该Windows配置不可用；optional-source目录符号链接不可用；v3报告、v4报告、本机引擎资产、真实快照/报告、实际v2报告、完整策略报告和独立2026赛事配置均为opt-in。最新修正后的合成成功/空输入负例聚焦运行`py -3 -m pytest -q tests/test_curry_consumption_reservation.py -k synthetic_v1_failure --tb=short -p no:cacheprovider`为1通过（39.24秒）。`py_compile`与V2 schema JSON解析通过。Rust/Cargo未在本批修改，引用此前认证的159项清单及Rust格式、Clippy、workspace和examples结果；本批未重复Rust总检。

审计源码在真实检查前完成完整冻结：身份`be9414a756ab436ba12221f178ea23bbb55ac00bfa0ff55c170ca69647bafc98`、535项；归档SHA256 `8104ee889d2ae0a686fb5b5a3cba8add1076ad22f29e029f871ee825eea9eb67`，文件清单SHA256 `08dd2255a19eea71b1a8d92c03051e1d7b20717265044b91ce7f4005dfb180c9`。正式V2命令只执行一次，退出码1；新报告SHA256 `5fb0cd2e10d3477fd09544e85e02b5234386b60668721ba33bc85ccb1db745da`、5,338字节，通过v2运行时合同和JSON Schema。V1失败来源检查通过；第一业务门禁`latest_delivery_chain`失败，稳定诊断为`independent_review_invalid`，后续检查均`not_run`。固定review文件没有`public_cli_bypass_found`字段，而当前门禁要求该字段为false，故本次不进入报告、旧scope及历史账本核验。预留未记录、ID/规划总额/本次历史统计均为null，`native_calls=0`。依据一次性规则，未执行verify-only、不修补输入、不重试；V1报告SHA256 `17dd4b3f08c4c13c1d440bf6641a3fa4b9c9ae498e652c5d852156c8891ee3e7`仍匹配。正式输出目录由失败件独占，后续不能覆盖或复用。该错误链不认证历史实际退出码，也不改变旧scope消费仍未知的状态。

未创建原生scope、窗口或收费账本；未启动runner、worker、FFI或doctor。全部历史实际累计仍为null；既有九账本32次/未知0只作为此前认证基线，本轮没有重验。续接及恢复条件见[本批断点](superpowers/plans/2026-10-25-curry-consumption-reservation-v2-handoff.md)。

证据体积清点只遍历本批测试/冻结目录与V2失败输出：分别13,230个文件、65,267,339字节及3个文件、352,946字节，访问错误0。该记录仅代表两棵本批证据树，不包括旧历史或ACL受限目录；明细见`target/curry-consumption-reservation-v2-tests/evidence-size.json`。

## 2026-10-25 Curry预算风险预留准入准备：真实来源门禁失败，新增原生调用0

新增`python -m ygo_eval.research prepare-curry-consumption-reservation`、独立`curry-consumption-reservation-v1`合同及只读`--verify-only`路径。合成公共CLI回归贯通成功预留、确定性ID、32＋7规划口径、旧scope实际统计保持null、保存报告只读核验、输出碰撞拒绝和四个固定来源篡改停止点。独立只读复核未发现生产门禁放宽或原生副作用；复核要求的来源篡改覆盖已纳入回归。

修正后的全量Python命令显式传入60个顶层测试文件：`py -B -m pytest -p no:cacheprovider -q -ra <pytest-files-final-2026-10-25.txt中的文件>`，结果469通过、9跳过、145个子测试通过，用时602.21秒。跳过原因：reservation和optional-source两个Windows目录符号链接测试不可用；v3、v4报告、本机引擎资产、真实快照/报告、实际v2报告、完整策略报告及赛事独立资产均为opt-in。完整文件清单、完整日志和退出码位于忽略目录`target/curry-consumption-reservation-tests/`。修正前完整复跑为468通过、9跳过；不作为最终计数。另有固定来源负例聚焦测试4子例通过，锚点回归1项通过；`py_compile`通过。

对固定真实基线的命令只运行一次并以退出码1结束。报告路径为`data/runtime/p1-curry-consumption-reservation-offline-2026-10-24/reservation.json`，SHA256 `17dd4b3f08c4c13c1d440bf6641a3fa4b9c9ae498e652c5d852156c8891ee3e7`，有效通过报告合同与JSON Schema，但状态为`failed`，检查点`latest_delivery_chain`，诊断`delivery_anchor_mismatch`。固定delivery SHA256 `5ede9f0f47742e07961fe7341c70777b134bff43dbeae267890c65a0c906f64e`及其内容/所引用文件哈希核对表明，源码中的`ACCEPTANCE_SHA256`少了一个字符（63位）；delivery与真实acceptance文件的64位哈希一致。常量已修正，新增固定profile回归并通过完整复跑。失败报告仍绑定修正前工具源码，未改写。

该单次真实检查在失败前后确认baseline、v2报告树、confirmation树内容稳定，旧charge ledger保持缺失；失败发生在读取v2报告、旧scope和九份历史账本之前。本次报告明确`native_calls=0`、预留未记录、旧scope实际新/累计/未知消费为`null`、历史统计未核验为`null`，不宣称规划基数39已发布。没有运行runner、worker、FFI、doctor，也没有创建新窗口、scope或收费账本。旧九账本32次/未知0沿用此前认证事实，本轮没有重算。由于固定输出目录已由失败报告独占占用，本轮不覆盖、不换目录重跑；失败报告合同校验通过不等于只读verify成功，`--verify-only`未对失败报告执行。

Rust/Cargo源码未改动，沿用既有159项文件清单与此前格式、Clippy、workspace及examples验证；本轮未重新运行Rust总检。下一次尝试需先定义版本化恢复路径，保留本次失败原件并解决固定输出目录冲突，再对真实材料重新核验。详见[本批断点](superpowers/plans/2026-10-25-curry-consumption-reservation-handoff.md)。

## 2026-10-24 Curry公共审计完整合成验收：通过，新增原生调用0

按[本批断点](superpowers/plans/2026-10-24-curry-recovery-synthetic-e2e-handoff.md)完成来源节点消歧及公共合成验收。旧Curry归档和允许差异显式取自`asset_audit_scope`，历史链从`historical_chain`传递；不改通用查找规则。生产来源描述的固定哈希、计数、节点和完整树黄金摘要均有回归锁定。合成公共入口覆盖7项检查，九份账本真实解析器核算消费`9/8/1/4/2/2/0/0/6`、总计32；最早账本37条记录。报告通过Python校验器与Draft 2020-12 schema。

隔离合成成功报告SHA256 `45d127bed0f27870167c042a23f8f253c88fb4338edc17ca73a9dc6443578812`，`native_calls=0`、`execution_ready=false`；本批不重新运行旧真实审计。纯字节保护检查确认旧v2报告SHA256 `67c6332310aed1e77ccc9eb4394b700f4169837b198a50de20d422dc01da757b`、验收`data/runtime/p1-curry-v2-validation-2026-10-24/final-delivery-after-docs-v2/acceptance.json`SHA256 `20654b7d09247f5f71acd038c6f72546b50a8bfa85f0a3bb9041fc297b1c69e0`及九份受保护账本仍匹配固定字节锚点。旧Curry confirmation账本保持缺失、消费为null。独立只读审阅通过，无生产锚点放宽或CLI绕过。

全量测试命令为`py -B -m pytest -q -ra -p no:cacheprovider`加显式列举的59个顶层`tests/test_*.py`文件；结果461通过、8跳过、130子测试通过，497.48秒。8项跳过：目录符号链接不可用（OSError）；v3报告、v4报告、本机引擎资产、真实快照/报告、实际v2报告、完整策略报告、独立2026赛事配置均为opt-in。首轮仅有一项合成来源夹具缺少逐账本消费数；补齐后同一清单全套复跑通过。逐项日志及命令文件清单保存在`data/runtime/p1-curry-recovery-synthetic-e2e-offline-2026-10-24/`。证据目录文件数、字节数及访问失败见`evidence-size.json`（该清单不计入自身）；目录外旧ACL受限临时材料保留原状。Rust/Cargo本批未改动，引用前批159项认证源码和已通过的fmt、Clippy、workspace及examples检查。

真实已认证历史仍为9账本、32次消费、未知0；旧Curry confirmation消费继续为null，七个旧槽位封存。无runner、worker、FFI、真实审计、doctor、实验窗口或收费账本活动；四项研究资格均保持false。正式交付仅包含合成验收证据和源码归档，不改变真实证据资格。

## 2026-10-24 Curry v2清单驱动审计：真实只读核验通过，合成总流程仍有缺口

按本批计划修复Curry冻结输入恢复审计器，并对固定confirmation交付只运行一次纯Python只读审计。命令为`python -B -m ygo_eval.research audit-curry-input-recovery --report-version 2 --baseline-dir data/runtime/p1-curry-option-confirmation-native-2026-10-24 --output data/runtime/p1-curry-input-recovery-v2-offline-2026-10-24/audit-report.json`。v2报告通过7项检查：acceptance/delivery锚点、证据清单、归档、冻结输入绑定、历史账本、旧材料保护和输入稳定性。报告SHA256为`67c6332310aed1e77ccc9eb4394b700f4169837b198a50de20d422dc01da757b`，142,277字节，耗时70.474482秒；审计时工具身份`62b0729c20381023f655fb08f47863f8150c6de8d713f273c39e6bf4d99b8c06`、508文件。模块校验器和Draft 2020-12 schema均通过。

报告重新认证9份历史账本，共32次、未知0；其不可写journal核验通过。旧confirmation ledger采集前后均缺失，但该scope的新增消费、累计消费和未知消费保持`null`，七个槽位继续封存。历史输入绑定修复通过：`base_request`和`candidate_case`的规范化对象哈希与manifest一致，原始容器SHA单独记录；旧失败报告仍保持原SHA `e6140724dc2048b82165a98306d970b4793cee6e4d9c46e487e98a49d6131e14`。观察记录声称退出码1，归档静态分支返回2；历史实际退出码未认证，旧失败没有被改写为成功，也未重跑。

测试：Curry审计和CLI dispatch聚焦共31项通过；显式枚举所有顶层Python测试文件的pytest结果为419项，412通过、7跳过、0失败（186.870秒）。7项跳过分别为v3报告、v4报告、本机引擎资产、快照/报告、实际v2报告、完整策略报告、独立2026赛事配置opt-in；日志保留逐项测试名和原因。Rust/Cargo源码与上批认证清单157项匹配，本轮没有Rust/Cargo改动；引用上一批已通过的`cargo fmt --all -- --check`、全目标Clippy、workspace 325通过/36忽略及adapter examples 42通过/1忽略。独立审阅记录在`data/runtime/p1-curry-v2-validation-2026-10-24/independent-review.json`，指出完整九份合成账本贯穿公共审计入口的成功夹具尚未实现；因此本批只报告真实只读审计通过，不把合成覆盖缺项写成完成。

审计固定`native_calls=0,execution_ready=false`；未启动runner/worker/FFI、未调用子进程、未打开可写账本，也未创建窗口或收费账本。`proof_ready`、`complete_action_coverage`、`global_optimality`和`native_probability_verified`均为false。源码与断点见[本批续接](superpowers/plans/2026-10-24-curry-input-recovery-v2-handoff.md)。

## 2026-10-24 Curry 公共审计合成验收：额度不足时暂停，未完成

本批承接Curry v2清单驱动只读审计后的完整合成来源树公共入口验收。曾运行提示来源固定聚焦测试：初次因测试辅助函数错误引用`audit.sha256_file`失败，改用标准库哈希后，测试发现合成辅助函数会重写子来源已固定的提示文件；修复后该单测通过（10.99秒）。较早一次聚焦运行结果为3失败、6通过、5个子测试通过（77.17秒），失败发生在当时尚未补齐的公共递归成功路径材料。之后补齐合成历史消费计数、递归来源身份字段、归档成员与delivery audit相对路径、verify统计；最新直接完整路径已推进至外层合成归档缺失两个必需成员。该归档修补刚完成，未复验；不能报告完整合成验收通过。

用户告知Codex五小时额度不足5%，因此此处暂停继续测试。固定交付目录尚未创建。完整Python总检、独立最终审阅和交付未进行。本批新增原生调用0；没有运行真实审计、runner、worker、FFI或doctor，也没有创建scope、窗口或收费账本。已认证历史九账本为32次、未知0；旧Curry confirmation消费仍为null。ACL受限pytest临时目录保留原状。恢复命令、最后未验证补丁和剩余验收见[断点记录](superpowers/plans/2026-10-24-curry-recovery-synthetic-e2e-handoff.md)。

# 本机验证记录

## 2026-10-24 Curry新scope七阶段确认：收费前normal编排拒绝，按门禁暂停

按[本批断点](superpowers/plans/2026-10-24-curry-option-confirmation-handoff.md)新增固定scope `curry-option-confirmation-v1`（最多7次、7200秒、单worker串行）。本批改动包含Python固定scope/新报告合同/Rust批次路由，以及归档角色哈希和`verify-only`准备状态门禁修复。新增回归测试先观察到4个失败，再修复；聚焦测试51项通过。Python全套`py -m unittest discover -s tests`最终为398项、7项跳过、0失败（210.290秒）。跳过项均为现有真实资产、完整快照/报告、赛事资产或版本化报告opt-in；测试错误输出是预期负例。Rust `cargo fmt --all -- --check`、workspace全目标Clippy（offline/locked、隔离`target/curry-option-confirmation-checks`）通过；workspace串行默认测试及examples测试通过，真实资产opt-in保持忽略。

独立审阅确认：`verify-only`在读取收据前要求`prepared=true`及`execution_ready=true`；源码ZIP和文件清单SHA256还须分别与manifest `input_sha256`角色一致。最新基线只读核验匹配delivery SHA256 `58f9d28bcf5ac20cd3ee517aa70a6cc9fec294973a295a51d1dc415b4212eee0`及audit SHA256 `f31e019affc99d3cf8cfc81921f72a424c904fcc4750b67a0a443ae3fc5a74b5`；9份历史账本32次、未知0，545项保护材料通过。新隔离构建状态`recorded`，源码身份`316443a5aa270488fb5ab88f463174a9e6c3f66cc9ddc1702c1ffe96f0525408`、501文件，构建记录SHA256 `a576968b9cdcc69fce1791a262b6b57d4e58e81c2f4ab77918f2ad35d15f718b`；runner/worker/CLI SHA256依次为`f9c3c9925599952c2ccf9e724c57e76140fe5f24b6949331e292dc7ff17b5c22`、`87c2f44ab0e64d72870c0879cc6ac78895bc43023a492512c2893480e313f376`、`2f0813f3e5caf791d745a024714584f17510ee994a54051f85906f510a0a2bfc`。`reproducible_build_proven=false`。

`prepare-only`在首次候选身份采集前创建新窗口，起点`1792787058`；manifest源码身份与构建一致，双资产身份及候选请求冻结完成。隔离runner `--preflight-only --trace-stderr`通过，`prepared=true,execution_ready=true,native_calls=0,planned_calls=7`，其diagnostic SHA256 `4cddd741871cedbe5064fe18f621cbffde549a2626fecf80e00f2b3a1cf2efa1`。窗口创建后的normal命令返回通用拒绝文本`native-curry-option-confirmation refused: frozen input, build, ledger, or output check failed`。未保存normal进程诊断、stage收据或`research/calls.jsonl`。没有重试。只读状态诊断重算时源码仍匹配manifest、21项冻结输入哈希无差异、delivery哈希匹配；但拒绝原因未能由安全只读核验进一步定位。

`--verify-only`仅核验已存文件，不执行缺失阶段，报告`valid=false,native_calls=0,diagnostic=incomplete_saved_stage_files`，`new_consumed/cumulative_consumed/unknown`为`null`。根据该报告构造并schema验证了失败summary：`successful=false`、新增/累计消费和未知均为`null`，诊断`normal_cli_refused_without_authenticated_stage_receipt`；它是保存状态的收尾摘要，不是runner生成的stage结果。账本不存在、0个stage收据，故不能把原32次直接扩写为“32次累计已确认”，也不能宣称七阶段失败具体发生于哪条卡效果。四项资格继续为false；新scope不得重试或重开，后续需先离线定位normal拒绝，再另立scope/预算。准备输入、summary、verification、runner诊断、构建及源码归档见忽略目录`data/runtime/p1-curry-option-confirmation-native-2026-10-24/`；文档后最终归档和build另见其中`final-build/`。

## 2026-10-24 Curry哈希角色修复与只读验收：通过，新增原生0

按[本批断点](superpowers/plans/2026-10-24-curry-asset-binding-audit-handoff.md)完成离线修复和验收。`versions.engine_sha256`现在与DLL身份比较，manifest worker输入另行与worker身份比较；normal经过共享预检、收费前与收费后三次资产采集，显式preflight一次采集。角色hash使用不同的合成值测试；缺失DLL、DLL/worker混淆、manifest worker失配、预检失败及到期均拒绝，adapter收费调用为0。

验证命令及结果：Python全套`py -m unittest discover -s tests -p 'test_*.py' -v`，382项总计、375通过、7跳过，用时191.278秒；跳过项依次为v3报告、v4报告、本机引擎资产/ABI、真实快照/报告、实际v2报告、完整策略报告、独立2026赛事资产配置。完整明细和理由保存在忽略日志`data/runtime/p1-curry-asset-binding-offline-2026-10-24/verification/python-unittest-final.log`。Rust `cargo fmt --all -- --check`、workspace全目标Clippy（offline/locked、`-D warnings`）通过；workspace串行测试325通过、36忽略；adapter examples串行测试42通过、1忽略。忽略测试及原因在同目录Rust日志中逐项记录。`py_compile`、CLI help、聚焦审计测试也通过（19项及4个子测试）。无真实资产opt-in、doctor、normal阶段、worker或48手评估。

审计源码身份`43f4518145e6fa0157896c96f6d48dcd9df89c80f24d64bfc6a116b6be7e62f2`、498份文件；源码归档SHA256 `a235cf00ee038196782e1e33992bc7719d5dce9169d56d204f5d99167a5fbbde`、文件清单SHA256 `75b21e3fd265ffac5c9bca78c4d067c6a479f937d07461733ef8fec73e005aff`。审计runner构建记录SHA256 `da933dbae09031d5646cbed1eccdcafc403e3378e071f85e70d6d4b0945429e2`，runner SHA256 `f0cc84f858c8bbd5bc771cf6146850b8dfeabb9f78ffbff633cf53c15f479240`。固定旧验收锚点和原输入/预期身份匹配；只读报告9项检查通过，历史9账本32次/未知0，`research/calls.jsonl`仍不存在。runner返回0，报告结果`preflight_passed=true,native_calls=0`，stdout单JSON 239字节，stderr追踪225字节；实际共享预检耗时161.618秒。旧Curry报告仍`prepared=false`及原失败诊断，七个槽位保持封存。报告和原始诊断保存在忽略目录；文档后独立构建、源码归档、文件清单与证据体积另见其`final-build/`和`verification/`。

验证目录首次被本批合成测试误创建时，测试在固定输出根下留下一个空`test-fixtures/`目录。已只读核查并保留该空目录，没有删除或覆盖历史材料；其余审计输出全部位于新增忽略目录。四项资格保持false，累计消费仍32、未知0。

## 2026-10-24 Mooyan Curry opcode14七阶段批：离线检查通过，收费前预检阻断，新增原生0

按[本批断点](superpowers/plans/2026-10-24-curry-option-validation-handoff.md)实施固定scope `curry-option-validation-v1`（7次/7200秒）。先完成RECOVER92生产解码与独立原始帧oracle、七阶段调度/父收据/重放合同、进程诊断保护及Rust测试输出根目录修复。原始Python日志共373项，其中366项通过、7项opt-in跳过（152.259秒）；原记录曾把“总计”误写成“通过”，此处予以更正。Rust格式和workspace全目标Clippy通过；串行workspace测试325通过/36忽略；examples测试37通过/1忽略。日志位于忽略目录`target/curry-option-validation-tests/verification-20261023/`，Cargo目标目录隔离于`target/curry-option-validation-tests/cargo-target/`。真实资产opt-in、doctor及48手评估未运行。

冻结构建记录状态`recorded`，源码前后身份均为`29205c8ef0b98b07b3003a64baa6c7dede5e03391cf7e245b59905e0b2341028`（494文件），构建身份`5dc12ce4742ed5fb2364b8d8c51aed7bb95dd098734ee95e304f90a799d4fb88`，构建记录SHA256 `9bef7b74baac4a502ad94b1296ade61a081c233f027963329dc22b102ad17626`；`reproducible_build_proven=false`。CLI、专用runner、worker副本SHA256分别为`00395cd2e209746ba7295d07782fd64ce635a960273c511469e0b0a89959e089`、`57e119a1232b91dd57d13a5803475398589d2a801cc95ea27790a813326ed85f`、`087fe574ac8d21a10befdbdad9ccfbc871805e643b6669e3fab520c8eb7fcb6d`，均与构建记录一致；源码归档SHA256 `d8b31b838f0b559adc513159a2e8135fd6ecaf2fab0c42897e3f8ebd6fc99582`，文件清单SHA256 `4c64d44dba562aa9f1ac8d133d63f56b9b0b6e4d02a826e144767477116cf04b`。

只读核验最新天玑验收和delivery锚点匹配（SHA256分别`242e0f5e1839f132d5b091963ba9917691536ae0913e7beeca6fc62635d7f4f9`、`7c46a4a790c56dea2daf77478c5a33654ee20bb3bd3179bdfb57ebf74cc21061`），历史9份账本累计32次、未知0，518项保护材料未变。prepare-only先冻结来源、归档和候选配置，在首次候选资产扫描前写入窗口`started_at=1792771619`，双资产身份采集完成；manifest绑定普通资产身份`77d671fd2b48bdb230bbebb8445f5dce11d6958ec0f86577355a6810ad8de462`、构建、源码与请求。静态准备仍是`prompt-14-curry-v1`且`execution_ready=false`。

runner只读预检`--preflight-only --trace-stderr`返回码2；stderr原始字节SHA256 `a3b70cf9e917d6791789e9f3933c92cf6d5ba9bf9c62c02f056bc5c8533f0672`（273字节，含输入验证和共享预检阶段追踪），stdout 0字节，SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。保存的`prepared.json`为`prepared=false,execution_ready=false,native_calls=0`，summary为失败，收费账本未创建。代码核对显示Rust校验把`request.versions.engine_sha256=446f26df…`（冻结资产`roles.dll.sha256`）与`roles.worker.sha256=087fe574…`比较，导致共享预检拒绝；这不是观测到的资产变动。未构造引擎适配器或启动worker。窗口不可重置，本批7个未消费槽位封存；累计消费仍32次，未知0。Curry选项0/1、LP变化及独立重放均未取得证据；四项资格保持false。所有进程输出、输入、report及源码归档均位于忽略目录`data/runtime/p1-curry-option-validation-native-2026-10-23/`。

## 2026-10-23 天玑完整路径定向验真：六阶段通过，累计32次

按[本批断点](superpowers/plans/2026-10-23-tenki-placement-validation-handoff.md)完成独立scope `tenki-placement-validation-v1`，窗口起点`1792739271`（2026-10-23 15:07:51 +08:00），上限6次/7200秒。stage1验证己方opcode18及五个区域响应；stage2按坐标`player=0/location=8/sequence=0`接受`[0,8,0]`并到达描述`59877851398144`的opcode13；stage3选择false到下一idle、stage4独立重放一致；stage5选择true到opcode15并保留两个`69247929`位置、stage6独立重放一致。六个阶段的目标、响应oracle、单一合法自动动作、资产不变和窗口结果时点均通过。stage1/2是提示发现，不赋予重放资格；本批没有选择检索对象。

`research/summary.json`为`successful=true`，六次全部完成，历史26、本批6、累计32、未知0；保存账本`research/calls.jsonl`为32行、12,968字节，SHA256 `4244d92bd17413861bc92d4618803bc647dd05cab074189e678be8429f89971c`。独立重算新账本32条哈希链记录通过；19个checkpoint、6个begin、6个complete，29个blob及31个引用内容哈希一致。summary SHA256 `9b250b347a9f05c3eef8d321f6eba259d389d0cb1a9f4c1db0a84b205b8eee49`。随后使用同一保存runner执行`--verify-only`，报告`valid=true,native_calls=0`，verification SHA256 `836ef6447087290496ec9ef1a6e6f6492b1859b526099f3cc45b83bddfafd669`；没有补发请求。六阶段收据SHA256按顺序为`064fac05682b1974e3c93499df5542503d0b10913091861c734ae4b4f3cb6f9d`、`63558fa16fd9d5c07b9c8475960b1018992fc788a60e72a173bb0d7981c45374`、`0d077d70a00877c462ab60accc5092d95a722aa015104d5b3d2ea806f344eb17`、`aa15c7e6166c60bad762d3705cb71c2d7afd6679057ecfbd7855c0e1571368db`、`405a1ed9cb12778ad70afbeeb336ae983531a6e114ecdb9a34f2ed5e4216cd00`、`074de016f0eb0a70d56cf4cbb6fcf2c535330050eb00b8cd3bca4764e08849f1`；只有stage4、6为独立重放并匹配。总窗口从创建到stage6收据时点约22分18秒，低于7200秒。

测试通过：Python顶层测试文件列表`py -m pytest -p no:cacheprovider -rs -q @testFiles`，319通过、7跳过、71子测试通过，156.69秒。7项跳过为：v3报告、v4报告、本机引擎ABI、快照/报告、本机v2报告、完整策略报告及赛事2026独立资产配置（均opt-in）。Rust `cargo fmt --all -- --check`和workspace全目标Clippy（隔离`CARGO_TARGET_DIR`，offline/locked，`-D warnings`）通过；workspace `--all-targets`串行测试合计342通过、0失败、36忽略、84个测试目标；另行跑workspace examples测试33通过、0忽略。36个Rust忽略项均为显式opt-in用例，涉及真实冻结资产、收费原生案例、人工基准或本机报告；声明及原因保存在忽略目录`target/rust-ignored-tests.txt`。Python曾有递归收集尝试因本地ACL保护的临时目录报访问错误；最终通过的运行显式收集顶层`tests/test_*.py`，没有修改权限、删除或绕过受限目录。文档后独立构建与交付记录保存在忽略目录`final-build/`。真实资产opt-in、doctor和48手评估未运行。

原生时点源码身份`e9538276391f0e08bfa707534aeab6c8e663784da8fcd9a97dc5ea0e9eb6e8f0`、683文件；构建记录identity `00109bb132b00a61ff4330db8d950bb9b395ef82e94f89d53a27d6f3b2401886`，状态`recorded`，`reproducible_build_proven=false`。隔离runner、worker、CLI SHA256依次为`60fb6b9b531d1f1166fbb51a009a507f61c06534cf90a14d308607e8a5dcc035`、`905ec0d590755565c74b7c8bd60919474174e0614e96b81b4880555f57a5fb03`、`ef663c1ea863f22bdb11e0b1c1a9157f750eb3021b2fc27dc1e3769ece2b9796`；源码归档SHA256 `8c8c5d676d34ae03161491cd0a6dcedd5cc7c47d5ed2ecabdfbf4231c6e34e7e`。文件、原始进程输出和阶段证据位于忽略目录`data/runtime/p1-tenki-placement-validation-native-2026-10-23/`。完整自动化独立审阅确认summary/verification、父链与收据相符。四项资格仍false；当前批次暂停，后续14/24、检索和终场均须单独定义范围及预算，不复用本批或旧scope。

## 2026-10-23 天玑runner输出/期限修复与只读审计：通过，新增原生0

按[本批断点](superpowers/plans/2026-10-23-tenki-runner-repair-handoff.md)完成离线修复。Rust runner将共享预检改为返回数据，由唯一输出路由在normal/stats/verify/preflight各自输出一份JSON；新增可选`--trace-stderr`固定阶段JSONL追踪，默认关闭。Python normal runner外层timeout改为原`started_at + 7200 - now`，且收费前要求时间不少于worker 30秒超时并留有严格余量；stats、verify与只读preflight不被窗口过期挡住。timeout回归覆盖慢预检、时钟倒退、恰剩30秒、窗口格式错误和超时参数传递。

总检通过：`cargo fmt --all -- --check`；workspace all-target Clippy（隔离`CARGO_TARGET_DIR`、`--target-dir`一致、offline/locked、`-D warnings`）；默认串行workspace测试300通过/36忽略；workspace examples 28通过；Python全套295通过/7跳过、156.699秒。Python七项跳过分别为v3报告、v4报告、本机引擎ABI资产、本机快照/报告、实际v2报告、完整策略报告及赛事独立资产/重放opt-in。完整日志和逐项跳过明细在忽略目录`data/runtime/p1-tenki-runner-repair-offline-2026-10-23/`。第一次全套Python发现一个旧测试仍要求confirmation账本不存在；依据固定基线将其改成校验现存账本SHA256，单项及之后完整套件均通过。真实资产opt-in、doctor、worker和48手评估未运行。

冻结stage 1输入的`audit-tenki-confirmation-runner`审计通过，审计总耗时188.068秒，其中runner共享预检阶段157.106秒。只用新隔离runner运行`--preflight-only --trace-stderr`，进程退出0；原始stdout为215字节单JSON，stderr为224字节、仅含`input_validation`和`shared_preflight`开始/结束事件。输入/请求/seal、普通资产身份、历史源码归档及8份账本/检查点保护检查均通过；报告schema和运行时校验通过，`native_calls=0`、`execution_ready=false`。历史消费26/未知0，本confirmation账本0/6；旧stage 1的`runner_timeout`明确保留，stage1–6仍未完成。

审计时源码身份`5ccaa25c19b6b53cf6759c7ebe63481a108ddc8029cdf570c25b1119633e762d`、534文件；隔离runner SHA256 `96a1ad1b0a8c3374e2ef158b7c569cf4ae1aa0daee362f08e1d47c74249ec46c`；build-record identity `23ddae17e7e417af83d0d198edc824cd2e516a02811ddd993131fd94df64da53`，runner复本哈希一致；审计源码归档SHA256 `8e0565d8ea474198e6a76d839b7b50324891128fc20ce8c0f4e2d8cc7a6f302a`。实跑报告在忽略目录`audit-report.json`，原始进程sidecar位于批根`process-diagnostics/`。报告生成后修正schema的logical role字符集，以兼容冻结历史scope名中的连字符；原始报告数据通过新schema及运行时校验，无需重跑预检。证据体积和遍历错误见`evidence-size.json`；旧confirmation交付中的`test-data/tmpl3hi9n25`仍被ACL拒绝访问，原`evidence_size_complete=false`保持不变。

最终文档后源码/归档/构建单独保存于忽略目录`final-build/`；新runner不替换worker或产品部署。旧八份账本和保护输入字节未变，累计仍26、未知0。四项证明、完整动作和原生概率资格保持false；不提交或推送Git。

## 2026-10-23 天玑placement confirmation：离线验收通过，stage 1 runner超时后停止

按[本批断点](superpowers/plans/2026-10-23-tenki-placement-confirmation-handoff.md)执行新scope`tenki-placement-confirmation-v1`，独立上限6次/7200秒。源码/合同和离线门禁通过，`--prepare-only`通过并声明新增调用0；原生阶段仅尝试一次stage 1 runner进程，随后按停止规则暂停。窗口固定起点`1792691169`，不重置、不续用剩余5槽。

正常模式诊断为`runner_timeout`，stdout 215字节、SHA256 `b91e902f0319a3abfbb90ba152d577dc8e1ac6b6b4ea7714383ee06dce57fe60`，内容形状却是`preflight_passed=true,native_calls=0,stage=1`；stderr为空。原因未确定。收费账本仅有header和零消费checkpoint，无begin，账本SHA256 `5daf512e4381803663df466575f4706f083843629ae660caf8c557ebecc8bc21`。stage1报告和summary失败，stage2–6没有运行；只读`--verify-only`返回`valid=false`、`incomplete_stage_receipts`，不执行或补发缺少阶段。由账本统计本批实际消费0、未知0；七份旧账本9/8/1/4/2/2/0保持原哈希，旧累计26，最终仍26/未知0。历史runner/worker身份及账本细节见忽略目录`data/runtime/p1-tenki-placement-confirmation-native-2026-10-22/`及断点文档。

修复后的聚焦Python测试11项通过；完整`py -m unittest discover -s tests -v`为276通过、7跳过（139.061秒）。Rust格式、workspace全目标Clippy（offline/locked，`-D warnings`）、workspace默认串行测试288通过/36忽略、adapter examples 21通过；日志为本批根目录`rust-fmt.log`、`rust-clippy.log`、`rust-tests.log`、`rust-examples.log`。七个Python跳过项均为明确opt-in资产或报告案例；详见本批忽略目录日志。真实资产opt-in、doctor、worker测试及48手评估未运行。原生时点源码身份`554891b51a1316ae68b145559930e95264e64470da6e1240969ae41ed96df133`、510份文件；构建记录identity `97bb1c490a95f079210fc5cd343003af4b35e793757be498b2e4a3ce95cc0f63`，reproducible build未证明。最终文档后源码/构建另存于`final-build/delivery.json`。普通dist、active资产及旧产物未切换；四项证明/完整性/概率标志保持false。本批不重试、不提交或推送Git。

## 2026-10-22 天玑历史锚点修复与只读预检：离线通过，新增原生0

按[本批断点](superpowers/plans/2026-10-22-tenki-placement-diagnostics-handoff.md)交付。只读基线与前批一致：HEAD `8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，未提交工作区保留；六份历史账本为9/8/1/4/2/2次，累计26、未知0；placement账本两行且消费0；365项未迁移保护文件匹配，单一worker迁移值保持`4f2b…7680`。窗口起点、七份账本共8份文件继续保持原字节。

先把布尔/数值相等问题写成失败回归：同角色和路径的重复记录中`bytes=1`与`true`、`1.0`此前会被Python相等比较误合并。改为比较规范JSON字节后，两个负例先失败、再通过；精确副本仍成功折叠。定向诊断测试12项通过、2个类型子用例通过；独立审阅确认报告合同及成功资格未放宽。完整Python套件命令为`py -m pytest -p no:cacheprovider -rs tests --ignore=tests/tmp5esbfrkg --ignore=tests/tmpue0c2a3k -q`，257项通过、7项跳过、58个子用例通过，用时119.74秒。两个被排除目录在本机拒绝遍历；七项跳过为v3报告、v4报告、冻结引擎ABI、本机快照/报告、实际v2报告、完整策略报告及赛事2026独立资产配置opt-in，逐项原因和36个Rust ignored项保存在忽略目录`verification/test-exclusions-final.json`。

Rust源文件在本次Python严格比较修复后未变，因此引用先前本批隔离目录的完整验证：`cargo fmt --all -- --check`、workspace全目标Clippy（offline/locked，`-D warnings`）通过；workspace串行测试293通过、36忽略；adapter examples 23通过。完整日志在`verification/cargo-{fmt,clippy,workspace,example}-final.log`；所有Cargo编译命令使用固定忽略`CARGO_TARGET_DIR`与相同`--target-dir`。真实资产opt-in、doctor、worker及48手评估未运行。

修复后的源码身份`7e3471035380cf1043a84b43a5b94f08d3f322c53919cb48814209bb6dac81e6`、458份文件；隔离runner SHA256 `f8cbeb4f2cc17976d23e3bbfbd6339d16506991d5d421c7804f32fc431186d56`，构建记录身份`b79668df0aca61f849d7dc5de6a6cb4db02ee845e37d8d581b53605809f863fe`。历史Python/报告原值均为`c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7606dbce5ceaf76`；原native Rust归档错误地带有66位`c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7601bbedce5ceaf76`。固定材料SHA、实际stage 1字节、修复后Rust与Python锚点相符。原历史stderr未保存，不声称恢复。

`python -m ygo_eval.research audit-tenki-placement-preflight`真实只读运行通过；9项来源/manifest/request/input/seal/ledger/资产/runner检查全部通过。预检runner退出0，模式仅`preflight_only`，stdout 215字节、stderr 0字节；原始输出及哈希已独占保存在`process-diagnostics/`。报告输入468条、证据体积155,012,220字节、审计耗时698.659秒、资产身份匹配。报告同时通过运行时校验器和`tenki-placement-diagnostics-v1` JSON Schema；固定`native_calls=0`、`execution_ready=false`，`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`均false。该runner路径在`--preflight-only`分支验证冻结stage 1后直接返回，分支位于`TenkiPlacementBatch::open`之前；没有创建/打开新收费账本，没有调用worker、FFI或普通runner。

收尾按不可变快照逐字节比对六份旧账本、placement账本和窗口起点，8/8匹配；累计仍26、未知0，placement新增消费0。当前报告`preflight-report.json`的审计源码与构建绑定正确；此前同一预检报告、旧构建记录及runner移至`verification/*-before-strict-dedupe`保留作历史，不覆盖。来源归档458个成员全部逐项哈希通过，报告不含个人绝对路径。原stage 1 `runner_failed`和六阶段原生目标未通过状态不变；不授予原生可达、响应、重放或最优性资格。文档收尾后的独立源码身份、归档及构建在忽略目录`final-build/delivery.json`记录。

## 2026-10-22 天玑v2基线迁移与六阶段验真：离线准备通过，原生阶段零消费失败

按[v2执行断点](superpowers/plans/2026-10-22-tenki-placement-native-v2-handoff.md)收尾。源码和Rust实现于原生前冻结，源码身份`ebd4d89356b32398a492d900ff9b604e7b03f072d5f24142300e19ba23bf2287`，401份文件，HEAD `8a6b2f6762131aebea6d8c0f5f61363d573f1b36`；保留工作区既有未提交更改。新增v2迁移合同只接受本批批准的共享debug worker路径及精确SHA `a384b35aff160049b3381f15bfc35e17cf373a1ada54986b8c884bde09c78c7e → 4f2b5a7c73914f07b0bce39ed01b7f74ed9c335dba329ef3a3bf1803a6db7680`。旧v1合同语义未变；worker来源仍标记未知，不补签历史构建或资格。迁移报告哈希进入新manifest输入和context；旧scope剩余4槽未使用。

原生前验证：Tenki聚焦Python测试37项通过；Python全套251项，244通过、7跳过，用时136.565秒；Rust `cargo fmt --all -- --check`和workspace全目标Clippy（隔离`CARGO_TARGET_DIR`、offline/locked、`-D warnings`）通过；workspace串行测试292通过、36忽略；adapter examples 22通过。完整日志与逐项跳过/忽略说明保存在忽略目录`data/runtime/p1-tenki-placement-native-2026-10-22/verification/`。没有运行真实资产opt-in、doctor或48手评估。共享debug worker及其他365项受保护文件在Cargo检查前后复核一致。

准备期间首次`prepare-only`因缺少标准运行时路径`data/runtime/banlist.json`而退出，未收费。只读核对活动快照与冻结案例后，在忽略目录创建与冻结banlist字节完全相同的本地验证副本，未改快照或active指针；来源记录在`verification/banlist-source.json`。随后的`prepare-only`通过并声明新增原生0，完成manifest、普通/赛事身份和不可覆盖的stage 1请求冻结；stage 1请求及seal哈希分别为`e6b111354986fc1e0237c7a001d0b7dc233af59e9653bfca6e0176a60767c53e`和`61277129f00905d5a96c007a0a568e3758ce4d8f691c2b7d3eecc87fb3b8adb3`。固定窗口起点在首次候选资产身份扫描前保存，2小时起点不重置。

六阶段常规runner仅调用一次，汇总为`runner_failed`、`stages=[]`；没有stage收据。底层runner错误文本未进入summary，故失败原因未知。账本只有header和`consumed=0`起点检查点：`calls.jsonl` 674字节，SHA256 `0c274d01a40bb1f225409346b8d2f377fe84246f5bb367672ebcf25d74760767`。仅使用匹配哈希的保存runner以只读`--stats`核实本批消费0、完成0、未知0、预留0、额度6；原生attempt验收在`verification/native-attempt.json`，summary哈希为`e466dd498a7495313b790fec075d01d676368cb73a1030f0c8bbe98399c8446d`。独立审阅复核未产生收费调用。六份旧账本保持9/8/1/4/2/2、合计26、未知0；旧原始收据未改写。365项未迁移保护文件匹配，唯一worker记录值为`4f2b…7680`。累计仍26次，legacy查询总量与本批目标查询数均未形成原生结果，不报告为0次引擎查询。

按停止门禁未重试、不回答区域18、不运行worker/doctor、不使用旧scope剩余槽；stage 1/2不具有重放资格，opcode13、false/true及两次重放未验证。四项证明/完整性/概率标志继续为false。本批工具/合同、v2迁移、隔离构建和prepare-only为离线验收成果，不能表述为六阶段原生成功。文档收尾后的源码身份、最终独立构建和归档由忽略目录`data/runtime/p1-tenki-placement-native-2026-10-22/final-build/delivery.json`绑定，不能替代原生时点产物或为本次失败补签来源。

## 2026-10-22 天玑区域18与opcode13恢复：计数兼容修复，迁移门禁拒绝

按[恢复断点](superpowers/plans/2026-10-22-tenki-placement-native-recovery-handoff.md)复核。原恢复验收把`remaining_slots_sealed`记录为整数`4`，而Python门禁错误地用`is True`比较；先新增失败测试，再改为`type(value) is int and value == 4`，拒绝布尔值、浮点数及其他计数。另增加单个worker哈希不属于精确许可对时必须拒绝的回归。聚焦测试19项通过；Python全套233项、226通过/7跳过，用时99.525秒；7项为opt-in报告、冻结引擎/资产或实际本机报告用例。`cargo fmt --all -- --check`和目标Python文件`compileall`通过。Rust生产代码未变；引用前一条使用独立`CARGO_TARGET_DIR=target/tenki-placement-offline`的全目标Clippy、workspace 292通过/36忽略及examples 22通过记录，本次不重跑。

独立只读复核发现，本计划唯一允许登记的worker变化是`a384b35a…9c78c7e`到`be6aae6e…9db9eba`，但现场`target/debug/ygo-engine-worker.exe`及Cargo依赖副本都为`4f2b5a7c73914f07b0bce39ed01b7f74ed9c335dba329ef3a3bf1803a6db7680`。完整可用目录、相邻checkout和保留源码归档未找到`be6aae…`副本。Cargo普通worker与test-harness指纹显示标准`target/debug`在2026-10-22 06:13 UTC附近有产物；记录不足以确定具体触发命令，因此不推断其来源。366项旧保护文件中365项匹配，唯一失配仍被严格门禁拒绝。`prepare-tenki-baseline-transition`返回`historical_protected_input_changed`，没有生成迁移报告。独立审阅确认正常CLI路径、迁移记录重算及阶段保护回调均不能绕过该哈希门禁。

六份旧账本哈希均匹配，消费序列9/8/1/4/2/2、累计26、未知0；本次没有运行旧runner、worker、doctor或新原生runner，也未扫描候选资产。固定新实验目录、窗口、manifest、请求及账本均未创建；新增原生0。`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`保持false。源码快照身份`674988ca4c168e44f86e037a91fcd621a759c7f58fe11e450787df71f782b776`、399文件是在本记录编辑前取得，不能当作文档收尾后的最终身份。

## 2026-10-22 天玑区域18与opcode13两分支：离线交付完成，原生前置阻断

按[实施计划](superpowers/plans/2026-10-22-tenki-placement-native.md)新增独立`TenkiPlacementBatch`/example runner、`native-tenki-placement-probe`编排、opcode18区域响应oracle及独立v1 schema。Rust收费层固定六槽顺序、用途、精确账本前缀、不可覆盖请求和父收据派生；Python从公开菜单按坐标选择`player=0/location=8/sequence=0`，不依赖菜单顺序。schema收紧成功stage字段并修复`Ok`/`Err`在`additionalProperties:false`下被错误拒绝的问题。成功、失败、未知汇总及伪造oracle/阶段/资格负例已测试。

验证结果：Python聚焦9项通过；Python全套223项、216通过、7跳过，用时102.925秒。7项跳过分别为opt-in v3报告、v4报告、本机引擎ABI资产、真实快照/报告、实际v2报告、完整策略报告、赛事资产重放。Rust使用隔离`CARGO_TARGET_DIR=target/tenki-placement-offline`：workspace串行292通过/36忽略、0失败；examples 22通过/0忽略；`cargo fmt --all -- --check`与`cargo clippy --workspace --all-targets --offline -- -D warnings`通过。Rust忽略项均依赖冻结引擎/本机资产、人工准备、pilot报告或明确opt-in；详细列表在忽略日志`target/tenki-placement-offline/workspace-test.log`。Python完整日志在`target/tenki-placement-offline/python-full.log`。真实资产opt-in、doctor、48手评估未运行。

原证据状态：六份历史账本累计26次、未知0。前一轮合同收尾的验收记录显示，匹配哈希的原生时点`prompt-probe.exe`对旧stage1/2执行`--verify-recorded`及`--stats`共4次，全部`native_calls=0`；原`calls.jsonl` SHA为`5337352e249a13eb51a5a6dd124bc2397c4402a68e99cd77c2bffc7da22392b6`。stage1仍成功，stage2仍为`unexpected_intermediate_prompt`并停在opcode18/prompt9；旧scope剩余4槽封存。本轮在受保护worker哈希门禁处停止，未再次运行旧runner。

新原生门禁发现保护清单366项只有365项匹配：`target/debug/ygo-engine-worker.exe`期望SHA `a384b35aff160049b3381f15bfc35e17cf373a1ada54986b8c884bde09c78c7e`，当前SHA `be6aae6ec2d03ae3293f2954fb84be211483bd9c5b57e4ac3b546b7239db9eba`。关联checkout、运行时副本及保存源码包中没有找到可验证原件，历史构建记录也不证明可复现来源。因此停止在创建新窗口和候选资产扫描之前：本轮未创建新scope目录、manifest、请求、账本或窗口，未运行新runner/worker/doctor；新增原生0，累计仍26次、未知0。不得用其他哈希的worker替代或重写保护清单。后续门禁和断点见[续接说明](superpowers/plans/2026-10-22-tenki-placement-native-handoff.md)。

## 2026-10-22 天玑合同兼容修复与离线收尾

按[收尾交接](superpowers/plans/2026-10-22-tenki-prompt-probe-recovery.md)恢复，暂停时源码身份`8ad8afa9a5994d0290d904ae0d069301b052ed821f1d110daa9d9aeadb624ef0`/389文件。修复前先将成功stage测试改为保留冻结请求的`catalog=""`、`banlist=""`，聚焦运行确认schema拒绝该完整成功证据；随后仅删除这两个字段的`minLength:1`。两字段仍required/string，schema v1、哈希约束和其他成功条件不变。合成成功stage覆盖空/非空四种组合、字段缺失/null/错误类型、损坏资产哈希和错误阶段；空成功及伪造成功负例继续拒绝。以暂停源码ZIP内旧schema作结构差异基准，仅这两条约束不同。

验证：聚焦合同3项通过；`PYTHONPATH=python;tests; py -m unittest discover -s tests -v`共214项、207通过、7跳过，约102.04秒。跳过原因分别为v3报告opt-in、v4报告opt-in、本机引擎ABI资产未提供、本机快照/报告opt-in、实际v2报告opt-in、完整策略报告opt-in、赛事2026配置下独立重放opt-in。Rust源码未改，本轮不重跑Rust套件；引用原生构建前已通过的workspace 288通过/36忽略及examples21通过。`cargo build --workspace --all-targets --offline --locked`在隔离既有build目录完成，6.87秒；文档冻结后的构建身份另见本批最终验收。

修复后schema通过原manifest、stage1成功、stage2失败和summary。使用原native-artifacts中的runner，以原stage输入SHA执行stage1/2的`--verify-recorded`和`--stats`，共4次零调用核验；ledger保持SHA`5337352e249a13eb51a5a6dd124bc2397c4402a68e99cd77c2bffc7da22392b6`，stage收据SHA及暂停清单不变。原5份账本24次，加本批原生2次，累计26、未知0；本轮新增原生0。旧暂停证据61项与366个保护文件均匹配。stage1仍成功；stage2仍以`unexpected_intermediate_prompt`停在opcode18区域选择/prompt9，未到13；false/true及原生重放未执行。剩余4槽封存，没有调用普通runner、worker或doctor，没有切换部署、提交或推送。

新增忽略证据位于`data/runtime/p1-tenki-probe-native-2026-10-21/recovery-2026-10-22/`；测试日志、结构复验、零调用runner输出及审阅报告均在此。原生时点runner/worker仍绑定原哈希，新构建产物单独记录，不继承原生资格。所有证明、完整动作、全局最优和原生概率资格继续为false。

## 2026-10-22 天玑六槽位批：2次后区域18停门，额度暂停待合同修复

- 按[计划](superpowers/plans/2026-10-21-tenki-prompt-probe.md)实现PromptProbeBatch、prompt-probe runner及native-prompt-probe CLI/合同。独立审阅修复完整牌组/版本绑定、手牌计数下溢、raw15坐标、事件序列/pending尾、固定路径/重复JSON键、到期零调用恢复和静态libduel来源保护。32项聚焦通过；Rust格式/Clippy通过，默认串行288通过/36忽略（187.353秒），examples21通过（5.494秒），Python214项207通过/7跳过（104.657秒墙钟），逐项忽略/跳过在本批日志清单。真实资产opt-in、doctor、48手未跑。
- 原生时点源码6a838b72…0a3da76、388文件归档，构建记录及产物副本保留。窗口先于双资产扫描持久化；重复身份采集383.016秒，prepare-only通过且未创建收费账本。跨日保持原目录/窗口，不重开。
- 实际stage1成功：prompt7己方idle、唯一天玑command5/index0响应[5,0,0,0]；stage2停在opcode18/prompt9的5个区域选项，未到13，按unexpected_intermediate_prompt停止。两次均有完整结果，资产一致，未知0；false/true及原生重放均未执行。新增2次、累计26，余4槽封存。静态operations.cpp预测的中间区域提示得到观察，不因此授予18响应资格。
- 外层交付验证随后发现成功stage schema错误要求旧catalog/banlist标签非空，实际旧请求合法标签均为空、资产内容哈希独立绑定。编排summary及两个原收据已保存；run-native.py在验证阶段异常，未生成原native-end.json，补存native-end-paused.json及native-contract-diagnostic.json。原生已停止，不为修合同重新执行。
- 原生时点runner对stage1/2 --verify-recorded均返回native_calls0；账本及原收据字节不变，stage1保留消费1前缀、当前消费2。新账本哈希5337352e…392b6；旧366保护文件及manifest静态来源复核通过。内部FFI/legacy查询计数未知。未切换部署或提交推送。
- 用户因Codex五小时额度不足5%明确要求暂停。当前仅保存暂停身份/完整源码归档/清单与精确[断点](superpowers/plans/2026-10-22-tenki-prompt-probe-handoff.md)，状态为paused_incomplete；最终schema修复、Python复验、最终构建关联与正式验收尚未完成。恢复只做离线收尾，不运行普通原生入口或使用剩余额度。证明/完整动作/概率资格均false。

## 2026-10-21 剩余提示静态准备：三个候选及命令6阻断，新增原生0

- 按[准备计划](superpowers/plans/2026-10-21-prompt-probes-offline.md)实现prepare-prompt-probes及两份独立v1合同。只读冻结Rabbit、最新线路验收、CDB/禁限、脚本清单和核心；工具只用文件系统及SQLite，不启动Git、子进程、worker或可写账本。正式输出在忽略目录`data/runtime/p1-prompt-probes-offline-2026-10-21/research-final`，完整验收及源码归档在同批根目录。
- 三候选仅替换主卡及起手85138716，保持40/3/0和seed1，同步复制主卡组的对手资源。天玑两张检索目标留在牌库；13/14描述按冻结Stringid左移20位，24的实际掩码留待未来原始提示。候选无实际prompt编号、未来worker或完整原生请求哈希，execution_ready=false；发行依据unknown，静态API不认证可达性。命令6保留首回合战斗及worker下一回合停止阻断，脚本直接符号扫描明确限域；RECOVER92/FIELD_DISABLED56缺口保留。
- 先观察缺模块、选择器浮点卡号和静态描述断言失败，再修复。独立审阅发现候选资格schema、成功绑定字段、目录事前快照、清单统一读取及忽略保护缺口，均补强；新增静态目标断言误用旧左移4位，独立手写59877851398144/60895602409472/3先失败后修复。malformed preflight类型安全及部分失败前缀保留通过。最终独立聚焦18项通过，未发现剩余可行动问题。
- 正式准备首跑70.466秒，两份schema通过，源码a170bcc2…52153f4、382文件完整归档。research-attempt1为合同补强前诊断产物，不作验收。输出覆盖退出2且原字节不变；错误来源保存失败报告退出1，两份合同均有效；伪造候选资格被拒绝。绝对路径检查通过；初次过宽探针把逻辑角色runtime/ocgcore_path误判，修为个人绝对路径检查，未更改产物。
- Rust格式及workspace全目标Clippy离线通过；独立忽略target下默认串行280通过/36忽略，examples19通过。Python200项、193通过/7跳过，unittest92.120秒、墙钟94.025秒。36个Rust忽略与7个Python跳过逐项保存在rust-and-review.json/python-counts.json；真实资产opt-in、worker、doctor和48手评估未运行。源码无Rust行为改动，不为文档收尾重复Rust检查。
- 五账本及保护文件在收尾再次核对，累计24、未知0。报告、输入哈希、最终文档时点身份/完整归档、源码差异、证据体积、总耗时及验收写入acceptance.json和delivery-checkpoint.json；无新窗口/收费账本、FFI查询、部署切换、新worker或Git提交推送。所有可达、响应接受、证明及native_probability_verified资格均false，按约暂停；见[断点](superpowers/plans/2026-10-21-prompt-probes-offline-handoff.md)。

## 2026-10-21 洗手牌后结束线路：可见历史闭合与终场衔接，新增原生0

- 按[线路计划](superpowers/plans/2026-10-21-shuffle-route-offline.md)交付audit-information-route、独立研究/报告合同与rabbit-shuffle-end-observation-v1。仅固定命令8→命令7线路，两个历史run共6视图（4决策、2研究终止）、3观察键；6条合成样本形成3个一致性分组。原4条范围缺口不改写，新报告明确完整Rabbit/赛事范围外。
- 己方动作从原始菜单、Choice、请求/已解决决策绑定并写入历史；原记录无bytes时只复算菜单响应，不补签线缆采集。4条对手提示审计留在视图外，不生成“对手不响应”公开事件。终止phase未知、历史512保留、无后继研究菜单；14×2原查询由现存纯数据runner重算通过，两个计数/效用0。新增FFI查询0、新原生0，不把离线读取称为新原生重放。
- 实跑工具时点源码cdd7727c…72a5e85f、373份文件完整归档；最终测试时点另存4a7def6a…aca8940a。文档后最终身份、完整归档及有效audit-final报告在acceptance记录。早期audit-attempt1仅作诊断，字段早于最终合同，不作为验收结果。
- 先观察模块缺失、布尔路由及报告合同负例失败，再实现复验。审阅补齐线路不完整前停止评价、私有审计持久化、输入漂移撤销终场值和晚期失败管线测试。初轮Python180项通过后，额外探针发现schema接受伪造phase/seed；收紧字段、嵌套公开声明、菜单/历史和终止语义，独立6项篡改探针拒绝。合成管线初次SQLite未关闭导致Windows清理失败，测试显式closing修正后通过。
- 独立聚焦61项通过（17.304秒）；追加管线6项通过（15.696秒），涵盖正常纯评价器、损坏/异常/非预期评价、缺少查询时零评价器调用、终止动作样本及绑定后漂移撤销。合同聚焦11项通过。实际终止动作负例保存报告并退出1，输出覆盖退出2且旧字节不变；最终合同接受成功/部分失败报告。
- 格式检查2.671秒、workspace全目标Clippy离线33.018秒通过；独立忽略target的Rust默认串行280通过/36忽略（169.646秒），examples 19通过（5.082秒）。最终Python182项、175通过/7跳过（107.590秒）；逐项名称和原因见skipped-tests-final.json。真实资产opt-in、worker、48手评估未运行；合同最后仅修改JSON/schema测试，无Rust行为变化，不重复已通过Rust检查。
- 272个保护文件及五份账本未变，累计24次、未知0。无实验窗口/收费账本、部署切换、新worker交付或Git提交/推送。证据体积、总耗时和最终保护检查据实写入acceptance.json及delivery-checkpoint.json。本批按约暂停，三项证明资格及native_probability_verified均false；见[断点](superpowers/plans/2026-10-21-shuffle-route-offline-handoff.md)。

## 2026-10-21 P1可见信息、洗手牌理想概率及动作顺序：零原生交付

- 执行[离线计划](superpowers/plans/2026-10-21-information-offline.md)，新增information-study-v1、information-audit-v1及`python -m ygo_eval.research audit-information`。输出独占保存在`data/runtime/p1-information-offline-2026-10-21`；原始外部输入仍在旧忽略目录。工具时点源码7b8458bd…90ffe0d，363份归档文件逐项哈希匹配；文档后最终身份及完整文件清单另见acceptance.json。
- 绑定冻结Rabbit case/request、规则/资产、旧空前缀、洗手牌前缀、最新洗手牌后结束、完整Rabbit及赛事报告，以及冻结核心field/duel/playerop三份静态文件。三份前缀报告各有执行/重放，总计10个视图、2个观察键。实际MAIN1来自原始phase4，未继承旧checkpoint512；未使用终场快照反推早期状态。
- 16条合成策略数据样本形成3组（policy_id＋观察键），同组精确分布一致；不同策略在相同观察上可以不同选择。有限样本通过不认证任意策略实现。受限观察通过，历史范围完整性false：保留第二idle以后2条、完整Rabbit/赛事各1条范围缺口。
- 合成独立均匀索引Fisher–Yates精确得到120个带标签排列各1/120、20种卡号顺序各1/20，两层质量1。独立排列期望及负例校验通过。Cards/Place位置与反向顺序的字节可区分；不新增生产响应，不授予反向原生合法性或等价资格。native_probability_verified固定false，真实PRNG状态、条件分布、拒绝采样与后续随机行为缺口保留。
- 测试先观察缺模块/接口、损坏元数据等失败，再实现复验。独立审查发现历史来源类别重标、损坏嵌套提示和运行时/schema不一致3类问题，修复后31项聚焦测试及6项报告篡改、3项来源探针全部通过。实际成功/失败报告均通过schema；非法响应报告保存后退出1，输出覆盖退出2，旧报告字节不变。输入/源码漂移、重复JSON键、伪造视图/来源、策略分布及顺序损坏负例已覆盖。
- `cargo fmt --all -- --check`通过（2.862秒）；独立忽略target的workspace全目标Clippy离线通过（36.533秒）；默认workspace串行280通过、36忽略（186.493秒）；examples 19通过（5.775秒）。Python全套153项、146通过/7跳过（79.557秒）。忽略/跳过的名称和原因逐项保存在skipped-tests.json；真实资产opt-in、48手评估及worker未运行。
- 237个保护文件复核一致，五份历史账本及blob未改；累计24次、未知0，新增原生0。没有新实验窗口/账本或部署切换。源码归档、报告哈希、输入/证据体积及本批总耗时在acceptance.json和delivery-checkpoint.json据实保存。所有证明资格仍false；本批按约暂停，见[断点](superpowers/plans/2026-10-21-information-offline-handoff.md)。

## 2026-10-21 独立历史核验与四次终场续办：两组通过，预算封存

按[本批计划](superpowers/plans/2026-10-21-history-followup.md)执行。HEAD仍8a6b2f6762131aebea6d8c0f5f61363d573f1b36，全部改动未提交。用户明确调整旧门禁：独立账本/结果完整性核验可作为后续消费及输入依据；旧runner来源不补签，不将独立核验称为历史重新执行。新的构建、双资产、原生及最终源码归档/验收保存在原四次交付目录的recovery-2026-10-21子目录，旧验收和阻断证据未覆盖。普通dist、原worker及active资产未切换。

新增audit-history只读Python标准库核验器和独立v1合同，核对固定验收SHA7bf14e90c46e2a6c610f47433cfbe63b6eb377c147f2646186daf75081a05cf7下的最早9次：37条链记录、18个检查点、9份恢复结果及事件块、请求和五组报告绑定。覆盖原始/归一化哈希、案例借记、收费前缀、预算、固定检查点前置条件、严格整数/重复键、精确目录清单和采集漂移。第7次单例保留，旧报告额外journal_checkpoint错误没有对应新扣费，保存为未收费后继错误哈希。报告5/6/7运行字段由封存账本重算，额外元数据来源未认证；原runner/binary来源、历史重新执行及新的原生重放资格均false。独立手写哈希夹具、损坏/重哈希负例、禁止进程stub及独占输出通过。terminal-followup新增必需historical-audit，创建意图和每组前后现场重算完整报告，不信任valid标志。

原生前检查：cargo fmt --all -- --check及workspace全目标Clippy（offline/locked、-D warnings）通过；Windows串行workspace默认集280通过/36忽略，examples19通过/0忽略。最终Python全套122发现、115通过、7跳过（70.440秒）；忽略/跳过逐项列于skipped-tests.json，未运行真实资产opt-in或48手评估。审阅38项聚焦测试通过，无未解决阻断项。一次并发编辑期间的Python尝试因source changed during capture拒绝，保留原日志；冻结后全套复跑通过，没有为通过而放宽稳定性检查。Windows私有ACL产生的新空暂存目录未影响源码或旧证据，列为证据遍历排除项。

原生时点源码b071fe7497d9cd9eb7c4bebb3a4036469f09e466a3b6dcca9e66c98f5546c63c，352文件；构建记录121638484146249c99b7d5d7ac285fc6fd8cb635d6832801374748c7c5ba96cf。先立即保存完整源码归档和五份产物，再保存唯一窗口起点、重复采集普通/赛事身份、冻结两份具体请求并prepare-only（native_calls=0）。独立terminal-followup-v1上限4次，赛事先于洗手牌后结束，worker串行30秒。历史8/1/2次另以各自保存runner的verify-recorded零调用复核，旧20次账本及保护文件未变。

实际两组均通过：赛事48项冻结决策执行/重放各一次，边界事件160、批索引154；洗手牌公开prompt7命令8及prompt9命令7执行/重放各一次，边界事件13、批索引11。上述编号由实际原始批次独立重算，未硬编码。四次均engine_verified、无错误/待提示、决策全消费、目标查询各14项完整、binding_valid=true、计数/正常效用0、phase=null；事件/处理批/原始查询/快照/决策及资产一致。共134个实际提示审计，观测opcode11/12/15/16/18/19/26；13/14/24和命令6仍未触达。完整动作、概率/信息/循环和最优性资格保持false。

本批实际新增4、完成4、未知/预留0，累计9+8+1+2+4=24。新账本SHA68b134725597f62a888dd182b25bb0fb16cb2dbfcaf5154009b2242dc4bcc473；赛事收据消费前缀2、洗手牌4。完整编排零调用恢复及保存runner的verify-recorded均通过，恢复后账本及两份收据字节不变，总计仍4，不重写第一组前缀。显式离线v2再次获得四项绑定及效用0；默认v1仍为checkpoint_not_bound_to_terminal_boundary、正常效用null。目标FFI查询56，legacy总数未知。原生结果保存点1026秒，含恢复及原生时点离线评价的阶段收尾1094秒；预算已用满，不再执行worker。

文档后另存最终构建/双资产身份及完整源码归档，最终源码和证据清单以本批acceptance.json及delivery-hash-verification.json为准。交付核对旧130份保护文件、77份blob、源码归档、原生与最终worker、原账本及新账本。仅新增两条冻结线路的终场绑定与独立重放证据，旧Rabbit资格继续绑定原产物；不提升正式v6、全卡或全局最优。按[续接断点](superpowers/plans/2026-10-21-history-followup-handoff.md)暂停，不自动提交/推送Git。


## 2026-10-20 赛事/洗手牌四次入口：离线交付，来源门禁阻断原生

源码基线HEAD仍为8a6b2f6762131aebea6d8c0f5f61363d573f1b36，工作区未提交。按[四次计划](superpowers/plans/2026-10-20-terminal-followup.md)新增terminal-followup Python入口、独立v1 manifest/pair/summary合同、Rust固定4次scope和双案例runner模式；不改核心、目标或采集合同。已有普通部署/active快照/原worker未切换。最终源码及构建身份以忽略目录p1-terminal-followup-2026-10-20/acceptance.json为准，不将文档收尾后的身份沿用为先前构建身份。

验证在新忽略build目录执行：cargo fmt --all -- --check、cargo clippy --workspace --all-targets --offline --locked -- -D warnings通过；cargo test --workspace --offline --locked -- --test-threads=1为280通过、36忽略；adapter examples为19通过、0忽略。最终Python全套98发现、91通过、7跳过（84.112秒）；跳过及忽略逐项保存在skipped-tests.json，未运行真实资产opt-in或48手评估。聚焦测试先观察缺失入口/构造器/资产助手及partial错误放行的失败，再实现通过。独立审阅覆盖来源、固定顺序、严格完整零值、父菜单篡改及收据前缀恢复，并补充对应负例。

只读核对最新Rabbit验收SHA fbd371a4f8f10166df2b501b40fc25d35df05ad2b0deffd1055559cfa30bea6a，源码基线c595aece46eda83f7e3412c01c0ea242a6885e117adffd5615ef683c1553d8fc。历史四账本9+8+1+2=20、未知0；本轮保护95文件及77 blob。历史8/1/2分别使用已记录哈希的原生时点runner带--verify-recorded通过，新增原生调用0。父公开prompt9命令7/index0/字节[7,0,0,0]与原冻结模板匹配。

**原生前置阻断：**最早9次的首次/续办原生runner预期SHA分别b6c68c92414e1fed0b46ef4d2e5c2be3a6b5aa797e0f8261481bfa90034bc4c3、b111cf5f5f015299517f80295a22c002b19efbb0c8cc685298f8d46794c3b7c7；两份原构建记录哈希已核对，本机17份research-audit候选均不匹配。旧runner使用--recover而非纯--verify-recorded，不能以当前构建替代原产物完成本计划的历史来源门禁。真实预检以old9_runner_unavailable拒绝，记录在preflight-blocked.json；不是引擎执行失败。来源门禁尚未通过，因此未运行完整prepare-only、未冻结两份新请求、未采集候选双资产、未创建窗口/新账本，4次授权未使用。累计仍20、未知0，本批目标FFI查询0，legacy查询总数未知。

build-offline及文档后的build-final分别保存，均是离线工具构建，不冒称原生时点构建。验收、源码归档、清单及[续接断点](superpowers/plans/2026-10-20-terminal-followup-handoff.md)区分工具完成和两线路原生未完成。无全局最优、完整动作、全卡或正式v6资格提升，不自动提交/推送。下一步先解决旧9次原产物和只读收据适配，不能直接运行新4次或换ID绕过。


## 2026-10-20 Rabbit终场单例两次验真交付

原生时点源码身份`1ed1abc02994bf06f755a3de450b05b4f8597c6395dda6f84d9e70fa48f37a39`，HEAD仍为8a6b2f6，工作区未提交。证据根目录`data/runtime/p1-terminal-smoke-2026-10-20/`保存build-native.json、workspace-native.json、native-source.zip/json及五份原生产物副本；文档收尾后的最终关联另存。新普通/赛事配置仅替换worker路径，原dist、原worker、active和历史18次账本/保护文件未改。

新scope为terminal-smoke-v1，硬上限2次、仅terminal-rabbit执行和独立重放。首次候选扫描前持久化新窗口，原生结果保存点为753秒；包含预检、执行/重放、结果检查、零调用恢复及原生时点离线复核的阶段收尾为880秒，均在2小时内。**实际consumed/completed2，unknown/reserved0，累计18+2=20次**。新账本SHA为`624b4843dc9cd09e07588074b2b4ecbd91737316c70e922a183f0dd9a5f137b0`。旧窗口剩余5次未续用。

| 验收项 | 执行 | 独立重放 |
|---|---|---|
| 引擎结果 | engine_verified，无错误、无待提示，20项冻结决策全部消费 | 同左 |
| 原始边界 | NEW_TURN1，事件63、批60，status2且批尾 | 与执行一致 |
| 目标查询 | 14项完整，IS_PUBLIC合法，坐标/类型/CDB/哈希一致 | 14项完整，原始查询一致 |
| 独立评价 | binding_valid=true，计数1、正常效用1 | 同左 |
| 实际响应集合审计 | 27项通过 | 27项通过 |

边界位置由原始批次独立计算，未硬编码63/60；phase保持null。运行器在执行结果、14查询、实际响应审计和重新扫描后的资产/时间全部通过后才重放。事件、处理批、查询、目标快照、已消费决策及既有语义字段比较一致，资产前/中/后检查通过。目标FFI查询共28次，legacy查询总数未统计，保持null；收费worker请求只有2次。仅这条冻结Rabbit线路获得终场绑定和重放证据，不外推为最优或完整树。

冻结源码下重开Python编排及保存runner的verify-recorded均零调用成功，账本哈希未变。原生时点和最终源码时点的纯v2报告另存；离线报告本身的来源真实性/native_replay_verified仍为false，与账本中实际独立重放资格分层记录。原失败43字节查询单独保留为历史部分查询，完整合成夹具没有冒充原生14查询证据。

验证：Rust格式检查、workspace全目标Clippy（-D warnings）、离线锁定workspace默认测试集（Windows串行）通过278项、忽略36项；example通过18项；Python unittest详细日志86项中79通过、7跳过。未运行真实资产opt-in矩阵、48手或额外查询/探针。跳过名称及原因见skipped-tests.json和原日志。独立审阅发现并修正汇总的响应审计/状态检查、旧runner及输入哈希固定、CDB/调用输入防变更、真实门禁夹具测试；无剩余阻断项后才冻结构建。预算第三次、重复/错误请求目的、到期重开、未知消费和零调用恢复均有回归，旧6/16/4096入口语义保留。

本批观察到11/15/16/18/19/26，共54项提示审计；本批未触达12/13/14/24，命令6未观察到，不删除历史其他案例已获得的证据。proof_ready、complete_action_coverage、global_optimality始终false。最终源码/构建/双资产身份、证据体积、归档和文件哈希见本机acceptance.json，续接见[本批断点](superpowers/plans/2026-10-20-terminal-smoke-handoff.md)。本批在此暂停，不自动启动赛事或洗手牌后结束的原生验证，不提交或推送Git。

## 2026-10-20 T1/T2工具与T3查询失败停止断点

原生时点完整源码身份`2bdeaa40305a768dd1fc9631b289eca906568e455be07bb788ffd8b7cf15f69a`，HEAD仍为8a6b2f6，工作区修改未提交。证据根目录`data/runtime/p1-terminal-2026-10-20/`保存原生时点构建、源码归档及五份产物副本；文档和离线修复后的最终构建另存。未切换普通dist、原worker或active，未运行doctor、全量opt-in或48手。

首次候选资产扫描前独占保存新窗口，实际包含预检的实验墙钟563秒。独立scope硬上限6次，**实际1次、completed1、unknown/reserved0，累计17+1=18次**；历史两账本及其32+31个blob保持原字节。Rabbit首次执行到达原始事件63（NEW_TURN1）、处理批60（status2且边界在批尾），但第一项目标查询解析失败。正常计数/效用为null，未独立重放；赛事和洗手牌后结束两组均未运行。资产前后身份一致。剩余5次不自动使用。

原始43字节查询包含CODE、POSITION、TYPE、额外的IS_PUBLIC以及END。冻结核心card.cpp明确无条件附加IS_PUBLIC；初版生产与独立解析器仅接受请求的三种字段，造成结果级query_failed。完整事件、批次、第一项原始查询及错误均保留，未用空快照伪装0。故障诊断、原失败pair/summary、原生源码及产物不可覆盖。两条解析路径分别离线修复可选IS_PUBLIC的精确长度/布尔/重复检查，手写反例先失败后通过；**最终worker未重新进行原生验真**。

冻结原生源码下重开编排及原runner的`--verify-recorded`均新增0次，账本哈希不变；最终只读复核继续使用保存的原生时点runner，避免用后续诊断分类更改历史收据。离线v2最终报告另存，失败结果分类execution_failed，计数/效用仍未知。旧Rabbit/赛事报告v1计数分别1/0，正常效用仍null；v2未向旧报告授予绑定资格。

交付验证命令：`cargo fmt --all -- --check`、离线锁定的workspace Clippy（全目标、-D warnings）、workspace默认测试集（`--test-threads=1`）、adapter example测试及Python unittest全套。Rust默认线程尝试两次出现Windows共享文件占用os error32，原日志保留；串行全套通过274项、忽略36项，example通过15项。最终验收发现报告schema缺少汇总分支，补充真实失败汇总的正例及消费7次/错误资格等负例后，Python最终79项中72通过、7跳过；Rust源码未因此改变。真实资产opt-in与重型压力测试的忽略项逐项保留于rust-tests-delivery.log，Python跳过名称及原因见python-tests-contract-final.log；两者另汇入skipped-tests.json，不将其视为通过。schema修正前的构建和双身份记录另存before-schema-fix文件，最终关联重新采集。

研究问题使用冻结Rabbit完整案例、请求和来源内容哈希，独立validate-problem通过候选结构检查，明确列出隐藏信息、概率、动作顺序、循环、树规模和必要动作六项阻断。来源真实性、牌组资格、完整动作和证明就绪不由声明获得。构建关联、双资产身份、实际证据体积、文件清单与最终源码身份见本机acceptance.json；续接见[终场绑定断点](superpowers/plans/2026-10-20-terminal-binding-handoff.md)。本批不授予全局最优、正式v6或全卡资格。

## 2026-10-20 S1/S2交付与S3停止断点

原生时点源码身份为`a94c197d198630d5a483a4b3f74f7a34dfeb42cf877d35196b2cd38a2ada55aa`，HEAD仍为8a6b2f6，全部修改未提交。证据根目录`data/runtime/p1-state-native-2026-10-20/`保存build-native.json、workspace-native.json、native-source.zip和native-artifacts，区别于文档收尾后的最终构建及归档。原生期间未修改源码/产物，原普通dist、target/debug worker及active未切换。

新窗口起点1792431055，在候选双资产身份扫描前独占保存；包含扫描的实际实验墙钟为804秒。新scope预算16次、计划10次，**实际8次、completed8、unknown/reserved0**。历史9次账本及32个blob保持不变，累计17次；未执行计划2次及储备6次均不自动续用。新账本SHA为`0e50a03837676b8b19a1409b9ffa06bc7798ff61254109c10025c7733a3c410b`。

| 组 | 执行/重放 | 实际响应集合（两份） | 观察验收 |
|---|---|---|---|
| Rabbit完整线路 | 均engine_verified、重放一致、资产稳定 | 27+27 | 首回合边界可观察，快照计数1，终场效用null |
| 赛事完整线路 | 均engine_verified、重放一致、隔离资产稳定 | 64+64 | 快照计数0，终场效用null |
| Rabbit空前缀 | 均decision_required、重放一致、资产稳定 | 1+1 | 实际己方idle prompt7，命令8可用 |
| 父菜单派生命令8 | 均decision_required、重放一致、资产稳定 | 2+2 | 原观察器失败并停止；后续纯离线修复复核通过，实际下一prompt9且shuffle关闭 |
| 继续派生命令7 | **未运行** | 无 | 不推断本组终场或响应资格 |

全部188个已记录提示的实际响应集合对独立oracle一致。原生仍未触达opcode13/14/24，命令6未出现；顺序、信息、概率与循环未获资格。正常终场固定checkpoint标签不能提供精确查询绑定；离线评价执行/重放均保留`checkpoint_not_bound_to_terminal_boundary`或未终止诊断，不把表侧超量存在视为结束。

**后续状态勘误（2026-10-27）：**上段是该次洗手牌终场研究的历史时点记录。之后Tenki opcode13与Mooyan Curry opcode14各自的冻结案例已有局部原生分支及独立重放；Ground Collapse opcode24仍未原生触达，当前只有静态/合成离线协议与选区准备。命令6仍未出现。该后续进展不改写当时的188条提示审计，也不扩大其覆盖结论。

实际故障是观察器错误要求完整历史仅一条己方shuffle消息：父前缀已有初始化shuffle，命令8新增一条，合计两条。原native-run退出1，summary保持successful=false并停止第五组，未自动调整线路或重试。停止后先观察新测试失败，再修复为精确父历史前缀与增量后缀检查；手牌多重集、增量消息与选项关闭均通过，两份已有结果离线复核另存shuffle-suffix-offline-recheck.json。原报告与账本未覆盖，离线修复不冒领新的原生重放或第五组资格。

原源码下实际重开四组，退出仍1但账本字节不变，新增调用0；最终又使用保留auditor逐组`--verify-recorded`核对账本不可覆盖收据、结果、实际响应审计及重放，4组通过、消费仍8。见native-resume.log和native-receipts-final.json。源码变化后不直接续跑原编排器。

最后生产变化只涉及Python离线观察器与测试；其后Python全套**66 passed、7 skipped**（73项，python-final.log）。Rust内容与原生前总检相同：默认**259 passed、36 ignored**、example **11 passed**，格式/Clippy通过。未运行的真实资产/opt-in名称及实际命令保留于verification清单；本批原生仅上述4组，未启动全量规则或48手。

最终build-final.json、workspace-final.json、acceptance.json及delivery-source.zip在文档冻结后独立生成；清单核对源码/产物/双资产、旧文件与blob、总消费、实际耗时和证据体积。S1/S2工具可用，S3第五组未完成；下一入口见[本批断点](superpowers/plans/2026-10-20-snapshot-native-handoff.md)。proof_ready、complete_action_coverage、global_optimality仍为false，不授予正式v6或全卡资格。

## 2026-10-20 S1/S2离线工具及原生前置验证

HEAD仍为8a6b2f6762131aebea6d8c0f5f61363d573f1b36，保留全部未提交修改。新证据及隔离构建目录为`data/runtime/p1-state-native-2026-10-20/`；本条只记录进入S3之前的离线验证，不预填原生成功或消费。

- 纯Rust snapshot-evaluate与Python evaluate-snapshot、独立snapshot-evaluation合同已实现。历史Rabbit快照两份均计数1，赛事两份均0；均观察到下一回合，但正常效用null，明确缺少终场查询绑定。initial报告为开发期记录，冻结后另采报告。WIN胜负平、损坏/冲突、结束后事件或prompt、仍要求决策、查询矛盾/缺失/重复位置/越界均有负例；不修改生产decoder或worker终场协议。
- NativeRegressionBatch保留旧ResearchBatch语义；独立16次/8例/2小时，执行与重放各一次，9项预算合成测试通过。时间起点从候选身份扫描前的独占文件导入并精确绑定；重开不重置。原生runner全响应审计、事前请求、公开父菜单派生、不可覆盖账本证据收据与零调用恢复已实现。
- 独立审阅修复终场状态误判、恢复只信报告、重算替代实际响应及部分消费后预检失败丢失结果等问题。新增入口的退出码和隐私诊断先红后绿。实际红绿日志保留，不将合成调用记为原生请求。
- `cargo test --workspace --offline --locked`：259 passed、0 failed、36 ignored（rust-default.log）；`cargo test -p ygo-engine-adapter --examples --offline --locked`：11 passed（examples.log）。格式及`cargo clippy --workspace --all-targets --offline --locked -- -D warnings`通过。`py -m unittest discover -s tests -v`：65 passed、7 skipped（python-all.log）。真实资产/opt-in未运行的36项Rust及7项Python完整名称列于verification-preliminary.json，不运行全量规则或48手。
- 原账本仍9次、unknown/reserved为0；before.json所列9个历史文件以及protected-blobs.json列出的32个blob哈希未变。仅生成两份候选配置，修改worker路径到隔离build；不替换普通dist、原target/debug worker或active。

后续按冻结源码及构建关联启动S3，原生实际计数、失败、墙钟、资产与交付身份另追加；完整动作、精确终场、proof_ready和global_optimality均未通过。

## 2026-10-19 P1动作修复与离线研究准备

HEAD仍为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，保留前批未提交修改；本批不提交、不启动worker、不新增原生、不刷新dist或active。实施计划见[P1离线计划](superpowers/plans/2026-10-19-p1-actions-offline.md)，候选问题见[P1_MICROCASE](P1_MICROCASE.md)。独立构建和证据根为`data/runtime/p1-actions-offline-2026-10-19/`，build子目录与既有target/debug、普通包隔离。

- M1先观察失败：手写idle标志测试及4097子集反例各失败一次，日志m1-red.log；修复后4096子集/额外取消、空集/重复卡号位置/区域组合通过，4096张强制全选不递归。命令6/7/8的8种标志组合直接核对Choice/编码，生产和oracle不共享枚举。
- 全量回归实际暴露旧派生prompt字段不一致：首轮ygo-api旧恢复3例失败，后轮紧凑capture读取1例失败；原日志rust.log/rust-final.log保留。已通过精确非空旧idle投影兼容读取修复，并补任意字段/动作/label/bytes篡改拒绝，以及新帧+旧菜单可读、旧菜单不得选择6/8的负例。历史自动响应及重建保留原记录菜单，新worker仍使用新完整菜单。没有重写夹具或历史报告。
- 最终`cargo test --workspace --offline --locked`：**250 passed、0 failed、36 ignored**，日志rust-complete.log。格式检查及`cargo clippy --workspace --all-targets --offline --locked -- -D warnings`通过，日志clippy-complete.log。research-audit example原3项离线测试通过，日志examples.log。
- Python默认全套64项：**57 passed、7 skipped**，日志python-complete.log。显式原生/opt-in项目未运行；完整跳过清单和命令收录acceptance.json关联记录，不以默认测试扩大规则资格。
- 三份冻结报告的最终离线审计为research/corpus-final.json：92帧，当前解析对oracle差异0、解析错误0；历史响应差异7、不可得28，故退出1，报告successful=false。7处为旧菜单缺失洗手牌命令8；早期Rabbit27/Phantom1帧未记录完整旧响应，不能从旧matches=true反推集合。原生来源语料仍未触达13/14/24。合成正例退出0，删除/非法位置/未知/截断/旧解析错误负例退出1，报告分别为research/synthetic-positive.json和synthetic-negative.json；合成出现不提升原生触达资格。
- P1.2候选收据research/rabbit-candidate.json绑定原frozen-cases文件及Rabbit case/request哈希；旧v1保持不变，新增研究草案目标为正常表侧超量数0–7、提前胜8/负−2/平−1。状态相关评价、终止、完整动作、顺序、随机/信息、循环、树规模及发行依据仍阻断，proof_ready=false，未实现求解器。
- 最终构建记录build-final.json、双配置重复身份workspace-final.json、报告及原账本/旧worker哈希检查见acceptance.json。当前/原生开发worker只构建到隔离目录，未启用或获得原生验收资格；普通和赛事实际配置仍绑定原冻结worker/资产。源码before/after/capture及审计器哈希须一致，后续未修改源码才发布验收清单；不声称可复现构建已证明。

原账本37条记录、9次已落盘、unknown/reserved为0；本批前后账本和三份原报告、普通dist worker及原target/debug worker哈希一致。全部历史失败保留。耗时、原生新增0、证据体积、各源码/产物/资产身份、原生未触达和下一断点详见本机acceptance及delivery-checkpoint；本批不提升全卡、中文正式数据、完整动作、最优性或正式v6资格。

## 2026-10-19 断点恢复及首批A–E验收

HEAD仍为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，本轮修改未提交。恢复时核对暂停源码归档与7次账本，无覆盖恢复。原实验窗口已到期；用户明确批准“新的2小时时间窗，仅补执行和重放2次”。追加窗口ID为`user-resume-20261019`，原起点1792381989不变，新起点1792409341；同一context和账本，base_consumed=7、additional_calls=2。

- 新增原生仅第8/9次：赛事执行与独立重放均成功，64个提示canonical比较一致，前后资产一致，unknown/reserved均0。原生证据为`data/runtime/baseline-2026-10-19/research/evidence/tournament-9-1792409563968375300-0.json`；runner当时SHA-256为`b111cf5f5f015299517f80295a22c002b19efbb0c8cc685298f8d46794c3b7c7`，关联`build-resumed-native.json`。开始至报告约223秒，含双次身份扫描；原生、失败和证据体积详见acceptance清单。累计9次，无退款或清零，旧故障全部保留。
- 独立审查发现入口在已消费执行后重开会重复提交Execution。已修复为读取原执行结果、只补剩余Replay；完整消费后零请求读取两份结果。合成预算回归覆盖7→8→重开→9和拒绝第10次；example参数/进度/不可覆盖证据3项通过。修复后实际重开同窗口，账本仍9次、replay_matches=true，恢复报告assets_unchanged=false，不冒领历史资产连续性。修复后没有新增原生消费；最终example与原生时点二进制分别记录。
- `cargo test --workspace --offline --locked`：238 passed、0 failed、36 ignored，日志`rust-resumed.log`；其后仅example重开入口修复，已单独3项回归。`cargo clippy --workspace --all-targets --offline --locked -- -D warnings`和最终格式检查通过。
- Python全套61项：54 passed、7 skipped，日志`python-resumed.log`。36项Rust及7项Python真实资产/opt-in测试未全跑，不以本批结果扩大规则资格。
- 最终构建关联为`build-delivery-final.json`，双配置重复身份为`workspace-resumed.json`；最终`acceptance.json`检查源码before/after/capture、工具链、CLI/worker/audit哈希及各JSON合同，记录实际证据体积。早先`build-resumed.json`因构建期间文档变更标为source_changed并保留，不能用作最终关联。
- 沿用已冻结的ordinary/tournament inventory-v3和language-audit-final；本轮重新解析及schema校验。全正式OCG发行分母未建立、中文语义/许可未通过、动作完整性/顺序等价/未触达opcode和搜索裁剪缺口均保留。未更新dist或active快照，未启动48手、全量规则或正式v6。

原暂停记录和失败历史如下；当前状态以TASKS为准。

## 2026-10-19 首批基线审计实现与用户要求暂停

源码HEAD为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，本轮Rust/Python、schema、来源元数据及文档修改尚未提交。用户因额度要求暂停，停在默认回归通过、原生账本无未决调用的边界；**首批整体验收尚未完成**。恢复入口见[断点交接](superpowers/plans/2026-10-19-baseline-audit-handoff.md)，不从旧计划猜下一步。

### 已运行的最终默认验证

- `cargo fmt --all -- --check`：通过。
- `cargo clippy --workspace --all-targets --offline --locked -- -D warnings`：通过，见`data/runtime/baseline-2026-10-19/clippy-delivery.log`。
- `cargo test --workspace --offline --locked`：**237 passed、0 failed、36 ignored**，见同目录`rust-delivery.log`。包含新增identity输出保护、Windows路径、同case执行/重放/重开收费等修复；未运行36项显式opt-in，不把默认通过算作完整规则认证。
- `$env:PYTHONPATH='python'; py -m unittest discover -s tests -p 'test_*.py'`：61 discovered，**54 passed、7 skipped**，见`python-full-final.log`；其后没有Python行为修改。
- `cargo test -p ygo-engine-adapter --example research-audit --offline --locked`：example安全测试1项通过，见`example-test-final.log`；后续收尾仅改CLI/identity及research同请求绑定，example文件本身未再改。恢复时最终构建前可单独复验。
- 新增schema及负例聚焦验证通过；当前ordinary/tournament清点v3和语言报告分别通过单JSON解析及相应schema。早期仅宽松schema通过的报告不替代v3。

### 已运行的数据调查

外网命令均在同次调用配置7897代理。固定mycard提交`217ae165c1886af2fc36b823fc08f9fc3ec13185`的zh-CN/zh-SC原始文件哈希和许可调查登记在`configs/language-sources-2026-10-19.json`。39卡zh-CN名称/正文逐卡与来源字节一致，但未经独立语义核对；zh-SC含义未确认，不能当作繁体。取得材料中未找到足以确认再分发的许可依据，因此qualified=false。

当前证据只采用`data/runtime/baseline-2026-10-19/data/ordinary-inventory-v3.json`、`tournament-inventory-v3.json`、`language-audit-final.json`及`data-evidence-summary-v3.json`。SHA和详细统计见断点交接。

| 输入 | CDB原始行 | 已提供发行依据 | 专用脚本字节匹配 | 脚本未知 | 脚本缺失 |
|---|---:|---:|---:|---:|---:|
| 普通冻结资产 | 13728 | 30 | 12582 | 185 | 2 |
| 赛事冻结资产 | 14759 | 39 | 13455 | 314 | 2 |

另有959/988项不需专用脚本；缺失两项均为发行身份未确认的88264978/88264979，不能外推为正式OCG缺失两张。行数不同于普通目录过滤后13665卡；以上均不证明全卡分母或动态依赖完整。提供的发行凭据已按实际字节检查，但来源语义source_verified仍false。早期alias处理误报和损坏中间JSON保留，不作为当前验收。

### 原生批：累计7次，无未知消费

同一持久账本为`data/runtime/baseline-2026-10-19/research/calls.jsonl`及`.blobs/`。原Rabbit、Phantom、赛事三组执行/独立重放各2次，共6次；Phantom仅初始提示前缀，其余既有路线可达终场。赛事后置身份采集遇到与debug worker并发构建的实际冲突，未给资产一致性结论。原第5/6次结果从账本零消费恢复，64提示canonical响应匹配；失败元数据与恢复报告都保留。

后续补验只新增第7次赛事执行，64提示、前后资产一致；Replay因重复写不可覆盖case绑定被收费前拒绝，replay_matches=false。已新增失败回归并修正：先读绑定，同hash复用、异hash拒绝；执行/重放/重开继续正常收费，不增加非法请求费用。修复后用户要求暂停，尚未补新的原生重放。

暂停时7 begin/7 complete、unknown=0、reserved=0，最后账本hash为`9f0a3685575fe149c5b7ea46d95c743ca31d4372c352541693b93d19e45c3f91`。complete仅表示结果已落盘，不是终场成功数；所有故障和消费不清零。合成预算故障测试不计入原生7次。

批次UTC起点1792381989；北京时间2026-10-19 13:52:39起拒绝新请求（留30秒worker余量），两小时截止13:53:09。暂停不改此起点；恢复若超窗，必须先处理时间窗授权，不通过新账本绕过。call limit仍4096，微案例仍最多8个、每例512。

### 暂停时尚缺

最终开发构建关联记录、双配置工作区身份实采与schema/源码/产物关联、修正后同账本赛事执行/重放两次，以及最终文档收尾验收仍待续。现存`build-before-native.json`早于最后CLI安全及重复绑定修复，不能当作最终构建证明。普通dist、active快照及冻结数据未刷新；没有正式v6、48手、全卡或最优性验收。

源码/差异/账本摘要的暂停清单与源码zip置于忽略目录`data/runtime/baseline-2026-10-19/pause/`；不包含外部资产，原始data/runtime和data/tmp证据仍须保留。没有后台任务自动续跑。

## 2026-10-19 工作树整理与文档/环境复核

源码基线（本次提交的父版本）为 `54e8e10dab05a7d94196ceebc4febf18978117e0`；验证在提交前完成，记录随本次交付固化。复核覆盖文档重构、`.gitignore` 去重和 `ApiService::placeholder_combo` 删除。该方法仓库内无调用方；正式Combo与规划版本路由未改。

- `cargo fmt --all -- --check`、`cargo clippy --workspace --all-targets --offline --locked -- -D warnings`、`git diff --check`：通过。
- `cargo test --workspace --offline --locked`：225 passed，0 failed，36 ignored；忽略项需显式冻结资产、账本报告或人工基准。
- `$env:PYTHONPATH='python'; py -m unittest discover -s tests -p 'test_*.py'`：37 discovered，30 passed，7 skipped。
- `cargo test -p ygo-engine-adapter --test live_engine --offline --locked -- --ignored --nocapture`：1项本机Rabbit真实引擎golden测试通过。
- 普通发布包和赛事开发配置 `engine doctor` 均为 `ready=true`、`abi_ok=true`、`assets_ok=true`、`issues=[]`、`smoke_ok=null`。普通目录为13,665张卡；禁限表203项、生效日2026-10-01。该目录计数不证明全正式OCG覆盖。
- 普通包CLI与现存 `target/release/ygo-cli.exe` SHA256相同（`54804730…1432a89f`）；worker与 `target/release/ygo-engine-worker.exe` SHA256相同（`ad4a5929…f37fd11c`）。哈希相同仅确认现存构建产物，不证明由当前源码干净重建。
- 全仓Markdown扫描65份、143条相对文件链接，0断链；PRODUCT_VISION中16项需求均有计划映射，P0–P8共35项未来任务。独立只读审查未发现最终全卡/全局最优门槛降级；COMBO-01阶段现统一为P5/P6，并映射至P2.2、P5.3–P5.4和P6.1。
- `.gitignore` 已移除被整目录规则覆盖的逐JSON重复项，并按构建环境、本机资产、部署产物分组；`git check-ignore -v`确认本机配置、运行/数据目录、`target/`、`dist/`和`.venv/`仍被忽略，源码和文档未被忽略。无已跟踪文件被忽略。
- `cargo machete` 未安装；未联网安装工具。此次源码清理仅删除确认无调用方的占位API。`data/runtime/`、`data/tmp/`、`dist/`和`target/`含本机资产、持久账本、部署或构建证据，未作递归清理。

本次复核没有重建部署包、重新进行规则认证、正式v6、16+32手评估或独立干净checkout验收。上述跳过项与缺口仍按TASKS跟踪。

## 2026-10-19 产品目标与路线文档交付：只读运行复核

本条对应PRODUCT_VISION、OPTIMALITY_RESEARCH和2026-10-19产品演进计划的文档交付，晚于下方“完整自检”。HEAD为 `54e8e10dab05a7d94196ceebc4febf18978117e0`；开始时已有未提交源码/文档修改，本轮仅写Markdown，不提交、不构建、不部署、不清理资产。

实际运行以下本机命令，均退出0：

```powershell
./dist/ygo-local/ygo.cmd engine doctor
./dist/ygo-local/ygo.cmd catalog status
./dist/ygo-local/ygo.cmd banlist status
Get-FileHash dist/ygo-local/ygo.exe,dist/ygo-local/ygo-engine-worker.exe,target/release/ygo-cli.exe,target/release/ygo-engine-worker.exe -Algorithm SHA256
Get-Content dist/ygo-local/build-hashes.json
$env:YGO_ENGINE_CONFIG='data/runtime/tournament-2026/engine-development.toml'
./target/debug/ygo-cli.exe engine doctor
./target/debug/ygo-cli.exe knowledge validate --knowledge knowledge/tournament-2026.knowledge.json
```

上述最后三行是独立终端调用内的赛事配置；普通包wrapper固定其自己的配置。哈希逐项核对：

| 观察 | 结果及限制 |
|---|---|
| 普通包doctor | ready/abi_ok/assets_ok=true，issues=[]，smoke_ok=null |
| 赛事开发doctor | 同样就绪，smoke_ok=null；使用独立冻结资产和debug worker，不是统一发布包 |
| 普通CLI与现存release/包内清单 | SHA256 `54804730b3a507c0143c627d5e5c61b2acc03964c9a7cda7c803b6101432a89f` 一致 |
| 普通worker与现存release/包内清单 | SHA256 `ad4a592981535144190ec44e0dd8c4aca951ec21c0206a1346961484f37fd11c` 一致 |
| 普通catalog | 13,665张，ID `catalog-1b0564fd61eec4730828fea1d48391aa1598bca3157c255454a8dcf487485d6d`；不是全正式OCG完整性证明 |
| 普通banlist | 203项，生效2026-10-01，ID `banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783`；本轮不重新核对官方逐项名单 |
| 赛事知识来源 | sources_verified=true，39卡/102规则，14潜在灰点，静态verified_ash_effects=0，complete_semantic_coverage=false |

知识身份为 `first-turn-knowledge-419cdd70cb1e3a913d80d7beabc05a153b339659f14f52578c04e4fdcf429658`。静态包声明不等于独立原生认证；下方历史记录的运行时12项指定分支/1灰点没有在本轮重认证，也没有因来源检查而提升。doctor产生ABI探针请求，不是决斗smoke，不计入未来赛事矩阵或规则认证；本轮没有进行新的规则/策略实验。

文档验收使用Python标准库内联检查：文件集合为Git跟踪Markdown与docs递归Markdown的并集（排除忽略的dist/运行目录），去除代码块后检查相对文件链接存在；将PRODUCT_VISION表格的需求编号逐项核对PROJECT_ASSESSMENT与实施计划，并核对阶段及任务状态。最终实跑：38份Markdown、95条相对文件链接均存在；16项需求无遗漏/重复，P0–P8齐全，35项未来工程任务均未勾选。该检查验证链接目标和编号映射，不代替内容审阅或证明研究可行性。`git diff --check`退出0，Git提示的既有LF/CRLF转换警告不是空白检查失败。

独立只读文档审查发现两项重要缺口，已一次修正：研究终止定义补充首回合合法提前胜/负/平及其目标评价、终止后无后继动作；新增P5.4输入牌组识别任务，明确主题/字段/玩法/互动输出、setcode事实与推断分层、混合/未知牌组验收并修正COMBO-01映射。修正后重新运行链接、16项需求/阶段/任务检查，并定向核对两项修正文字与映射，全部通过；未声称又运行了一轮独立审查。

范围检查以本轮开始时266个Git跟踪文件的内容SHA256为基线，比对收尾内容及新增路径：非Markdown变化0，删除0，HEAD未改变，新增文件仅三份目标文档。已有 `crates/ygo-api/src/lib.rs` 修改属于前次工作，其本轮前后SHA256均为 `c74dee19f8fb794a7b6bf0193272a09458f437ec74bac8734697010a11e4cd48`，不能算本轮源码改动。普通二进制的一致哈希不证明它由最新工作区干净构建；本轮未运行Rust/Python全套、真实决斗重放、v6、48手或干净checkout验收。下方225项Rust、30项Python等为前次自检证据，不能移作本轮新结果。

## 2026-10-19 完整自检、当前部署与文档重构

基线代码提交 `54e8e10`。当前工作区移除了仓库内唯一引用点的旧 `ApiService::placeholder_combo` 占位方法（未触及正式 Combo/规划版本路由）；下列 Rust 检查是在该修改之后运行。工作区保持未提交状态，报告中的历史 commit 不包含本次修改。

- `cargo fmt --all -- --check`：通过。
- `cargo clippy --workspace --all-targets --offline --locked -- -D warnings`：通过，0 warning。
- `cargo test --workspace --offline --locked`：225 passed，0 failed，36 ignored。忽略项是需显式选择冻结资产、账本报告或人工基准的 opt-in 案例。
- `$env:PYTHONPATH='python'; py -m unittest discover -s tests -p 'test_*.py'`：37 discovered，30 passed，7 skipped。
- `cargo test -p ygo-engine-adapter --test live_engine --offline --locked -- --ignored --nocapture`：1 个真实本机引擎 golden 测试通过。
- `scripts/deploy-local.ps1 -Offline -FrozenRuntime`：成功重建并更新本机 `dist/ygo-local`；catalog 13,665 张，禁限表 203 项（2026-10-01 生效）。`engine doctor` 返回 `ready=true`、ABI/资产均通过、`issues=[]`。
- 用当前部署二进制运行 `combo analyze`：Rabbit 固定五张起手得到 5 条候选、735 个前缀节点、54.398 秒墙钟预算，终止原因 `time_budget`；5 条均由当前部署包 `combo replay` 独立重放通过。评分为 heuristic，不将排名解释为全局最优。
- `target/debug/ygo-cli.exe knowledge validate --knowledge knowledge/tournament-2026.knowledge.json`（赛事隔离配置）：来源校验通过，39 张、102 条分类；`complete_semantic_coverage=false`。这不是规则验真或 v6 完成证明。
- Markdown 相对链接检查 33 个源码文档通过；`git diff --check` 通过。环境清理只做审计，没有删除本机数据、报告、账本或构建缓存。

自检分析报告保存在忽略目录 `data/runtime/self-audit-current.json`；最新本机执行文件哈希见 `dist/ygo-local/build-hashes.json`。普通发布包不包含 `knowledge/tournament-2026.knowledge.json` 与独立赛事资产，因此验证该包不等于部署了新本家规划功能。

本轮没有运行正式 v6规划或 16+32 手评估；完整语义覆盖、端到端执行续跑、第三方逐资产许可清单和独立干净 checkout 双资产验收仍未完成。

## 2026-10-18 费用支付后的运行中故障

实跑原生前缀，在Scythe已经取除1张素材、仍等待牌库对象选择的提示处注入已标记的worker退出。实际查询中宿主只剩1张素材，原始MOVE从132到16且费用位0x80成立；这些断言依据原始事件／查询和人工预期，不使用符号预测当作实际变化。已有前缀独立重放通过，但仍不是终场或恢复锚点，不能取得成功推荐或规则资格。

先复现：执行故障后审计成功的报告误入旧完整执行校验路径，读取已收费错误调用时直接失败。现在分别验证实际成功前缀、错误调用、预测、费用及完整审计。伪造素材恢复或把基础设施失败改为规则受阻均被拒绝。接口中的可注入backend只用于内部故障测试；独立查询／根重放仍固定使用ProcessEngineAdapter，正式CLI没有backend选择入口。

失败和修正两次混合试验各收费34次，每次33次Process适配器请求＋1次明确模拟的错误扣费；后者不能冒充原生规则验真。证据paid-cost-fault-1792258592406533900及paid-cost-fault-1792258871450973900保留在原pilot目录。异常开发总收费804次，其中802次Process适配器请求、2次上述模拟扣费；默认单元故障模拟不计入此账本，亦不混入矩阵比例。

新增缓存查询版本负例先复现公开字段相同即可被接受，现核对初态、查询和完整根结果的协议／运行版本。另补回归确认错误的完整结果协议原已在收费前拒绝，没有据此虚报新增修复。

最新默认Rust225通过、0失败、36忽略；格式及workspace Clippy通过（v6-paid-cost-default.log、v6-paid-cost-clippy-final.log）。当前保存的旧v1合同复核通过，不产生新引擎消费。Python未改动，最近一次默认记录仍为30通过／7跳过。完整执行续跑、其余失败分支、剩余74项资格、正式v6、48手和干净部署仍未完成。

## 2026-10-18 初始预算拒绝与计数负例

增加初始调用前的不可覆盖意图，绑定请求、方案、调用序号和历史预算。对已耗尽的同一账本再次启动，保存无实际局面／无已审计前缀的预算拒绝；新增消费为0，既有消费不变。移除意图或伪造已启动调用引用均被拒绝。该证明不借用上次失败或其他运行的局面。

计数篡改专项先复现局部v1验证器的usize加法溢出，再增加边界拒绝；v1／v2的超大起始调用和消费计数不会触发panic。新执行入口限制单组预算1..512；原有合法报告身份与读取保持不变。

最新实跑：Rust默认223通过、0失败、35忽略，格式和workspace Clippy通过（v6-startup-default.log、v6-startup-clippy.log）。保存的旧v1报告防篡改及新v2启动失败／预算拒绝／独立前缀重放通过，日志v6-counter-overflow-green.log、v6-root-budget-final.log。新原生开发、失败及重复审计18次，本轮异常账本累计736次，仍与矩阵比例分开；0消费拒绝不算实际发动或成功线路。其他执行失败分支、完整执行续跑、74项资格、正式v6、48手和干净部署仍未完成。

## 2026-10-18 独立符号前沿续跑

默认Rust223通过、0失败、35忽略，格式及workspace Clippy通过，日志data/tmp/v6-search-resume-default.log及v6-search-resume-clippy.log。Python源码与合同未改变，上一异常基础检查点的30通过／7跳过仍作为本轮Python记录。

新增三项回归：分别在1／7／33次展开后序列化恢复，与保留的旧连续算法逐项比较候选、排序、完整历史和方案ID；篡改context、游标、展开数、前沿或待排序节点时拒绝；持久账本关闭重开后恢复，收费序列及预留令牌保持一致。更换同数量的预留所有者仍会拒绝；模拟扣费后结果未保存的中断，1次未知消费保留，旧检查点不能抹去它。该扣费属于单元故障模拟，不计作原生引擎试验。

恢复校验会重算既有符号前缀，不冒充零CPU成本。完整执行的提示进度、安全续跑、调用中崩溃恢复及矩阵编排尚未接通；未重新运行原生或干净部署。本轮原生异常开发账本仍为下节718次，规则资格仍为12项／1灰点。

## 2026-10-18 异常证据基础专项（非整轮验收）

当前源码实跑：`cargo test --offline --locked --workspace` 为220通过、0失败、35忽略；Rust格式及workspace Clippy通过。Python 3.14默认37项中30通过、7项本机opt-in跳过。日志为data/tmp/v6-exception-default-final.log、v6-exception-clippy-final.log及v6-exception-python.log。未在本次重跑历史17项真实引擎全套、完整规则认证或干净部署。

新局部v2真实预算边界通过，保留最后实际提示及事前证据：

| 调用上限 | 实际收费 | 结果 |
|---:|---:|---|
| 1 | 1 | 初始局面可见，但独立见证预留不足；无已审计前缀 |
| 12 | 11 | 第2语义步骤的操作中截断，实际提示18 |
| 30 | 29 | 第5语义步骤前截断，实际提示11 |
| 70 | 69 | 第9语义步骤盖放处理中截断，实际提示18 |
| 71 | 71 | 结束处理前截断；已观察到目标，但不是终场成功 |
| 72 | 71 | 仍受新查询保守预留限制，不能提前标成功 |
| 73 | 72 | 完成结束阶段、目标验收和独立重放 |

该组324次，证据在pilot-autonomous/1792230018011645100/budget-boundaries-1792254943717317300。此前110次探索、252次失败期望的边界试验保留；后者错误地预期72上限必能完成，账本证明预留仍可能阻止最后调用，遂修正测试，不退款也不改规则。

真实worker启动失败、故障报告篡改及正常部署重放失败前缀通过：worker-failure-1792255577629251900中，原组初态1＋失败执行1＋失败审计1＝3，独立前缀重放另2，初始worker失败另1，共6次。原失败与费用不因后续前缀重放而消失。退出／超时／损坏输出错误类型及不一致查询的故障注入是默认单测，不作为原生规则资格。

旧局部v1保存报告防篡改检查通过，真实4次上限旧入口仍以3次保留已审计前缀（budget-1792255730842048500）。本轮异常开发、失败、重跑与审计共718次，依据相应新持久日志逐条汇总；全部单列，不混入未来矩阵比例。原规则1000、人工及自主试验等历史账本不清零。

新增不可覆盖的选择／预测检查点和审计意图；重算查询审计进度、收费调用、原始错误、故障阶段及已审计前缀。JSON不能取得原生凭据，修改运行时报告会失效。未支持错误证明与未知结果继续保持未认证。完整搜索续跑、全部异常分支、剩余74项规则、正式v6、48手及最终双资产干净部署仍未完成。

## 2026-10-17 调用前预算截断

真实4次预算测试通过：初始查询消耗1次；首个选择在引擎调用扣费前因必须预留独立见证而停止；已有查询和根前缀独立重放再消耗2次，总计3／4。未启动的选择单独记录为pending_choice，不伪装成已执行决策。检查点预算由持久日志在该时点的状态重建，验证器不采用报告自填余额。证据位于pilot-autonomous/1792230018011645100/budget-1792232273812117000，该3次作为预算专项单列。

尚未宣称覆盖全部处理中截断、引擎失败及完整矩阵续跑；这类缺少完整证明的局部报告仍不能取得验证资格。

## 2026-10-17 自主线路新增依赖资格

新增13个独立规则案例：Soleret通常召唤／盖放及剩余同名卡受通常召唤次数约束，Decay展示特召及无展示对象，Boots特召，Rusty连接、送墓盖放与再次发动反例，以及I:P实际素材筛选中Rusty被排除、普通暗属性怪兽仍可选的持续规则正反例。人工准备和重放28次单列；案例不读取规划器路线，不计入赛事样本。

当前26案例原生执行及首次重放共93次，独立认证审计93次通过，运行时取得12项成对规则／1项Scythe实际灰点资格；完整覆盖仍缺74项。复用此前85次已持久化结果后，本次素材规则只新增8次执行和93次审计，复用不重复扣费。

失败材料全部保留：展示对象序号断言写错、负例中的Fuwalos先打开主阶段前窗口，导致81次案例运行未通过；修复后85次案例通过，但审阅清单同名条目被覆盖，认证再次拒绝。恢复原条目后从收费检查点续跑，仅新增85次独立审计。规则开发／审计累计1000次，人工pilot153、新独立准备28、模型64、查询95、自主探索518分别列账。

当前默认Rust214通过、33忽略，格式及workspace Clippy通过；Python37项中30通过、7跳过。首批依赖有了指定分支资格，不表示其他74项规则、正式v6、48手或最终部署完成。

## 2026-10-17 实际灰响应的分支资格

新增独立 `ash_response` 原生案例类型，不将无效后的目标效果误算为正向结算。案例沿用已审阅人工Scythe准备及其原始灰响应记录，未读取规划器路线；须证明指定发动后的对方法定选择、费用前手牌坐标、弃牌费用、实际灰结算、目标无效及闭链。缺少无效事件或费用坐标不符先复现失败，修复后通过。

原12项案例用新公开查询重新执行，合并1项Scythe灰响应案例，共46次；独立原生认证审计再46次，全部通过（rule-audits/resource-ash-1792230515806355200）。运行时仍为6项成对规则资格，新增1项实际Scythe灰点资格，完整覆盖仍缺80项。资格不来自修改知识JSON或整条自主线路成功。规则开发／审计累计514次，模型64、查询95、人工153、自主518均另列；尚未获得自主线路其他新依赖的分支资格。

## 2026-10-17 局部自主灰后恢复与报告重算

两次三组原生实验均通过，分组调用72／43／55，总计每次170。冻结自主Scythe方案、实际灰后Boots恢复方案及调用账本身份一致。第二次包含逐选择事前落盘及完整本地合同重算；保存证据目录分别为pilot-autonomous/1792229220179168800和1792230018011645100。后续纯合同篡改专项先复现错误失败类别被接受，再修复并通过6种篡改检查，不新增引擎消费。

新增回归覆盖失效实例别名、新同名卡不能替代旧未知实例、必要依赖与无关未知的区别，以及冻结方案起点／限制／步骤／目标身份篡改。当前开发树默认Rust212通过、30忽略；格式、workspace Clippy通过；Python全量35项中28通过、7跳过（本机opt-in）。当前真实运行覆盖三组局部实验及逐效果定向案例，未宣称历史真实引擎整套或最终部署已重跑。

自主探索累计518次（此前178＋本轮170＋170），全部保留；人工153、查询95、模型64和规则账本分别统计。这些成本不进入未来矩阵比例。完整规则、正式v6、48手与最终双资产部署仍未完成，局部合同尚需补齐通用预算／引擎失败降级。详见FIRST_TURN_PILOT.md。

## 2026-10-17 费用前发动源与公开查询修复

灰流丽发动源回接专项先复现失败：费用移动已识别墓地实例，发动源仍为未知。现按连续原始坐标补充同一物理实例证明，保留费用前手牌位置与费用后墓地快照；期间手牌移动、洗切或抽牌阻断推断。缺失历史属性不再从终场查询补齐。费用源、手牌压缩及洗切负例均通过。

v6新增实际QUERY_IS_PUBLIC字段；v1—v5不新增该字段。冻结原始事件及决策不变，三个查询夹具重新取得实际见证并独立审计42次，旧查询保留本地诊断。trace/state/query累计95次；旧规则认证报告需要重跑，不放宽比较。

当前开发树格式、workspace Clippy和默认Rust204项通过、28项忽略；包括尚未提交的局部规划器测试，不代表本提交或正式v6已经全量验收。局部自主三组实验已运行170次（72／43／55），原方案缺素材与灰后自主Boots替代线路有独立证据；报告合同及依赖资格尚在开发，不标记完整v6或48手完成。历史人工153次、自主失败探索106次与此前自主成功72次保持单列。

## 2026-10-17 实际状态与请求绑定收口

默认Rust194通过、25忽略；格式及workspace Clippy通过。实际灰后状态构造及查询独立复核两次各7次通过，均为手工前缀的局部集成审计，不是自主恢复验收。trace39＋state14＝53次，规则422和模型64次保持单列。

新增失败复现：认证凭据缺少请求绑定、缺失素材类型被解释为明确不满足。已修复并覆盖请求／前缀篡改、未知属性、额外超量限制的作用范围及实例绑定手续。恢复状态从实际闭链主阶段查询、原始事件和独立CDB构造；未建模持续规则拒绝依赖。旧协议序列化不变。完整86规则、正式v6、48手与最终双资产部署尚未验收。


## v6同名手牌与宿主离场坐标

默认Rust185通过、24忽略；格式与workspace Clippy通过。实际执行Decayed展示另一同名卡的合法准备与重放6次，复现原实例身份丢失；修复后执行、重放及五个查询前缀审计共12次通过。新增18次全部计费，trace累计39次，规则422次和模型64次不变。身份只由实际结算中的自身特召与唯一剩余查询建立对应；多余／歧义原实例保持未知，未知槽位不参与序号减法。

同一冻结core的旧真实MOVE还证明：宿主先入墓时，随后素材MOVE的原始源坐标为144及墓地主体序号；当前重建器保留宿主关系，更新这些瞬时坐标，同时销毁前快照保留素材、入墓快照不保留素材。这是共享core消息布局回归，不是新增v6效果资格。另修正双方次数命名空间，并以失败回归覆盖原始控制者越界，不再发生数组索引崩溃。完整限制／实际规划状态与自主恢复仍待完成。

## v6逐分支资格与负例合同

默认Rust179通过、23忽略；Python默认28通过、7跳过；格式与workspace Clippy通过。持续规则不能用缺少发动选项验收，延迟正反例要求实际结束阶段及随后回合边界。已审阅案例清单固定断言内容身份，JSON状态和任意改写的案例不能授予资格。

VerifiedKnowledge仅由持久证据与新原生审计构造。新CLI案例42次，加原生认证专项首次42／审计42／重复审计42，新增168次；规则开发／审计累计422次，查询审计21次、模型审计64次仍分别列账。6项成对分支可取得运行时资格，整包仍缺80项；当前没有合法灰响应认证，实际灰点仍0。重复审计的语义资格身份相同，调用从42增长到84，不隐去重复成本。

另修正Rusty的知识操作分类：冻结Lua无弃牌费用，改为独立牌库送墓并盖放操作。知识身份变为first-turn-knowledge-419cdd70cb1e3a913d80d7beabc05a153b339659f14f52578c04e4fdcf429658；来源、覆盖清单、牌表与资产不变。12项案例用新身份重新运行，旧知识及报告留作诊断。此处仍不是v6自主决策、完整恢复状态或48手验收；历史真实引擎整套尚未在本阶段重跑。

## v6原始事件与查询见证基础

当前默认Rust171通过、23忽略；格式及workspace Clippy通过。新增17项默认回归覆盖原始解码／前缀、实例素材、抽牌、费用与无效、通常召唤／名称次数、未闭合连锁、缺失SOLVING及素材未知降级；查询审计的预留、重复收费和查询篡改另有单元断言。

真实查询审计：无干扰8次通过；灰流丽旧探针缺少当前查询字段被拒绝6次，新采实际查询更新后7次通过。共21次全部留证，旧查询保留诊断。核验的是人工前缀及实际查询，不是自主恢复或48手验收；完整限制／恢复状态、运行时认证和其余规则继续开发。Python及历史真实引擎整套本阶段尚未重跑。

## v6资源属性与素材容器补强

发现第一组对比器遗漏非怪兽等级／属性／种族／攻守，使Veil的CDB怪兽化配置可能残留在预测中。已用符合真实CDB的单位夹具及严格原生对照复现失败；现在按原卡类型转换静态查询属性，Veil未怪兽化时等级、属性、种族、攻守均按实际查询处理。比较器补查这些字段，素材实例／宿主多重集不一致时拒绝继续；普通超量使用已有超量作素材时，旧素材送墓，不能自动转移。

默认Rust154通过、21忽略，格式与workspace Clippy通过；严格原生对照18次调用通过。模型审计累计64次：旧对照40次保留为诊断，严格复现失败6次、修复后18次。逐案例／导入审计254次仍单列；均不是48手正式评估。整包语义验真、实际事件恢复与自主v6尚未完成。

## v6第一组资源转移（完整语义仍在开发）

新增独立first_turn因果状态，首批仅注册6项转移：Soleret空场手续／盖放、Veil变怪兽、Scythe超量／牌库特召、Decayed Cloak检索。记录无序剩余牌数、实例和宿主、费用后与结算后状态、同名次数及可选触发。没有调用旧v1—v5状态或更改其合同。

10项默认回归通过，包含未知等级／限制、可选触发放弃、目标耗尽、同名素材独立取除、明确失败优先于未知。Veil成为素材、取除后还原原卡属性的失败回归已修复。独立人工准备的真实对照先保存预测，再执行／重放：6步资源投影、两种素材费用分支均通过，18次调用。此前一次目标选择未对齐人工对照的失败6次及通过16次均留证，模型审计累计40次，不计入48手矩阵。

当前默认Rust152通过、21忽略；格式和workspace Clippy通过。知识原生案例阶段的Python27通过、7跳过结果仍适用，本次仅修改Rust模型和测试。资源投影比较不证明历史、次数或恢复状态正确；本阶段尚无完整事件恢复器或自主v6入口。知识包状态与实际灰点资格没有自动提升，剩余规则、完整v6闭环及48手仍待完成。

## v6原生案例合同与首批资源规则

新增知识验真8项默认测试及1项本机测试；来源包保持102项分类、86项场景内规则不删减。12个独立人工案例覆盖Soleret空场手续／盖放、Veil变怪兽、Scythe超量／牌库特召、Decayed Cloak检索六项规则的正反例。准备、发动前见证、结算与重放均由真实引擎执行。报告明确保留其余80项缺少成对案例；不授予完整知识包或规划器支持状态。

复现并修复了特殊手续与通常召唤的选项混淆、通用221触发确认码绑定，以及素材费用源区域132的断言。通用触发实验先记录预期源与效果，随后必须由实际CHAINING、SOLVING、SOLVED、CHAIN_END确认；不能当成规划器已经在提示前识别了效果编号。

当前默认Rust142通过、20忽略；Python27通过、7跳过；格式和workspace Clippy通过。真实资源案例专项通过：首次42次调用，安全续跑不增加消费，独立导入审计两轮各42次；伪造结算引用在新增引擎调用前拒绝。案例开发／失败与独立审计累计254次调用全部留证，其中旧worker协议拒绝12次、早期绑定失败也保留；不计入未来48手矩阵或目标达成比例。旧17项真实引擎整套尚未在本阶段重跑。

可移植contract夹具只用于合同负例；真实日志、查询和分块结果位于忽略的本机目录，不将contract夹具当作原生验真证据。接口与复核方法见FIRST_TURN_VERIFICATION.md。

## v6持久调用包装层（语义验真前置）

新增CallJournal／JournaledAdapter。账本独占锁、逐记录哈希链；实际调用前sync_all扣费，结果及原始事件分块按内容哈希保存。预留不计消费，续跑显式读取已完成结果；未知调用与重试分别收费。安全检查点绑定候选顺序、搜索状态、预算与已完成调用序列。写入残片先保存证据和恢复标记，再修复尾部；无法确认是否已扣费时保守记录不明消费。包装层doctor不旁路启动进程，ABI检查须经显式probe调用扣费。

新增12项集成与1项写入故障单元回归；涵盖写入失败不启动引擎、结果失败保留扣费、崩溃、身份／内容篡改、检查点与连续运行序列一致、事件去重。真实Scythe探针通过统一账本再次执行，共5次调用；作为独立审计成本，不计效果覆盖或矩阵达成比例。旧零散探索日志仍保留，不能追认其具备新包装层保障。

包装层和检查点原语已可用；完整v6搜索及48手编排尚未接入，尚不能声称整套评估可恢复。

## v6基础集成复验

缺失知识模块的编译失败已复现并修复。当前默认Rust120通过、19项按设计忽略；Python默认25通过、7跳过；格式及Clippy通过。新知识专项4默认＋1本机来源检查通过；v6 Scythe真实灰流丽、费用／素材／无效／锚点及独立重放专项1项通过。本轮尚未重跑旧17项真实引擎全量。

知识包记录102项规则、86项场景内假说和14项潜在灰点；所有场景内条目仍是curated，实际可用于已验真策略集合的条目为空。私有验真认证不能从JSON状态字段注入。新手工探针与规则包分开，不提升整包语义状态。

新增JSON使用固定LF，赛事牌表SHA256现为5533c9f0aae115e9a408a26acb6d037d38c9505c1e78970431ffc19ab92cdb88；这是同一41＋15清单的换行规范化，不是改卡。历史摘要保留为诊断，当前摘要重新记录来源／覆盖身份。固定资产组身份未变。

## 2026-10-16 原表重选与独立资产（第一阶段）

起点a2929f8；Python3.14。新来源主41＋额外15的Rust CLI合法性检查通过；官方10月207行对照无差异。冻结资产13,571文件离线重建身份相同，ABI/doctor通过。新卡人工线路48决策／160原始事件独立重放一致；不等同于86项语义验真或v6评估。

默认Python全量23项通过、7项按设计跳过，包含新增默认14项；另有opt-in真实资产1项通过并重复确认。Rust领域合规3项通过。本阶段未重新运行整套Rust／真实引擎及Python opt-in历史验收。详细来源、修正与边界见TOURNAMENT_RESELECTION.md。

探索性资产调用日志39次（含错误请求／错误前缀，没有删去失败消费），doctor1次；新增opt-in人工线路及重放两轮共4次，合计44次。这是单列的来源／部署审计成本，不计入后续矩阵成功率。doctor在日志建立前执行，另行事后登记，不能冒称全程已有持久扣费保障。正式统一账本与崩溃续跑属于第三阶段待实现项。

## 2026-10-16 赛事来源关口核验（未通过，不是v6验收）

基线88d485f。原站HTML、X官方嵌入数据与原始照片取得并核对；原始尺寸1213×911、照片SHA256及完整诊断见TOURNAMENT_SOURCE_GATE.md。照片中至少一张墓穴指名者24224830与冻结OCG2026.10表的Forbidden/0张冲突，已足以拒绝原表；其他全部卡名、数量与规则尚未完成核验。没有更换构筑或升级资产。

原始材料哈希、官方帖子元数据、冻结禁限表源哈希、CDB卡号及Forbidden条目均已检查；领域牌组合规测试3项通过。代码未改，本轮没有重复运行完整Rust、真实引擎或Python验收。下方v5通过数为上一轮历史记录，不代表v6已经实施。

## 2026-10-16 多响应点与稳健展开顺序（验收完成）

实施基线 `782eca9`；主实现 `4084477`，证据与步数边界修复 `8fef50d`，最终源码及初始化共享预算修复 `a058a81`。Windows x64、Python 3.14.7。规划、分析、运行协议v5；profile `phantom-ash-strategy-v1`，初始化 `fixed-ash-strategy-v1`。旧v1—v4身份与读取/重放路径不重算。

| 检查 | 结果 |
|---|---|
| 默认Rust workspace | 112 passed、0 failed、17 ignored |
| 真实引擎 workspace | 17 passed、0 failed；原16效果、16固定起手、14目标请求及v4灰流丽通过 |
| 最终源码受影响专项 | v5完整矩阵及篡改/预算负例通过；七类人工真实响应及步数边界再次通过 |
| fmt / Clippy | 原工作区与独立副本通过，offline、locked、warnings denied |
| Python默认 | 9 passed、6 skipped |
| Python全量合同 | 13项既有合同及2项新增合同分批全部通过；新增项读取最终真实矩阵 |
| 独立构建部署 | 全新clone、自行构建target/dist，冻结资产离线部署，doctor ready |
| 兼容重放 | Rabbit分析v2、Phantom规划v1、Break Sword规划v2、目标v3、灰流丽v4通过 |
| 重复性 | 两处v5策略/执行身份、恢复状态、资源对照、调用账本及资产哈希一致 |

完整引擎命令为 `cargo test --release --offline --locked --workspace -- --ignored --test-threads=1`。最终收尾只修改v5专用分派与证据逻辑，再运行 `-p ygo-api --test strategy` 及 `--lib seven_effects_have_actual_ash_negation_and_replayed_paid_prefixes` 的opt-in专项；默认workspace、格式及Clippy重新通过。Python使用 `PYTHONPATH=python;tests`，全量合同设置 `YGO_LIVE_ENGINE=1`。一次全量执行的新增v5项读到修复前开发报告，因缺少共享展开字段失败；重生成后 `py -m unittest test_strategy_schemas -v` 两项通过，其余13项已在该全量执行通过。未掩盖旧报告失败或将旧开发报告冒充最终验收报告。

初始化两次搜索共享8个候选、5000次展开和frontier32，实际生成7个候选、累计392次展开；在响应实验前冻结两种首敏感效果不同的方案。第二个中性发现账本expansions为累计值。每格最多512次、共8192次；完整主线最多32语义步骤，包含前缀、灰流丽与后续触发。下表调用含内部见证及必要外部独立重放；重放预留在执行后作为实际消费，不重复相加。

| 响应策略 | Scales先行：调用 / 实际结果 | Boots先行：调用 / 实际结果 |
|---|---|---|
| 始终不响应 | 178 / 达标 | 209 / 达标 |
| Scales送墓 | 241 / 实际被灰后恢复达标 | 79 / 未到响应点，终场达标 |
| Boots检索 | 76 / 未到响应点，终场达标 | 150 / 实际被灰后恢复达标 |
| Cloak检索 | 281 / 实际被灰后恢复达标 | 79 / 未到响应点，终场达标 |
| Gloves送墓 | 76 / 未到响应点，终场达标 | 79 / 未到响应点，终场达标 |
| Rusty送墓盖放 | 76 / 实际被灰后恢复达标 | 31 / 实际被灰，已验证终场未达标 |
| 增援检索 | 76 / 未到响应点，终场达标 | 79 / 未到响应点，终场达标 |
| 愚埋送墓 | 76 / 未到响应点，终场达标 | 79 / 未到响应点，终场达标 |
| 合计 | 1080 | 785 |

矩阵总额 **1865 / 8192**。未到响应点不记作成功抗灰。Boots先行的无干扰主终场资源较多，但Rusty被灰后本次搜索未找到达成原目标的恢复；因此最坏结果优先排序仍选择Scales参照策略。未达标终场是有界探索的实际结果，不证明全局无解，也不声称顺序一定严格改进。原起手不可触达的增援、愚埋等，用独立合法五张定向起手补充七类真实响应验真，不当作随机起手统计。

失败复现与修复：愚埋冻结Lua实际描述编号；Greaves手牌触发源绑定；只剩结束回合时遗漏合法恢复窗口；软一次应绑定发动时登场批次；成功锚点须绑定完整运行身份；失败结算诊断不得冒充已验证证据；否定和发动/后续探针损失必须使用已验证真值；已结算前缀超步数必须返回预算诊断。步数边界先以实际引擎窗口复现失败，再修复通过。初始化核对发现原两个搜索累计11候选，收紧至共享8候选后重新生成并比较两处报告。素材与Break Sword复活限制原始事件夹具来自真实v3准备，仅测试同一原始帧在v5重建下的解释，不冒充v5场景重放。

独立副本 `../ash-strategy-clean-20261016` 只复制冻结数据、脚本、DLL及禁限表源，未复制target、dist、本机配置或快照；自行导入快照、生成副本路径配置。最终v5报告与原工作区比较：两行策略ID、逐格执行及锚点ID、实际状态、资源对照、目标评估和账本一致。复核结果保存于忽略的 `data/runtime/ash-strategy-acceptance.json`，完整报告为 `data/runtime/ash-strategy-report.json`；运行材料和外部资产不提交。

冻结资产SHA256（两处一致）：

- CDB：`c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225`
- Lua清单：`69bf6f9d3fe444fd53890c60bde877f97b753f8d3e218a6349615d09f6740d91`
- core DLL：`446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9`
- 禁限表：`e85912d33eaada6817477c3a8fac0ef0c3e77b6ca25de924826e7f5cbc7e25ab`

## 2026-10-16 指定灰流丽中断与恢复（本轮验收完成）

实施基线 `17f0e68`，核心实现 `90c9e45`，实际资源对照 `5613116`，部署CLI重放修复 `8737af1`。Windows x64、Python 3.14.7；冻结core、Lua、CDB及禁限表未升级。新增规划/分析/运行协议v4、profile `phantom-recovery-v1`、初始化 `fixed-interruption-v1`。

| 检查 | 最终结果 |
|---|---|
| Rust默认workspace | 104 passed、0 failed、15 ignored |
| 显式真实引擎workspace | 15 passed、0 failed；原16效果、16固定起手、14目标请求及灰流丽专项通过 |
| fmt / Clippy（offline、locked、warnings denied） | 原工作区及独立副本通过 |
| Python默认 / 全量合同 | 8 passed、5 skipped / 13 passed、0 skipped |
| 人工灰后恢复基准 | 独立编写8步恢复，真实执行及重放通过 |
| 部署CLI与旧合同 | 新v4三组、旧Rabbit、Phantom v1、Break Sword v2及目标v3重放通过 |
| 独立源码部署 | `8737af1`全新checkout自行构建，冻结资产离线部署、doctor、v4及v3规划重放通过 |
| 重复性 | 两处目标/方案/推荐/执行身份、恢复锚点、资源对照与调用账本一致 |

默认测试不要求本机引擎、CDB或报告。真实引擎测试显式使用 `cargo test --release --offline --locked --workspace -- --ignored --test-threads=1`；Python全量设置 `YGO_LIVE_ENGINE=1` 和 `PYTHONPATH=python;tests`。运行报告、外部资产和本机配置继续忽略，不纳入源码。独立副本为 `../ash-recovery-clean-20261016`，只复制冻结数据资产，未复制原工作区target、dist或本机引擎配置；部署生成副本自己的worker和配置。

固定起手、seed=1、每组512次调用、最多8候选、32步、5000展开。以下数字包括外部独立重放；账本中的预留在重放后成为实际调用，不重复相加。

| 组别 | 成功推荐 | 执行及内部见证调用 | 外部重放 | 总额 |
|---|---:|---:|---:|---:|
| 对方持灰但不响应 | 5 | 249 | 41 | 290 |
| 原方案被灰阻断 | 0（合法前缀） | 6 | 1 | 7 |
| 实际状态恢复 | 5 | 222 | 38 | 260 |
| 合计 | 10 | 477 | 80 | 557 / 1536 |

基准与恢复的符号展开分别171与95。恢复首推经过Boots特召、Cherubini连接、Boots除外检索、Scales触发复活、Rusty连接及送墓盖Fog，达成原目标。此处只报告本次有界搜索实际验证的结果，不以墙钟变化证明性能改善，不将恢复路线与基准终场差额当作手坑导致的全部损失。

真实事件确认Scales弃牌和灰流丽费用仍支付；Scales的牌库送墓没有发生，Cloak仍留在牌库；效果次数、通常召唤机会不重置。被无效的连锁单独记为effect_negated，不生成成功结算历史。人工Cherubini案例由引擎完成准备与费用送墓，检查对应窗口不存在灰流丽合法动作。相同Ryu-Ran分别留手与被弃，绑定不同实例。未到响应点、错误窗口、覆盖不足和预算截断保留明确失败分类；未知状态不用于证明恢复可行。

失败复现与修复：旧worker不能读取v4字段；严格历史检查暴露手牌源先CHAINING、后费用MOVE的绑定顺序；复审发现受阻Attempt可伪标成功、前缀步数硬编码、恢复组可换请求/知识/预算。最后部署CLI检查复现v4 plan-replay落入旧合同解析，补入口失败回归后修正分派。资源对照按实际窗口见证重算；改选解释只归因于原路线缺少资源，避免错误指向紧接着的下一步。篡改状态、费用历史、前缀、预算、预测、数量差及验证标志由合同或独立重放拒绝。

冻结资产SHA256（两处一致）：

- CDB：`c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225`
- Lua manifest：`69bf6f9d3fe444fd53890c60bde877f97b753f8d3e218a6349615d09f6740d91`
- core DLL：`446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9`

身份及资产逐项比较另存 `data/runtime/ash-acceptance/cross-checkout.json`。最终文档提交继续在独立副本离线部署并重放新旧报告。

证据报告为 `data/runtime/ash-recovery-report-final.json`，独立重放及检查日志在 `data/runtime/ash-acceptance/`；人工基准为 `data/runtime/ash-manual-recovery.json`。恢复锚点限于早期第一次Scales送墓与灰流丽连锁；已有其他效果连锁、素材锚点或不完整身份时返回覆盖不足。不声称任意手坑恢复或全局无解，后续先设计同一手坑的不同时点及展开顺序。

## 2026-10-15 通用目标 v3：证据修复与最终验收

实现提交 `dd13057`；证据修复 `8b6d047`、费用后采样修复 `363fa41`、最终发动源区域修复 `2e1e781`。Windows x64、Python 3.14.7；冻结 core、Lua、CDB及禁限表未升级。规划请求/报告v3、分析v3及运行协议v3保持不变，规划 profile 为 `phantom-goal-v2`。

| 最终源码检查 | 原工作区及独立干净副本结果 |
|---|---|
| Rust默认 workspace | 98 passed、0 failed、13 ignored |
| 显式本机资产/真实引擎 workspace | 13 passed、0 failed |
| fmt / Clippy（offline、locked、warnings denied） | 通过 |
| Python默认 | 11项：7 passed、4 skipped（本机报告/资产） |
| Python全量 | 11 passed、0 skipped |
| 原效果与固定起手 | 16个效果正反例、16个固定起手及独立重放通过 |
| 新目标矩阵 | 14个请求、成功推荐及其前缀/辅助分支独立重放通过 |
| 部署包CLI | doctor、知识来源校验、新目标/收益/历史规划与重放通过 |
| 旧版兼容 | 重新生成v2 Break Sword并重放；既有Rabbit、Phantom v1报告重放通过 |
| 评分配置 | v2/v3分别验证默认、环境变量、显式参数；实际权重和诊断分数改变，重放通过 |
| Rabbit固定512节点复验 | seed=1、512节点、517调用、5条线路重放通过（旧beam节点预算不含最终重放） |

默认测试不要求本机引擎或卡库；opt-in测试使用相同冻结资产。独立副本在最终源码上清除旧 target、dist、快照与本机配置后重建 CLI/worker、部署、导入与 doctor；未复用原工作区构建产物。Python依赖使用已安装环境，额外设置 PYTHONPATH 指向副本/python并记录导入位置，确认全量合同检查使用副本源码、Schema和新报告。

本轮一轮只读整分支审查确认两项重要问题、一项解释问题；均先复现失败再修复。批量召唤现在按完整实例与位置缓存，并在成功帧逐体提交，覆盖异名与同名两体、未完成/失败召唤和缺失身份。Boots自行特殊召唤再被Break Sword复活时计为两次；同名双Boots分别保留实例。

破坏保存MOVE前的剩余素材，送墓保存目的状态且无残留素材。独立原始事件核对进一步发现CHAINING早于费用，故在CHAINED采样费用及对象选择完成后的素材。原始帧夹具也暴露手牌魔法发动源区域错误：现在费用前绑定身份，区域取CHAINING实际位置（魔陷区），素材取CHAINED，实际结算由CHAIN_SOLVED证明。缺失必要帧、绑定或属性时保留未知。历史快照不会因后续取除、离场或重新登场而改变。

贡献与损失统一按有语义的条件节点计算，not保留自身真值；双重否定、all/any组合和未知状态有回归。OR分支失去不等于整个目标失败。伪造历史素材、条件路径、场景、等级、分支起点、收益、引用或验证状态均被合同或独立重放拒绝。CLI版本测试另外修复Windows时钟粒度造成的临时文件名并发冲突。

以下调用为固定seed=1的执行、内部见证及再次独立重放预留总额；相同请求在两个环境的目标ID、推荐ID、执行ID和调用账本逐项一致，CDB、脚本manifest与DLL哈希相同。

| 固定请求 | 完整见证推荐 | 执行及预留重放调用 | 预算 |
|---|---:|---:|---:|
| Rusty＋Fog | 6 | 436 | 512 |
| Cherubini＋Fog | 7 | 378 | 512 |
| 发动机会 | 4 | 438 | 512 |
| 消费主终场的后续收益 | 1 | 424 | 512 |
| 初态已满足 | 1 | 7 | 512 |
| 无检索对象 | 1 | 7 | 512 |
| 费用不足 | 8 | 491 | 512 |
| 同名次数已用 | 4 | 378 | 512 |
| Break Sword召唤/破坏/结算历史 | 5 | 512 | 512 |
| 未支持窗口 | 0 | 10 | 512 |
| 极小预算 | 0 | 0 | 1 |
| 预算截止保留推荐 | 1 | 118 | 128 |
| 后续步数不足 | 0 | 413 | 512 |
| 共享资源冲突 | 0 | 435 | 512 |

后续收益案例验证手牌净增1，同时披露失去Cherubini等原终场条件；没有把不同假设分支的收益相加。128调用案例保留一条完整推荐。无推荐与unknown不代表全局无解，预算/步数截断均保留已有结果。外层保留至多8个完整见证推荐；内嵌analysis的top_k只截取诊断线路，因此Cherubini外层7个推荐与top_k=5并不冲突。评分仍为heuristic，不替代目标事实与实际收益，也未用墙钟波动证明改善。

旧phantom-goal-v1本地报告明确拒绝并提示重新生成；原规划v1/v2身份及重放算法不重算。旧报告与中间修复材料仅作诊断保留。最终汇总和运行日志位于忽略的data/runtime/goal-v3-acceptance/，历史诊断位于data/runtime/goal-v3-work/；引擎、数据库、Lua、个人配置及运行报告继续不进入Git。

支持范围仍为十二卡有限语义、OCG/MR5、固定完整牌组和五张起手、无主动对手响应；Ryu-Ran为合成场景。Greaves可选增级、部分历史等级/阶级信息及其他未支持分支继续明确为缺口；有限搜索与人工基准不等于任意卡效理解或全局最优。下一阶段另行设计单次指定手坑与恢复，随后样本起手评估及构筑诊断。

## 2026-10-14 第二阶段：逐效果验真与 Break Sword v2

实现提交 `51a62a4`，审查修复提交 `ffaa1e5`。Windows x64、Python 3.14.7；复用原冻结 core、Lua、CDB、禁限表。没有升级资产，没有重新编译 ocgcore；独立 checkout 重新编译 Rust CLI/worker。本机结果不代表远程 CI。

| 本轮检查 | 结果 |
|---|---|
| Rust fmt / Clippy（offline、locked、warnings denied） | 通过 |
| 默认 Rust workspace | 67 passed、0 failed、9 ignored |
| 显式真实引擎 workspace `--ignored` | 9 passed、0 failed |
| Python 全量 `YGO_LIVE_ENGINE=1` | 9 passed、0 skipped |
| Python 默认 | 6 passed、3 skipped（本机资产/报告用例） |
| `knowledge verify` | 16个支持效果逐例通过，含结算后反例及独立重放 |
| 固定16起手 | 8个正例达标并重放；4个受限未找到方案；4个覆盖/预算降级分类正确 |
| 原生同名素材专项 | 两张 Boots 叠 Break、取除、自毁、复活并继续达标及重放通过 |
| 报告篡改 | 场景、等级、阶级、素材宿主、超量历史拒绝；嵌套 runtime/deck/stats/decisions/versions 损坏拒绝 |

默认测试不要求本机引擎/数据库。显式测试前需 `cargo build --release --workspace --offline --locked`，提供当前 worker；案例使用完整合法牌组、固定起手和实际引擎准备过程，不直接注入己方墓地、次数或召唤历史。

知识 profile：`knowledge-c2c93bf5222e30a45cb600e3b2cc120a4c83a5162d8e37ce28eef4ad3e41cc43`。12张卡、21条效果中16条支持范围内的效果有真实操作案例。符号假设、来源哈希、逐案例证据和完整线路证明分开保存。Greaves 可选增级分支仍不在规划范围；反例覆盖所列条件，不等于所有条件组合验证。

受控 Ryu-Ran 场景、无 Cherubini 额外牌组的默认请求产生8个方案、224次引擎调用、2条独立目标线路。其中完整 Break Sword 链为：

- `cb4cd1cb331628addc375d0589e44528300ca62bc8bf0cb9be214495b6444617`：超量、取除、双方破坏、自身复活触发、两体等级增加、继续做出 Rusty 并盖放 Fog。
- `4fefaaf4236ebdf1edd52fb745eed36f1cb2c1a9fa9be8b970be8be0e7b0bbe8`：直接 Rusty 路线，作为同一场景的候选对照。

再次 `plan-replay` 检查2条线路与42个去重前缀见证，共44次调用。固定起手的人工基准、规划和外部重放合计均不超过512次：正例213–303次，深度截断16次，其他无方案/覆盖/符号深度案例0次。有限搜索未找到方案不是证明无解；本轮没有用墙钟变化声称性能改善。

一次独立整分支审查发现并修复三项重要问题：同名 overlay MOVE 丢失 position、v3关键嵌套 Schema 过宽、worker异常误归为预测不符。每项均先复现失败再通过回归，修复后全量测试通过；未发起第二轮审查。预算截止导致的 timeout 与 worker 自身 timeout 也分别测试。

保留小项：v2 CLI 接受 `--scoring` 但使用默认旧诊断评分；它不改变目标/资源排序。基准步骤由实施代理手工整理、独立于规划器生成，尚无人类决斗专家策略审阅。

独立干净 checkout 在 `ffaa1e5` 上重新构建并部署，67项默认 Rust、9项显式引擎、Python9项全量、fmt/Clippy 全部通过。重新执行验真 CLI、v2规划/重放；16个效果案例、16个起手结果通过，知识 ID、两条线路 ID 与原工作区一致，CDB/脚本 manifest/DLL 哈希一致。Rabbit 固定512节点重新分析返回5条可重放线路；另外重放既有 Rabbit v2与 Phantom v1报告均通过。临时副本仅携带明确冻结前提和兼容性参考报告，没有复用原 target/dist；验收后清理。使用方法与约束见 [BREAK_SWORD_VERIFICATION.md](BREAK_SWORD_VERIFICATION.md)。详细运行报告保持在忽略的 data/runtime/，数据库、Lua、DLL、个人配置及报告均不进入 Git。

## 首版验收记录（历史）


最后复验：2026-10-14，Windows x64，Python 3.14.7。以下为实际本机与独立 checkout 结果，不代表远程 CI。2026-10-07 的 Python 依赖阻塞已解决，不再是当前阻塞。

## 源码、测试与审查

源码基线提交 `1db8cd8`；语义规划实现提交 `e43ab7594aa4e8b8d4be612e26344e6ab0b93950`。源码、锁文件、脚本、Schema、CI、文档和可分发夹具进入 Git；本机配置、数据库、Lua、DLL、快照、部署包和运行报告仍忽略。

| 检查 | 结果 |
|---|---|
| `cargo fmt --all -- --check` | 通过 |
| `cargo clippy --workspace --all-targets --offline --locked -- -D warnings` | 通过 |
| `cargo test --workspace --offline --locked` | 58 passed、0 failed、4 ignored |
| opt-in `live_engine` / `live_planner` / API `planning` | 分别 1 / 1 / 2 passed |
| Python 默认 unittest discovery | 7 项：5 passed、2 skipped |
| `YGO_LIVE_ENGINE=1` Python 全量 | 7 passed、0 skipped |
| Python 卡片夹具 validate | 2 张通过 |
| 新知识、请求及实际规划报告 Schema | 通过；缺理由、缺事前局面、伪造 outcome 三项负例拒绝 |

默认 Rust/Python 测试不携带本机资产；真实引擎和实际快照/报告检查必须显式启用。Python 环境需要项目 test extra 中的 jsonschema；本轮使用已安装依赖，未升级冻结引擎或数据。

回归覆盖：检索/送墓过滤及剩余资源、等级与阶级/连接区别、费用与效果送墓、墓地主动与事件触发、次数共享、Shade 墓地限制、素材消耗、Rusty 素材限制及复活后离场除外；同卡效果编号/实例位置、费用与对象提示、洗牌身份不确定、安全降级；v2 请求/预算/版本/验证状态和决策一致性，v1 原始选择与语义标签/事前证据绑定。

一次独立审查发现四项重要问题：预算或 worker 失败丢失未观察预测、线路重放绕过共享限额、语义标签未严格绑定实际动作、手牌洗牌位置过期。四项均先复现失败，再修复并通过回归。部分嵌套观察消息与旧 v2 Schema 较宽松这一小项保留后续处理，Rust 合同与实际重放提供更严格检查。修复后执行者复验全部检查，没有再进行第二轮审查。

## 冻结版本与独立干净 checkout

在独立目录本地 clone 实现提交，确认 tracked 工作树干净。仅准备这些明确的外部前提：冻结 `cards.cdb`、`scripts.json`、`script/`、x64 `engine/` 及固定 LFLists Git 缓存。未复制旧 target、dist、个人配置或快照。随后独立执行默认测试、格式/Clippy、`deploy-local.ps1 -Offline -FrozenRuntime`，重新生成 release CLI/worker、本机配置和数据快照。

这次验证重新编译了 Rust CLI/worker，复用了冻结 DLL；没有声称从零编译 ocgcore 或在无资产/无 Cargo 缓存的机器上完成联网安装。首次 engine 编译和联网准备前提见 [DEPLOYMENT.md](DEPLOYMENT.md)。复制尚未结束时部署拒绝缺少 manifest；资产就绪后完整重跑成功。

| 资产/检查 | 固定值或结果 |
|---|---|
| core / Lua | `38d04c9feb1a26617407091380634c87262fe3f8` / `6e22fedb74cf0c9b6656e9fce8b7331db847c605` |
| core ABI | API 11.0、x64；doctor assets_ok=true、abi_ok=true、ready=true、issues=[] |
| LFLists | `1051a65ab853fd84521aa919d1859f9468816c56`；OCG 2026-10-01 |
| catalog | 13,665 张；`catalog-1b0564fd61eec4730828fea1d48391aa1598bca3157c255454a8dcf487485d6d` |
| banlist | 203 项；`banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783` |
| knowledge | 12 张、21 条效果、14 支持；`knowledge-f6b43abb829ce5f6b25e1a77d5840604edd1afeb837b04a9bfaaf799750e4f73` |
| 独立来源校验 | CDB、脚本 manifest、DLL 哈希与原工作区一致；12 张效果正文/脚本引用校验通过 |
| 独立 engine smoke | 3 条完整重放线路；墙钟截断，只作为可用性检查 |
| Rabbit 固定 512 节点分析 | 512 节点、517 次调用、5 条线路独立 replay 通过，终止 node_budget |
| Phantom 固定 512 调用预算 | 8 个事前方案、224 次调用、2 条目标达成且独立重放线路 |
| Phantom 再次 plan-replay | 2 条线路、29 个去重前缀见证、31 次共享预算调用，通过 |

独立 checkout 的 Phantom 知识/快照及线路 ID 与原工作区相同：

- `3f2695617463042fffe688ac4eb568a63874a8f6848e3af50752d07e2fcac3d5`
- `939ce100f739993ba3831f3e45064e4d41a8b2d274d0b36c43798ca18bfc7817`

原工作区既有 Rabbit v2 报告的五条线路也再次重放通过。独立 checkout 同样通过 58 项默认 Rust、4 项 opt-in Rust 和 Python 7 项全量检查。临时 checkout 验收后清理；当前工作区运行报告保存于忽略的 `data/runtime/`。

## 固定预算对照

同一 Phantom 输入、seed=1、冻结版本和配置 node_budget=512：

| 入口 | 返回的验证线路 | Rusty 在场且 Fog 盖放 | 总引擎调用 |
|---|---:|---:|---:|
| `combo plan` | 2 | 2 | 224 |
| 旧 `combo analyze` beam | 5 | 0 | 517 |

旧 beam 的 rabbit-v1 评分没有该终场目标，且其节点预算不含最终重放；新规划预算含执行和重放。这是目标闭环能力对照，不是相同目标评分下的算法优劣证明。未把墙钟耗时波动当作性能改善。有限方案/frontier/符号展开可能遗漏有效线路，不保证全局最优。

## 复验命令

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --offline --locked -- -D warnings
cargo test --workspace --offline --locked
cargo test -p ygo-engine-adapter --test live_engine --offline --locked -- --ignored
cargo test -p ygo-planner --test live_planner --offline --locked -- --ignored
cargo test -p ygo-api --test planning --offline --locked -- --ignored
$env:PYTHONPATH='python'
py -m unittest discover -s tests -p 'test_*.py'
$env:YGO_LIVE_ENGINE='1'
py -m unittest discover -s tests -p 'test_*.py'
./scripts/deploy-local.ps1 -Offline -FrozenRuntime
./dist/ygo-local/ygo.cmd knowledge validate
./dist/ygo-local/ygo.cmd combo plan --input tests/fixtures/phantom.request.json --output data/runtime/phantom-plan-report.json
./dist/ygo-local/ygo.cmd combo plan-replay --input data/runtime/phantom-plan-report.json
```

首版范围、未支持效果及报告证据区别见 [SEMANTIC_PLANNING.md](SEMANTIC_PLANNING.md)。实际执行成功不能证明全部人工语义条目正确，固定起手验收也不代表所有合法起手、对手回合或手坑处理。

## 2026-10-24 Curry冻结输入恢复门禁与只读审计

本批新增原生调用固定为0；未创建窗口、scope或收费账本，也未运行runner、worker、FFI、doctor、真实normal、资产opt-in或48手评估。修复了prepare/normal对`base_request`与`candidate_case`哈希语义不一致的问题：manifest继续绑定规范化对象哈希，容器文件哈希单独用于原始输入保护；冻结原始案例文件有独立锚点。banlist相对路径统一按仓库根解析并拒绝越界、链接或缺失文件。normal在固定路径验证后、进入阶段循环前保存不含个人路径的拒绝诊断；保存失败则闭锁。

聚焦Python `unittest`：49项通过；最后一次定向复验：9项通过。Python完整顶层测试集（显式传入`tests/`下45个`test_*.py`文件，避免收集ACL受限临时目录）：402通过、0失败、7跳过，199.93秒。7项跳过均是显式opt-in：v3报告、v4恢复报告、本机引擎构建、实际v2报告、本机快照/报告、完整策略报告，以及需要独立2026赛事资产配置的赛事兼容回放。完整日志：`target/p1-curry-input-recovery-offline-2026-10-24-verify/python-pytest-tests.log`。

曾按默认目录发现方式运行pytest；收集阶段因现存ACL受限的`tests/tmp*`、`data/runtime`及`data/tmp`路径出现56个`PermissionError`而失败。随后显式列出顶层测试文件完成全套测试。访问失败材料保留原状，没有删除或改ACL。`git status`也报告部分pytest缓存临时目录无访问权；未尝试清理。此处记录的是可观察结果，不把ACL错误解释为测试失败。

Rust验证：`cargo fmt --all -- --check`通过；隔离target目录下workspace all-targets Clippy通过；`cargo test --workspace --offline --locked --target-dir target/p1-curry-input-recovery-offline-2026-10-24-verify/cargo-target -- --test-threads=1`汇总327通过、0失败、36忽略（87个test binary/suite）；adapter examples 44通过、0失败、1忽略。所有Rust测试都使用本地离线依赖；未运行真实资产opt-in。36项忽略全部是明确opt-in材料/引擎/收费实验：`seven_effects_have_actual_ash_negation_and_replayed_paid_prefixes`、`break_sword_full_chain_is_planned_and_replayed`、`duplicate_boots_materials_plan_and_replay`、`symbolic_break_paths`、`all_curated_effects_have_real_positive_and_negative_cases`、`fixed_hands_match_manual_baselines_and_replay`、`available_effect_and_consuming_continuation_have_separate_witnesses`、`changed_goals_change_choices_and_keep_pre_execution_evidence`、`goal_matrix_covers_history_conditions_and_safe_fallback`、`ash_interrupts_scales_and_planner_recovers_from_paid_costs`、`manual_recovery_recipe_reaches_rusty_and_set_fog_after_real_ash`、`exhausted_budget_preserves_unobserved_prediction_and_failure_report`、`planning_report_rejects_edited_knowledge_and_posthoc_reasons`、`two_distinct_strategies_have_replayed_eight_policy_evidence`、`scythe_has_actual_single_ash_cost_negation_anchor_and_independent_replay`、`rabbit_routes_replay_and_end_phase_is_settled`、`recapture_public_query_fields_without_rewriting_raw_duel_history`、`revealed_same_name_cost_does_not_swap_the_self_summoning_instance`、`captured_ash_anchor_queries_match_independent_native_replay`、`captured_queries_match_fresh_native_prefixes_and_complete_replay`、`real_costs_and_shared_search_resource_do_not_become_independent_gains`、`curated_first_turn_sources_match_actual_frozen_asset_bytes`、`prepare_normal_set_and_reveal_cases_using_only_actual_legal_prompts`、`prepare_rusty_material_filter_cases_from_the_independent_human_prefix`、`current_query_cases_and_actual_ash_response_grant_only_scoped_qualification`、`resource_cases_resolve_replay_and_resume_without_extra_charges`、`resource_predictions_are_recorded_before_native_execution_and_independently_replayed`、`a_tiny_native_budget_retains_the_audited_prefix_without_claiming_an_executed_choice`、`a_worker_failure_returns_a_v2_diagnostic_instead_of_losing_the_prefix`、`an_injected_failure_after_material_payment_keeps_a_replayable_pending_prefix`、`autonomous_generated_scythe_forecast_reaches_the_goal_and_recovers_after_ash`、`interrupted_native_operations_keep_the_latest_result_and_reserved_replay_budget`、`saved_local_reports_reject_relabelled_failures_and_anchor_or_resource_tampering`、`actual_ash_resources_usage_and_materials_drive_the_causal_state`、`independent_human_pilot_establishes_pass_and_real_ash_recovery_baselines`、`phantom_causal_plan_reaches_goal_and_independently_replays`。

真实固定材料审计只运行一次，命令为`py -B -m ygo_eval.research audit-curry-input-recovery --baseline-dir data/runtime/p1-curry-option-confirmation-native-2026-10-24 --output data/runtime/p1-curry-input-recovery-offline-2026-10-24/audit-report.json`。结果保存在忽略目录，耗时1.550518秒。acceptance、delivery和证据清单哈希锚点通过；在`source_archives`检查点失败，稳定诊断为`archived_refusal_source_hash_mismatch`。报告不能区分旧native模块哈希与research模块哈希中哪一项不符，也不能据此说ZIP本身损坏。冻结输入绑定、历史账本、旧材料保护及采集前后稳定性都标为`not_run`；本次报告中的历史统计为null。报告SHA256为`e6140724dc2048b82165a98306d970b4793cee6e4d9c46e487e98a49d6131e14`，新schema校验通过。未重试审计。

此前单独只读核验所得9份账本32次、未知0仅作为先前证据保留；本次审计未重验。旧confirmation的新增消费、累计消费和未知继续为null，七个槽位封存。历史观察中的normal退出码仍未认证；本次报告字段中预填的归档分支返回码不是本次成功核实的结果。历史Curry七阶段仍未通过。四项资格保持false。文档收尾后的工具身份、完整源码归档、文件清单、测试日志、acceptance及证据体积清单保存于忽略目录`data/runtime/p1-curry-input-recovery-offline-2026-10-24/final-delivery-after-docs/`；本地ACL受限路径未触碰。阶段摘要及恢复条件见[本批断点](superpowers/plans/2026-10-24-curry-input-recovery-handoff.md)。

## 2026-10-25 Curry父账本锁释放修复与stage 2只读验收

本批新增原生调用固定为0。修复了Curry runner normal路径持有父账本只读句柄并再次独占打开同一文件造成的Windows共享冲突。`verify_parent_request`现在在返回前释放读视图；收费前只读统计限于局部作用域。独占打开后仍通过`batch.validate_request`重新认证父收据、派生请求和收费槽位，未放宽锁或预算门禁。新增`--audit-saved-input-only`只接受verification scope的stage 2，要求prepared哈希与stderr追踪；它在账本只读视图内核验stage 1父收据、请求派生、资产身份和消费统计，然后在任何可写账本或adapter路径之前返回。normal/preflight/stats/verify的旧语义未改。

Rust红测先复现stage 1后stage 2因共享文件占用而不能独占打开；修复后生产normal分派stage 1→2合成路径通过，覆盖真实账本解析、独占收费、收据保存与父链复验。合成TOCTOU用有效账本链篡改父证据，确认独占复验拒绝且不作第二次adapter调用。另有validation、confirmation、verification三套配置的全七阶段合成执行/重放路径。只读审计复用同一个`ReadOnlyJournal`视图校验父收据和统计。独立Rust审阅确认normal路径在独占打开前释放共享view，并在writer锁内重验；audit分支不会构造adapter或进入writer。

验证结果：`cargo fmt --all -- --check`通过；`cargo clippy --workspace --all-targets --offline --locked --target-dir target/curry-ledger-handoff-rust-target -- -D warnings`通过；`cargo test --workspace --all-targets --offline --locked --target-dir target/curry-ledger-handoff-rust-target -- --test-threads=1`为380通过、0失败、37忽略（87个suite）。其中example runner测试54通过，锁句柄回归19项及stage 1→2路径包含在workspace结果内。37项忽略为仓库既有opt-in引擎/资产/原生证据测试；明细见`target/curry-ledger-handoff-rust-target/workspace-tests.log`，未运行真实资产opt-in。

Python新增固定入口`audit-curry-ledger-handoff`、独立v1报告及schema，原始进程诊断仅在进程启动后才创建。输入在runner调用前重新计算并与已认证stage 2输入哈希比对，向runner传递同一固定摘要。新增TOCTOU负例证明输入漂移时进程调用0并保存合法失败报告；运行编排测试使用私有边界stub验证诊断捕获，不替代或声称完成完整来源树验收。Python独立复审发现并确认上述哈希绑定、失败报告不变量及schema一致。全套测试明确列出`tests/`顶层64个文件，共517项，508通过、0失败、9跳过，用时686.28秒；跳过原因是两项Windows目录链接能力缺失、v3/v4报告opt-in、未提供本机引擎资产、快照/真实v2报告opt-in、完整策略报告opt-in及独立赛事配置缺失。日志、文件清单和临时材料保留于`target/curry-ledger-handoff-python-tests-final/`。冻结源码后的完整复跑通过；此前与源码编辑并行的一次全套曾因`source changed during capture`出现两项失败，已保留原日志且不作为最终验收。

测试和审阅后记录构建并保存548项源码归档。审计时源码身份为`9288335ca2fab0234489377ea1351bc651fca5b40fb6b03a25a472700b312ecc`，源码ZIP SHA256 `20ce6d7fde0a18f602c161c4a6b193795c1490eeedc138e2014e8bfa2c1fc20b`，文件清单SHA256 `713b24d41dbff9c1bf7a23f8529b0c348c28132d0645899dd328942dd215791d`。runner SHA256 `cd5f294e99aa5c44935e2ef414865a6f46fa2c8bbb5230f018d31ad606365b8d`；build-record源码前后身份一致，状态为recorded。runner仅被构建并封存，未启动。

唯一一次真实固定输入审计命令为`py -m ygo_eval.research audit-curry-ledger-handoff --baseline-dir data/runtime/p1-curry-option-verification-native-2026-10-25 --runner data/runtime/p1-curry-ledger-handoff-offline-2026-10-25/native-artifacts/curry-option-validation.exe --build-record data/runtime/p1-curry-ledger-handoff-offline-2026-10-25/build-record.json --output data/runtime/p1-curry-ledger-handoff-offline-2026-10-25/audit-report.json`，用时3.752秒，退出码1。报告SHA256 `4b3a802cb26097ec2bdf48ef59ffe56103ac87fc3b0842209feb3a7c89e0ec2e`，2,414字节，通过Python报告校验及JSON Schema。检查在`acceptance_delivery`停止，原因是审计器的整数类型检查读取了`policy_reserved`，而锚定acceptance实际字段名为`policy_reserve`；静态比对确认其余会计值与expected字典一致。此问题未被合成success夹具暴露。本次未读取历史账本/来源链后继门禁，未启动saved-input runner，`process-diagnostics/`未创建，stage 2 receipt仍缺失。报告固定`native_calls=0`、`execution_ready=false`、`new_consumed=null`、`unknown=null`、资格均false；不据此新增消费统计。

此次失败的隔离输出、构建和审计源码归档在`data/runtime/p1-curry-ledger-handoff-offline-2026-10-25/`。原scope仍消费1/7、未知0；认证子集33、规划40为原验收口径，旧confirmation与全部历史实际累计保持null。V3预留哈希保持`14c13e4992673115c0211259dd7d035d968b9c36518c28b4a4ea159ff06ad43f`。不重跑或覆盖失败审计；下一步要先为`policy_reserve`固定真实形状的回归，然后设计新的不可覆盖只读审计尝试目录/版本。完整断点见[本批断点](superpowers/plans/2026-10-25-curry-ledger-handoff-handoff.md)。
