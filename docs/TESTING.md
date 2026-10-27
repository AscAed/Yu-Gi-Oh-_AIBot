# 本机验证记录

## 2026-10-28 接续验证

- 在目录标识为`codex-ci-current-review312-20261027`的隔离干净源码副本执行Python 3.12.13顶层测试：**729 passed、24 skipped、0 failed**，1644.81秒，进程退出0；随后`python -m ygo_data.cli validate --input tests/fixtures/cards.sample.json`验证2张卡并退出0。测试输出副本为[`ci-current-review-python312.log`](../target/workspace-audit-2026-10-27-codex/ci-current-review-python312.log)，源码清单SHA-256 `9e67e38ce79935bd8c7ff8d6a773b6bcffa253264034f14be277672fdb2196eb`，共551个Git可见源文件。测试使用`PYTHONPATH=python`。与当前Git可见文件逐项比对时，成员数和路径均一致，快照后内容变化限于`docs/TESTING.md`、`docs/WORKSPACE_REVIEW.md`和`docs/superpowers/plans/2026-10-22-tenki-placement-native-recovery-handoff.md`；代码、测试、配置和schema与通过测试的快照相同。24项跳过涉及Windows目录符号链接、不可用的本机历史材料/基线，以及显式要求本机引擎、快照或赛事配置的opt-in；详情见日志。干净副本不含忽略的本机证据，因此这些跳过仍不能当作资产或历史用例验收。
- 最新工作区Rust验证：`cargo fmt --all -- --check`通过；`cargo clippy --workspace --all-targets --offline --locked -- -D warnings`通过；串行`cargo test --workspace --offline --locked -- --test-threads=1`为**331 passed、36 ignored、0 failed**；`cargo test -p ygo-engine-adapter --examples --offline --locked`为**52 passed、1 ignored、0 failed**。日志为[`final-review-rust-workspace.log`](../target/workspace-audit-2026-10-27-codex/final-review-rust-workspace.log)、[`final-review-rust-examples.log`](../target/workspace-audit-2026-10-27-codex/final-review-rust-examples.log)、`fmt.log`和`clippy.log`。
- 本次没有重建或部署最新源码包，也没有新增真实引擎实验。部署现状和旧包检查的限制仍以[工作区审计](WORKSPACE_REVIEW.md)及[部署文档](DEPLOYMENT.md)为准。

## 2026-10-27 项目环境自检与清理

在现有未提交工作区上复核，HEAD为`8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，未提交或切换部署。清理前，Ground最近交付的603个归档成员和15个带路径/大小/哈希引用均匹配，509个非Markdown成员与当时工作区一致；截至接续检查时，其中`Cargo.lock`、两个crate的`Cargo.toml`、`pyproject.toml`、`.github/workflows/ci.yml`、`scripts/deploy-local.ps1`、`python/ygo_data/identity.py`、`python/ygo_eval/native_tenki_placement.py`（仅注释）以及九个相关Python测试文件共十七项变化。归档和原报告没有改写。

- 普通发布包和赛事开发配置各运行一次`engine doctor`：均退出0，`ready`、`abi_ok`、`assets_ok`为true，`issues=[]`、`smoke_ok=null`。这是两次worker ABI探针，单独属于本次环境自检，不是决斗smoke、规则认证或既有研究scope消费。普通CLI/worker哈希与其包内清单一致；包仍为2026-10-19构建。
- `cargo fmt --all -- --check`、workspace全目标offline/locked Clippy `-D warnings`通过。隔离target的`cargo test --workspace --offline --locked -- --test-threads=1`为330 passed、36 ignored；另执行adapter examples为52 passed、1 ignored。日志在`target/workspace-audit-2026-10-27-codex/`。测试运行与本机发布worker隔离；忽略项未因此获得真实资产验收。
- 本次最初针对pytest缓存配置运行`tests/test_ground_collapse_protocol.py`，8项通过；预建`target/pytest-cache`后无缓存警告。接续的聚焦检查另见下方；恢复后完整Python套件结果见本节下方；下方734 passed/9 skipped属于旧Ground批次。
- 经提升权限逐个检查路径与内容后，非递归移除222个空pytest缓存目录、四个空`.v5-package-test-*`及三个空`tests/tmp*`目录；清单和首次空值判断导致零删除的记录也保存在上述target目录。未修改ACL，清理后`git status --porcelain=v1 --untracked-files=all`退出0且无访问警告。Ground归档中61个非空合成测试文件保留原位。
- 删除两个未被各自crate直接使用的`toml`/`sha2`依赖声明，offline更新的锁文件只移除相应直接依赖；其他crate仍使用它们。`.gitignore`是Ground固定工具包成员，本次未改。
- 保存的Ground准备报告执行`--verify-only`通过，报告SHA-256前后均为`5354438945079d9df4f2867e272e2420d71605909c772f0a874b6c21b8319d74`，本次复核的native/runner/worker/FFI调用均为0；日志见上述target目录。
- 文档拆分前快照`TASKS_HISTORY.md` SHA-256为`b7e6ec057cf03221a33c430ab343bb3dcdb790f4e5f91b84fece7869ec17d281`，`docs/TESTING_HISTORY.md`为`0798aa8ea1c333f9de0850752b512be74c57096cf99ddd1bc1226ff592d93eef`；拆分清单位于上述target目录的`doc-split-manifest.json`。独立检查保留全部原标题顺序、锚点和历史跳转。
- 隔离执行部署脚本的文档复制与包入口改写块：TESTING及其历史快照副本哈希匹配，79个历史跳转按本地Unicode标题slug算法匹配；包入口四个源链接和改写链接指向同一存在目标。生产包未改写；扁平副本的其余相对链接仍有缺口，不等于完整部署或GitHub渲染验证。结果位于上述target目录的`package-docs-copy-check-7908f831acd74cab9cd1da108f6031fc/`与`package-entry-transform-check-3d1a25e941374a37875d8da44792a520/`。
- 包入口模板现于构建、资产准备及发布覆盖前在内存中校验和改写。隔离验证成功路径及四条链接各自缺失/重复共8个负例，失败均发生在模拟发布前；记录在上述target目录的`package-preflight-check-e778dc9378394063867913bdb690984d/result.json`。脚本其余步骤不是事务，I/O错误仍可能造成部分更新。
- Python 3.12干净副本发现固定清单检查直接读取忽略的本机证据；已拆分为始终执行的固定pins检查与缺失时单独跳过的本机比对。隔离Python 3.12结果：无历史baseline目录时20 passed/1 skipped/2 subtests，有真实清单时21 passed/2 subtests；baseline存在但清单缺失、baseline为普通文件、清单篡改和清单为目录均按预期失败，详细矩阵见`curry-pin-isolated-check/python312-matrix-summary.json`。该聚焦检查的旧快照全套结果见下方。
- 接续阶段在文档拆分、CI与部署脚本修改后再次执行Ground `--verify-only`：`valid=true`、`preparation_successful=true`，native/runner/worker/FFI调用均为0；正式报告前后SHA-256仍为`5354438945079d9df4f2867e272e2420d71605909c772f0a874b6c21b8319d74`。输出及元数据分别为上述target目录的`ground-verify-final.log`和`ground-verify-final-meta.json`；它核验保存的工具和报告，不使当前工作区等同旧归档。
- 独立Python 3.12.14 venv中执行CI的`pip install -e '.[test]'`，`pip check`通过，pytest 9.1.1、jsonschema 4.26.0可导入，`ygo_data.cli validate`样本输出验证2张卡。安装及检查日志分别为上述target目录的`ci-editable-install.log`和`ci-editable-check.log`；完整Python套件另行记录。
- `checked_output` 曾将Git忽略检查异常误报为未忽略，并将跟踪检查异常误当未跟踪；现在仅对Git退出0/1执行原有判断，其余状态失败关闭。先观察两个检查各自注入2/128的4个子测试失败，再修复；Python 3.12聚焦完整`tests/test_identity.py`为11 passed、4 subtests passed，覆盖真实Git正常与异常仓库，日志为上述target目录`identity-git-exit-check/red.log`和`green.log`。未调用原生研究执行。
- `jsonschema` 原先只列在test extra，而研究入口无条件加载其依赖，基础环境执行`ygo_eval.research --help`会失败。现将其列为基础运行依赖，pytest仍为test extra。独立Python 3.12环境中无extras普通安装及editable安装、元数据和`pip check`通过；卡片样本验证2张、研究入口`--help`退出0；模拟缺少jsonschema时报告校验按预期拒绝。日志为上述target目录的`base312-*.log`；未调用原生研究。
- 在`checked_output`修复后重新执行保存的Ground报告`--verify-only`，退出0，报告哈希前后均为`5354438945079d9df4f2867e272e2420d71605909c772f0a874b6c21b8319d74`，日志和元数据分别为`ground-verify-post-identity.log`、`ground-verify-post-identity-meta.json`；这是保存报告及工具的离线验证，非当前工作区与旧归档逐字一致的证明。
- 基础依赖调整后再次执行保存的Ground报告`--verify-only`，`valid=true`且native/runner/worker/FFI均0，报告前后哈希仍为`5354438945079d9df4f2867e272e2420d71605909c772f0a874b6c21b8319d74`；日志与元数据为`ground-verify-post-package.log`和`ground-verify-post-package-meta.json`。
- 干净副本第二项生产来源测试同样直接读取历史清单，导致其后的嵌套静态断言无法执行。已拆分为始终执行的固定哈希/嵌套pins检查和单独本机清单比较；Python 3.12隔离矩阵无baseline时8 passed/1 skipped，有真实清单时9 passed，空baseline、baseline为文件、篡改清单和清单为目录均按预期失败；日志见`curry-source-isolated-check/`。
- Python 3.12短路径干净源码快照`ci-final-snapshot-manifest.json`（清单SHA-256 `bf6c7c73bc06b57bb84b794caedc12372efd2e78827c4d94a0ab3fc27b504614`）全套为717 passed、18 skipped、13 failed，耗时1820.42秒；日志`ci-final-python312.log`。失败按回溯分为真实历史清单/账本缺席、测试临时目录和合成banlist/预检准备缺口，不能标为通过。修复后：信息路线文件11 passed/13 subtests；Curry两个文件18 passed/2 skipped；Tenki三个文件71 passed/3 skipped/18 subtests；相关本机历史基线缺失、部分缺失和篡改负例单独记录在`route-empty-runtime-*.log`、`ci-curry-tests-fixed.log`、`tenki-*.log`。完整账本正例仍需本机完整证据。后续完整套件结果另记。
- Curry两处历史baseline跳过条件现仅捕获`FileNotFoundError`；Python 3.12隔离6项检查验证缺失、权限错误和其他OSError，日志为`ci-curry-skip-boundary.log`。无历史baseline时revalidation公共七阶段E2E被跳过，其他合成测试不能完全替代此覆盖。
- 从暂停恢复后，Python 3.12在本机完整历史材料上执行三个Tenki历史检查，3 passed；测试明确禁止原生runner，日志为`ci-resume-local-evidence.log`。另执行Curry revalidation公共七阶段集成测试，1 passed；该测试读取真实V3历史基线并检查前后状态，runner及新增执行输出均为合成替身，不是新原生实验或规则资格，日志为`ci-resume-v3-e2e.log`。干净checkout仍会跳过需要这批历史材料的路径。
- 恢复后对2026-10-19普通部署包执行一次预算受限`engine smoke`及单独`combo replay`：smoke退出0，326节点、329次引擎调用、`time_budget`终止，3条线路标记`engine_verified`且`replay_verified=true`；独立replay退出0、3/3线路通过。smoke报告SHA-256 `e813a3d7a66eac1d07df72165fbdb5901c11f6bcad81779d5425f7cb26f3698f`，replay输出SHA-256 `dfa31271c7cc3f371950661e243b2d3f7e3a50f6f5c4449c3bf1bee56fa200e0`，报告、输出及退出码在上述target目录`deployed-smoke-20261027-resume.*`和`deployed-smoke-replay-20261027-resume.*`。这是普通包本地诊断产生的实际引擎调用，独立于已封存研究scope/账本；单独replay的具体引擎调用数未计量。时间预算截断不证明全搜索、规则覆盖或全局最优，也不代表当前工作区已部署。
- 修复后在短路径干净隔离快照运行Python 3.12完整顶层pytest：**727 passed、24 skipped、0 failed**，1628.95秒、退出0；清单612项，SHA-256 `f9034abfdaa55af8c8cab518691bdc9c77382d40062fb9940fac629ba7155f38`，日志与退出码为`ci-resume-python312.log`、`ci-resume-python312-exit.txt`。该结果是当前复核补丁之前的完整套件基线；此前快照后源码、测试和配置一致，差异见`ci-resume-snapshot-comparison.json`。本轮审查又改动语言审计和兼容帧验证，完整套件尚待重跑。后续为准备复验，快照脚本误覆盖了本机`ci-resume-snapshot-manifest.json`与`ci-resume-snapshot-git.log`；原manifest字节未能恢复，原Git添加日志也未能逐字恢复（其他快照日志仍在）。旧612文件隔离源码副本仍完整且工作树清洁，七个记录差异pin匹配，重建清单见`target/workspace-audit-2026-10-27-codex/ci-resume-snapshot-manifest-reconstructed.json`（SHA-256 `df3ac48da93d666db256bc9517d779b030b890823f227fb8351aad9cb2c81a29`）；旧测试输出日志仍保留。细节见本机`ci-resume-manifest-overwrite-incident.json`。24项跳过包括2项Windows符号链接不可用、8项需本机历史材料、7项需历史baseline、7项显式真实资产/报告opt-in。
- 对其中历史材料相关跳过项，额外在本机执行：3项Curry本地pins/frozen cases、3项Tenki历史检查、1项使用真实V3基线但模拟runner的Curry七阶段集成，均通过；另以不写旧目录的方式执行历史审计文件16 passed/1 deselected，覆盖其中7项本机历史检查。余下旧目录独占写入测试未在本机执行；真实资产opt-in和符号链接不可用项不由上述结果覆盖，另见后续独立检查。日志分别为`ci-resume-local-pins.log`、`ci-resume-local-evidence.log`、`ci-resume-v3-e2e.log`和`ci-resume-local-history.log`。
- 对干净快照跳过的7项真实资产/报告opt-in，在本机补充执行：6项只读历史报告、快照与引擎清单验证均通过（`ci-resume-local-reports.log`）；赛事开发配置固定案例及独立重放1项通过，使用隔离配置副本及独立账本，2次实际worker请求分别记为debited，结果一致（`tournament-deployment-audit-resume/test.log`及`asset-probe-audit.jsonl`，账本SHA-256 `13a841e8d2495ef6496e1b8326cc629b9282d6c3965034f1c051e6552c323cb8`）。这是独立部署兼容诊断，不复用或累加研究scope账本；底层FFI次数未独立计量，不等于最新源码正式双资产发布验收。
- 接续只读容量扫描：`target/`约106.64 GiB、`data/`约112.86 GiB可读取文件逻辑大小；85处访问错误、无硬链接去重且并发写入，不等同实际占用。清单见上述target目录的`capacity-inventory.json`。`.venv`的Python可启动但缺少pip和pytest；详细限制见[环境审计](ENVIRONMENT_AUDIT.md)。
- 经检查准确路径、内容、reparse及编译进程后，仅删除本轮隔离Cargo编译目录`target/workspace-audit-2026-10-27-codex/cargo`；约5.76 GiB分配量为清理前估算，测试日志保留在父目录。证据为`cargo-cache-cleanup.json`；日志中二进制路径现已不可用，重新执行须重新编译。
- 恢复后对容量清点的85个原访问错误路径进行提升权限只读复核：85个均能枚举直接子项，58个当前为空、27个非空且属于隔离Python依赖目录；没有递归复测，原容量数仍不能当作精确占用。随后仅非递归移除本轮pip产生的5个空目录，其余路径保留；记录为`capacity-errors-recheck.json`和`pip-empty-cleanup.json`。
- 文档检查验证本机相对文件目标存在；指向忽略的`target/`和`data/runtime/`的证据在干净checkout中仍需单独提供。历史原生预算、规则资格及未知累计消费没有由本次检查增加。
- 交付前复核发现两项可修复问题：语言审计会保留schema禁止的未知record/field属性，且缺失或不支持的language会产出不符合schema的记录；现改为在写报告前拒绝不合约输入，Python 3.12聚焦文件`tests/test_coverage_language.py`为13 passed、4个拒绝子测试通过。修复前新增反例的4种输入均未拒绝；测试日志在`target/pytest-cache`之外的本机命令输出，不重写上述历史完整套件日志。
- 同次复核确认v1–v5历史事件opcode 56/92旧格式会被新增解析器拒绝；`frame_matches_raw`现接受精确的旧`unparsed`投影，同时验证新格式。离线locked Rust定向测试`cargo test --offline --locked -p ygo-engine-adapter --test historical_prompt`为2 passed。worker内部失败通过`DuelResult`保存部分terminal observation；独立复核的早期疑点不成立。
- 本次`.gitignore`审阅合并为crate内`data/tmp/`与`data/runtime/`两条本机证据规则，并排除可中断的`tests/.tenki-*`合成临时目录。清理候选复核后发现五个`.tenki-*`目录属于603项冻结归档，已从原归档按逐文件SHA-256恢复；报告为`target/workspace-audit-2026-10-27-codex/stale-tenki-restoration.json`。未把报告、runner占位文件或本机研究输出加入提交。两个crate内零收费测试ledger目录和一个188文件的confirmation测试输出仍保留，因其本机历史保留用途未完全确认；逐项清单见同目录`nested-synthetic-cleanup.json`。独立审阅中关于worker失败诊断的疑点已通过控制流核对排除；研究续窗说明现明确新ID须有单独用户批准，ID自身不是授权证明。

本次未运行新的收费研究实验、正式v6、16+32手评估或最新源码干净双资产部署；环境路径与保留范围见[环境审计](ENVIRONMENT_AUDIT.md)。

## 2026-10-27 项目再规划：仅文档静态交叉核对

本记录是后续文档重整的只读核对，不是下面Ground Collapse批次的实跑复验。开始编辑时，最新最终源码清单的603项与工作区逐项一致；完成文档修订后，完整工作区已变化，旧清单的完整源码身份不再描述现在的工作区。HEAD为 `8a6b2f6762131aebea6d8c0f5f61363d573f1b36`，既有未提交/未跟踪改动保留；HEAD不等于完整工作区身份。

以下是当时运行的历史命令和结果，**当前工作区已有后续修改，原命令中的工作区一致性断言不再适用于当前状态**；不要将其直接作为当前验收命令。检查当时从仓库根目录运行，结果为 `archive=603, nonmarkdown=509, delivery_references=15: OK`，退出0。它复核旧归档成员及其清单、当前工作区范围内509个非Markdown文件，以及交付记录中15个带路径、大小和SHA256的引用；**不证明清单之外所有忽略文件或不可读路径均未改变**。

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


以下保留历史标题及原锚点；完整记录见同目录历史快照。

## 历史状态（2026-10-27）：绑定V3恢复证据的Curry七阶段再验真：七阶段与双分支重放通过

[历史原文](TESTING_HISTORY.md#历史状态2026-10-27绑定v3恢复证据的curry七阶段再验真七阶段与双分支重放通过)

## 2026-10-26 Curry V3真实来源角色适配与零runner恢复：恢复和只读verify通过

[历史原文](TESTING_HISTORY.md#2026-10-26-curry-v3真实来源角色适配与零runner恢复恢复和只读verify通过)

## 2026-10-26 Curry V2精确来源恢复与零runner验收：离线通过，真实恢复在输入角色门禁失败

[历史原文](TESTING_HISTORY.md#2026-10-26-curry-v2精确来源恢复与零runner验收离线通过真实恢复在输入角色门禁失败)

## 历史验证（2026-10-26）：Curry V5已存证据恢复与报告发布诊断

[历史原文](TESTING_HISTORY.md#历史验证2026-10-26curry-v5已存证据恢复与报告发布诊断)

## 2026-10-26 Curry V5干净交付与单次零调用验收：runner只读检查通过，正式报告未发布

[历史原文](TESTING_HISTORY.md#2026-10-26-curry-v5干净交付与单次零调用验收runner只读检查通过正式报告未发布)

## 2026-10-26 Curry V4精确stdout合同与单次零调用验收：真实只读审计在来源根门禁失败

[历史原文](TESTING_HISTORY.md#2026-10-26-curry-v4精确stdout合同与单次零调用验收真实只读审计在来源根门禁失败)

## 2026-10-26 Curry V3来源角色修复与单次零调用验收：真实只读审计在stage 1父收据检查失败

[历史原文](TESTING_HISTORY.md#2026-10-26-curry-v3来源角色修复与单次零调用验收真实只读审计在stage-1父收据检查失败)

## 2026-10-25 Curry V2账本交接恢复审计：离线验收通过，真实只读审计首门禁失败，新增原生0

[历史原文](TESTING_HISTORY.md#2026-10-25-curry-v2账本交接恢复审计离线验收通过真实只读审计首门禁失败新增原生0)

## 2026-10-25 Curry V3预留绑定的Curry七阶段验证：stage 2停止，新增消费1/7

[历史原文](TESTING_HISTORY.md#2026-10-25-curry-v3预留绑定的curry七阶段验证stage-2停止新增消费17)

## 原生前记录：Curry V3预留绑定的七阶段验证离线总检

[历史原文](TESTING_HISTORY.md#原生前记录curry-v3预留绑定的七阶段验证离线总检)

## 2026-10-25 Curry V3风险预留：真实只读审计及verify通过，新增原生调用0

[历史原文](TESTING_HISTORY.md#2026-10-25-curry-v3风险预留真实只读审计及verify通过新增原生调用0)

## 2026-10-25 Curry v2风险预留恢复：合成验收通过，真实来源门禁失败，新增原生0

[历史原文](TESTING_HISTORY.md#2026-10-25-curry-v2风险预留恢复合成验收通过真实来源门禁失败新增原生0)

## 2026-10-25 Curry预算风险预留准入准备：真实来源门禁失败，新增原生调用0

[历史原文](TESTING_HISTORY.md#2026-10-25-curry预算风险预留准入准备真实来源门禁失败新增原生调用0)

## 2026-10-24 Curry公共审计完整合成验收：通过，新增原生调用0

[历史原文](TESTING_HISTORY.md#2026-10-24-curry公共审计完整合成验收通过新增原生调用0)

## 2026-10-24 Curry v2清单驱动审计：真实只读核验通过，合成总流程仍有缺口

[历史原文](TESTING_HISTORY.md#2026-10-24-curry-v2清单驱动审计真实只读核验通过合成总流程仍有缺口)

## 2026-10-24 Curry 公共审计合成验收：额度不足时暂停，未完成

[历史原文](TESTING_HISTORY.md#2026-10-24-curry-公共审计合成验收额度不足时暂停未完成)

# 本机验证记录

[历史原文](TESTING_HISTORY.md#本机验证记录-1)

## 2026-10-24 Curry新scope七阶段确认：收费前normal编排拒绝，按门禁暂停

[历史原文](TESTING_HISTORY.md#2026-10-24-curry新scope七阶段确认收费前normal编排拒绝按门禁暂停)

## 2026-10-24 Curry哈希角色修复与只读验收：通过，新增原生0

[历史原文](TESTING_HISTORY.md#2026-10-24-curry哈希角色修复与只读验收通过新增原生0)

## 2026-10-24 Mooyan Curry opcode14七阶段批：离线检查通过，收费前预检阻断，新增原生0

[历史原文](TESTING_HISTORY.md#2026-10-24-mooyan-curry-opcode14七阶段批离线检查通过收费前预检阻断新增原生0)

## 2026-10-23 天玑完整路径定向验真：六阶段通过，累计32次

[历史原文](TESTING_HISTORY.md#2026-10-23-天玑完整路径定向验真六阶段通过累计32次)

## 2026-10-23 天玑runner输出/期限修复与只读审计：通过，新增原生0

[历史原文](TESTING_HISTORY.md#2026-10-23-天玑runner输出期限修复与只读审计通过新增原生0)

## 2026-10-23 天玑placement confirmation：离线验收通过，stage 1 runner超时后停止

[历史原文](TESTING_HISTORY.md#2026-10-23-天玑placement-confirmation离线验收通过stage-1-runner超时后停止)

## 2026-10-22 天玑历史锚点修复与只读预检：离线通过，新增原生0

[历史原文](TESTING_HISTORY.md#2026-10-22-天玑历史锚点修复与只读预检离线通过新增原生0)

## 2026-10-22 天玑v2基线迁移与六阶段验真：离线准备通过，原生阶段零消费失败

[历史原文](TESTING_HISTORY.md#2026-10-22-天玑v2基线迁移与六阶段验真离线准备通过原生阶段零消费失败)

## 2026-10-22 天玑区域18与opcode13恢复：计数兼容修复，迁移门禁拒绝

[历史原文](TESTING_HISTORY.md#2026-10-22-天玑区域18与opcode13恢复计数兼容修复迁移门禁拒绝)

## 2026-10-22 天玑区域18与opcode13两分支：离线交付完成，原生前置阻断

[历史原文](TESTING_HISTORY.md#2026-10-22-天玑区域18与opcode13两分支离线交付完成原生前置阻断)

## 2026-10-22 天玑合同兼容修复与离线收尾

[历史原文](TESTING_HISTORY.md#2026-10-22-天玑合同兼容修复与离线收尾)

## 2026-10-22 天玑六槽位批：2次后区域18停门，额度暂停待合同修复

[历史原文](TESTING_HISTORY.md#2026-10-22-天玑六槽位批2次后区域18停门额度暂停待合同修复)

## 2026-10-21 剩余提示静态准备：三个候选及命令6阻断，新增原生0

[历史原文](TESTING_HISTORY.md#2026-10-21-剩余提示静态准备三个候选及命令6阻断新增原生0)

## 2026-10-21 洗手牌后结束线路：可见历史闭合与终场衔接，新增原生0

[历史原文](TESTING_HISTORY.md#2026-10-21-洗手牌后结束线路可见历史闭合与终场衔接新增原生0)

## 2026-10-21 P1可见信息、洗手牌理想概率及动作顺序：零原生交付

[历史原文](TESTING_HISTORY.md#2026-10-21-p1可见信息洗手牌理想概率及动作顺序零原生交付)

## 2026-10-21 独立历史核验与四次终场续办：两组通过，预算封存

[历史原文](TESTING_HISTORY.md#2026-10-21-独立历史核验与四次终场续办两组通过预算封存)

## 2026-10-20 赛事/洗手牌四次入口：离线交付，来源门禁阻断原生

[历史原文](TESTING_HISTORY.md#2026-10-20-赛事洗手牌四次入口离线交付来源门禁阻断原生)

## 2026-10-20 Rabbit终场单例两次验真交付

[历史原文](TESTING_HISTORY.md#2026-10-20-rabbit终场单例两次验真交付)

## 2026-10-20 T1/T2工具与T3查询失败停止断点

[历史原文](TESTING_HISTORY.md#2026-10-20-t1t2工具与t3查询失败停止断点)

## 2026-10-20 S1/S2交付与S3停止断点

[历史原文](TESTING_HISTORY.md#2026-10-20-s1s2交付与s3停止断点)

## 2026-10-20 S1/S2离线工具及原生前置验证

[历史原文](TESTING_HISTORY.md#2026-10-20-s1s2离线工具及原生前置验证)

## 2026-10-19 P1动作修复与离线研究准备

[历史原文](TESTING_HISTORY.md#2026-10-19-p1动作修复与离线研究准备)

## 2026-10-19 断点恢复及首批A–E验收

[历史原文](TESTING_HISTORY.md#2026-10-19-断点恢复及首批ae验收)

## 2026-10-19 首批基线审计实现与用户要求暂停

[历史原文](TESTING_HISTORY.md#2026-10-19-首批基线审计实现与用户要求暂停)

### 已运行的最终默认验证

[历史原文](TESTING_HISTORY.md#已运行的最终默认验证)

### 已运行的数据调查

[历史原文](TESTING_HISTORY.md#已运行的数据调查)

### 原生批：累计7次，无未知消费

[历史原文](TESTING_HISTORY.md#原生批累计7次无未知消费)

### 暂停时尚缺

[历史原文](TESTING_HISTORY.md#暂停时尚缺)

## 2026-10-19 工作树整理与文档/环境复核

[历史原文](TESTING_HISTORY.md#2026-10-19-工作树整理与文档环境复核)

## 2026-10-19 产品目标与路线文档交付：只读运行复核

[历史原文](TESTING_HISTORY.md#2026-10-19-产品目标与路线文档交付只读运行复核)

## 2026-10-19 完整自检、当前部署与文档重构

[历史原文](TESTING_HISTORY.md#2026-10-19-完整自检当前部署与文档重构)

## 2026-10-18 费用支付后的运行中故障

[历史原文](TESTING_HISTORY.md#2026-10-18-费用支付后的运行中故障)

## 2026-10-18 初始预算拒绝与计数负例

[历史原文](TESTING_HISTORY.md#2026-10-18-初始预算拒绝与计数负例)

## 2026-10-18 独立符号前沿续跑

[历史原文](TESTING_HISTORY.md#2026-10-18-独立符号前沿续跑)

## 2026-10-18 异常证据基础专项（非整轮验收）

[历史原文](TESTING_HISTORY.md#2026-10-18-异常证据基础专项非整轮验收)

## 2026-10-17 调用前预算截断

[历史原文](TESTING_HISTORY.md#2026-10-17-调用前预算截断)

## 2026-10-17 自主线路新增依赖资格

[历史原文](TESTING_HISTORY.md#2026-10-17-自主线路新增依赖资格)

## 2026-10-17 实际灰响应的分支资格

[历史原文](TESTING_HISTORY.md#2026-10-17-实际灰响应的分支资格)

## 2026-10-17 局部自主灰后恢复与报告重算

[历史原文](TESTING_HISTORY.md#2026-10-17-局部自主灰后恢复与报告重算)

## 2026-10-17 费用前发动源与公开查询修复

[历史原文](TESTING_HISTORY.md#2026-10-17-费用前发动源与公开查询修复)

## 2026-10-17 实际状态与请求绑定收口

[历史原文](TESTING_HISTORY.md#2026-10-17-实际状态与请求绑定收口)

## v6同名手牌与宿主离场坐标

[历史原文](TESTING_HISTORY.md#v6同名手牌与宿主离场坐标)

## v6逐分支资格与负例合同

[历史原文](TESTING_HISTORY.md#v6逐分支资格与负例合同)

## v6原始事件与查询见证基础

[历史原文](TESTING_HISTORY.md#v6原始事件与查询见证基础)

## v6资源属性与素材容器补强

[历史原文](TESTING_HISTORY.md#v6资源属性与素材容器补强)

## v6第一组资源转移（完整语义仍在开发）

[历史原文](TESTING_HISTORY.md#v6第一组资源转移完整语义仍在开发)

## v6原生案例合同与首批资源规则

[历史原文](TESTING_HISTORY.md#v6原生案例合同与首批资源规则)

## v6持久调用包装层（语义验真前置）

[历史原文](TESTING_HISTORY.md#v6持久调用包装层语义验真前置)

## v6基础集成复验

[历史原文](TESTING_HISTORY.md#v6基础集成复验)

## 2026-10-16 原表重选与独立资产（第一阶段）

[历史原文](TESTING_HISTORY.md#2026-10-16-原表重选与独立资产第一阶段)

## 2026-10-16 赛事来源关口核验（未通过，不是v6验收）

[历史原文](TESTING_HISTORY.md#2026-10-16-赛事来源关口核验未通过不是v6验收)

## 2026-10-16 多响应点与稳健展开顺序（验收完成）

[历史原文](TESTING_HISTORY.md#2026-10-16-多响应点与稳健展开顺序验收完成)

## 2026-10-16 指定灰流丽中断与恢复（本轮验收完成）

[历史原文](TESTING_HISTORY.md#2026-10-16-指定灰流丽中断与恢复本轮验收完成)

## 2026-10-15 通用目标 v3：证据修复与最终验收

[历史原文](TESTING_HISTORY.md#2026-10-15-通用目标-v3证据修复与最终验收)

## 2026-10-14 第二阶段：逐效果验真与 Break Sword v2

[历史原文](TESTING_HISTORY.md#2026-10-14-第二阶段逐效果验真与-break-sword-v2)

## 首版验收记录（历史）

[历史原文](TESTING_HISTORY.md#首版验收记录历史)

## 源码、测试与审查

[历史原文](TESTING_HISTORY.md#源码测试与审查)

## 冻结版本与独立干净 checkout

[历史原文](TESTING_HISTORY.md#冻结版本与独立干净-checkout)

## 固定预算对照

[历史原文](TESTING_HISTORY.md#固定预算对照)

## 复验命令

[历史原文](TESTING_HISTORY.md#复验命令)

## 2026-10-24 Curry冻结输入恢复门禁与只读审计

[历史原文](TESTING_HISTORY.md#2026-10-24-curry冻结输入恢复门禁与只读审计)

## 2026-10-25 Curry父账本锁释放修复与stage 2只读验收

[历史原文](TESTING_HISTORY.md#2026-10-25-curry父账本锁释放修复与stage-2只读验收)
