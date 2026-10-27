"""Read-only audit for the frozen Curry input-hash refusal."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import zipfile
from typing import Any

from ygo_data.identity import canonical, digest
from ygo_eval.prompt_probe_prepare import safe_path, strict_json


BASELINE_RELATIVE = Path("data/runtime/p1-curry-option-confirmation-native-2026-10-24")
OUTPUT_RELATIVE = Path("data/runtime/p1-curry-input-recovery-offline-2026-10-24")
OUTPUT_V2_RELATIVE = Path("data/runtime/p1-curry-input-recovery-v2-offline-2026-10-24")
ACCEPTANCE_SHA256 = "23fd2d5639663bae962f35a5792407b69cc8db202ccd8faa1c5b0a822ca111c0"
DELIVERY_SHA256 = "c2a2f2476732ee6503bfc047603f379d3f248098c3e67ea4ee6dc8b6c7971620"
INVENTORY_SHA256 = "807a45e142d5b634ad25be5ac1562ac829fa9cffca62b21c7c9f71a499b3e1ea"
NATIVE_ARCHIVE_SHA256 = "37b3d0c97478e566c8496f68a18508b4810e2997debcd2ca2ec148cc5afc84fe"
NATIVE_LIST_SHA256 = "da8d20ded68207065c62cb56cb23b96928359facac0abecd6dc003ccedc15e06"
FINAL_ARCHIVE_SHA256 = "c9c479323ee3344ed0b5debadc2d1ca539ca8b51df391df23c9734fa605a65e0"
FINAL_LIST_SHA256 = "808ea72c18a58c26136e130b13d22da7bd766565551c52a5a33f2d39c05f30fe"
NATIVE_SOURCE_IDENTITY = "316443a5aa270488fb5ab88f463174a9e6c3f66cc9ddc1702c1ffe96f0525408"
FINAL_SOURCE_IDENTITY = "d15234dc6c09f4a307eb249110b50d4ef2de13412d9e8a977ebfbd186c57aa92"
EXPECTED_HEAD = "8a6b2f6762131aebea6d8c0f5f61363d573f1b36"
CONFIRMATION_HANDOFF_RELATIVE = Path(
    "docs/superpowers/plans/2026-10-24-curry-option-confirmation-handoff.md"
)
ALLOWED_ARCHIVE_DIFFS = {
    "TASKS.md",
    "docs/TESTING.md",
    CONFIRMATION_HANDOFF_RELATIVE.as_posix(),
}
NATIVE_SOURCE_PATH = "python/ygo_eval/native_curry_option_validation.py"
RESEARCH_SOURCE_PATH = "python/ygo_eval/research.py"
HISTORICAL_LEDGER_COUNT = 9
HISTORICAL_CONSUMED = 32
HISTORICAL_UNKNOWN = 0
CHECK_NAMES = (
    "acceptance_delivery_anchors",
    "evidence_inventory",
    "source_archives",
    "frozen_input_binding",
    "historical_ledgers",
    "old_material_protection",
    "input_stability",
)
FLAGS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}
HASH = re.compile(r"^[a-f0-9]{64}$")

# This authenticated pre-run protection map is embedded below as a fixed data
# literal. It is never discovered from the live `before.json` at runtime.
_TENKI_BASELINE_PROTECTED_PINS: tuple[tuple[str, str], ...] = (
    ('crates/ygo-engine-adapter/src/codec.rs', '224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e'),
    ('crates/ygo-engine-adapter/src/worker.rs', 'adfad90c5a62944e2d669fad81dece7ec4e70a338a03362a30ffb2453a29c4d7'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl', 'b1cde5ab207a1e9ee5033f2b185c5c7de90994021d39c6a1bad9e82b2974bd6a'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/0cd8361383d52b7a3295cde354b99ab86af346af3c17addd625ea5344f90a0dc.json', '0cd8361383d52b7a3295cde354b99ab86af346af3c17addd625ea5344f90a0dc'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/143d8220aa0210f67fae1d25934c5ba558282544836f1b9b1f8aee8aaa3c63b9.json', '143d8220aa0210f67fae1d25934c5ba558282544836f1b9b1f8aee8aaa3c63b9'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/2b06a6c5351ca5a8a1c38b30fd32b2142e3523394e61cb249cb3443cc4eb0370.json', '2b06a6c5351ca5a8a1c38b30fd32b2142e3523394e61cb249cb3443cc4eb0370'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/2f1c981dcc38756638a0218439f90fcbfaf82bfdfdc73f90bdc26adf7383e42e.json', '2f1c981dcc38756638a0218439f90fcbfaf82bfdfdc73f90bdc26adf7383e42e'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/399c3cbc8ada12b0d6132b32e2abe359bbb890cdecd694bbaec895aa1b592b30.json', '399c3cbc8ada12b0d6132b32e2abe359bbb890cdecd694bbaec895aa1b592b30'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/480b4b748ab51b3899768d1c6ddfc464f37076f29c0e4e9ef58d622c3904009f.json', '480b4b748ab51b3899768d1c6ddfc464f37076f29c0e4e9ef58d622c3904009f'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/67e3b42d0c032ed74048d8b3b65fb43f6a0509c13421311170da652e76a0c4ba.json', '67e3b42d0c032ed74048d8b3b65fb43f6a0509c13421311170da652e76a0c4ba'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/7e688c0280b941241c607086bd5b4a0708e58afc940cb4b1ee842d3189d5a050.json', '7e688c0280b941241c607086bd5b4a0708e58afc940cb4b1ee842d3189d5a050'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/83dc61d14d1d338312d42c6c3c83903e83101fa8d43d7c606dee51f21401d09e.json', '83dc61d14d1d338312d42c6c3c83903e83101fa8d43d7c606dee51f21401d09e'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/930a5628f624ce23b6f025714b2978aa3d334f90dcde036b6466c5283826b784.json', '930a5628f624ce23b6f025714b2978aa3d334f90dcde036b6466c5283826b784'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/b1450e0bcc7875e259c4629957828bea2dfe4388908cd8b6c50a283a38a24e7f.json', 'b1450e0bcc7875e259c4629957828bea2dfe4388908cd8b6c50a283a38a24e7f'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/cf1001c774b82ec84f6b5f05d4f081bd186bde77dbd2233f02545f4574388dd9.json', 'cf1001c774b82ec84f6b5f05d4f081bd186bde77dbd2233f02545f4574388dd9'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/dc4fd5edede7bcb02e42e0bef0c86d853749a2ebab701081136851bcd314e112.json', 'dc4fd5edede7bcb02e42e0bef0c86d853749a2ebab701081136851bcd314e112'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/ddc185446514c84c84940fae3c7dacf65c40830bacae4601c2596d049b090fbb.json', 'ddc185446514c84c84940fae3c7dacf65c40830bacae4601c2596d049b090fbb'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/df938843ed5a52d032ceb8b5be839851a0583c14508a5480d9be21f71b91552c.json', 'df938843ed5a52d032ceb8b5be839851a0583c14508a5480d9be21f71b91552c'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/f5a815908583b49b155356aeb7de32d73696e99a3af822d5f714a8d3cc038998.json', 'f5a815908583b49b155356aeb7de32d73696e99a3af822d5f714a8d3cc038998'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/f9eb3a885b072f9f70b94b0e1c06f7cc8c2c07c2792206e2f68d3687101126e4.json', 'f9eb3a885b072f9f70b94b0e1c06f7cc8c2c07c2792206e2f68d3687101126e4'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/checkpoints/fd83e1a8f419398c5223a5ae83fcb3802c579e761d1c02f56f76fd789c5c4ff7.json', 'fd83e1a8f419398c5223a5ae83fcb3802c579e761d1c02f56f76fd789c5c4ff7'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/events/6369a414464d9091fef00f5c05fbef3f7dd7850c7120994aa014b678617fab71.json', '6369a414464d9091fef00f5c05fbef3f7dd7850c7120994aa014b678617fab71'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/events/8338a41c98f3b3145ef144e692aaa9c807403aa90867b94bba74f20d5bfb941d.json', '8338a41c98f3b3145ef144e692aaa9c807403aa90867b94bba74f20d5bfb941d'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/events/848aa745329c3758da7209886135dd12cf6def0680bfdee4f217869628afae9b.json', '848aa745329c3758da7209886135dd12cf6def0680bfdee4f217869628afae9b'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/events/aa7414b34ea382d27fdd2b5f50409dd72c0caed318a36eb69bf0f13229c1a6fd.json', 'aa7414b34ea382d27fdd2b5f50409dd72c0caed318a36eb69bf0f13229c1a6fd'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/events/f73e2ce8b1962668cde8aac3da0192a1e23eab12ddf1f295f68b29b0411ece52.json', 'f73e2ce8b1962668cde8aac3da0192a1e23eab12ddf1f295f68b29b0411ece52'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/results/15e01cc07416f755f40455c39b723ad3f40dd67b0f0e773626fac07b8b72061b.json', '15e01cc07416f755f40455c39b723ad3f40dd67b0f0e773626fac07b8b72061b'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/results/2c45c6a1641273a89f3360b6080858f26af78dc8fadc56505f97f93dadf6f40d.json', '2c45c6a1641273a89f3360b6080858f26af78dc8fadc56505f97f93dadf6f40d'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/results/406fac0f66cf8c91a5d4752442653817bd0d62ab87f72070181dfcc52cc058a3.json', '406fac0f66cf8c91a5d4752442653817bd0d62ab87f72070181dfcc52cc058a3'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/results/802461fa8358ed67f8d9ca64b7eb01d66c3a46c4a296ae4d3d17d6b084b399a5.json', '802461fa8358ed67f8d9ca64b7eb01d66c3a46c4a296ae4d3d17d6b084b399a5'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/results/8eda9d1eba582854f9e0a7ecbe4f5a6d2fd2a7baffb3a29f798f1d61b2b480ca.json', '8eda9d1eba582854f9e0a7ecbe4f5a6d2fd2a7baffb3a29f798f1d61b2b480ca'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/results/9da14b1bbda775758e619468c645f0c2c10141fb96ee80bff8af6db2da8380a3.json', '9da14b1bbda775758e619468c645f0c2c10141fb96ee80bff8af6db2da8380a3'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/results/a3a44635e2477dc8497184577781fff7c413e90bf846409dbcc520cba0f357ee.json', 'a3a44635e2477dc8497184577781fff7c413e90bf846409dbcc520cba0f357ee'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/results/bdae05e862b38eaefbfb3b7b3d38763b0764f38139751bc99ceed1a2c92292bd.json', 'bdae05e862b38eaefbfb3b7b3d38763b0764f38139751bc99ceed1a2c92292bd'),
    ('data/runtime/baseline-2026-10-19/research/calls.jsonl.blobs/results/eded07e8218d89c19bd22966ffc483108c3fbdd210e691cf28211012a03eb66d.json', 'eded07e8218d89c19bd22966ffc483108c3fbdd210e691cf28211012a03eb66d'),
    ('data/runtime/baseline-2026-10-19/research/frozen-cases.json', 'de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879'),
    ('data/runtime/cards.cdb', 'c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225'),
    ('data/runtime/p1-information-offline-2026-10-21/acceptance.json', 'cac76781c455854c8629cd47afed69ef090a8e4b7cd05f75e96afdeddb425a0a'),
    ('data/runtime/p1-information-offline-2026-10-21/audit-cli.log', '62a1adeaa7e8e0a3dd6eeb9add161c4246cf35842a67ab910549b18744134d8c'),
    ('data/runtime/p1-information-offline-2026-10-21/audit-final-cli.log', '62a1adeaa7e8e0a3dd6eeb9add161c4246cf35842a67ab910549b18744134d8c'),
    ('data/runtime/p1-information-offline-2026-10-21/audit-final.json', '32ade33aa012b1963520f25f4de57ac51a6f23f1e5199371afad064bbbc06d52'),
    ('data/runtime/p1-information-offline-2026-10-21/audit-policy-negative.json', 'd32c9c2d09f9dc1d0e9a6de70ebc52bff61b435e80df8ee90ce318af2d84eae8'),
    ('data/runtime/p1-information-offline-2026-10-21/audit.json', '560b5b9f31ee7d3e54dbca200bd6da9a0bd1f33d0f97ed61a612973f435b304e'),
    ('data/runtime/p1-information-offline-2026-10-21/before.json', 'b2d7baecf8d99880fa4805e260b1f22a1d6d39dbc657ad86585bf3f4b1c64e99'),
    ('data/runtime/p1-information-offline-2026-10-21/clippy.log', 'da4b765f6c4dc5970441b818b0c0662c2139e76fcc5de19335d39993a3f8d3b9'),
    ('data/runtime/p1-information-offline-2026-10-21/contract.json', '78d7ea65c136f0c7a33c827b77308af7b900d302f442208ebff4a993bac92dee'),
    ('data/runtime/p1-information-offline-2026-10-21/corpus-paths.json', 'adeebb7577e82b5fbd759a68aac04998e98b0d6d9aa4fa5d61656b2b64874955'),
    ('data/runtime/p1-information-offline-2026-10-21/delivery-checkpoint.json', 'b665ad765fa7fad51a51aedc24671fb17149e6897dde44c07581304d80c6e5ce'),
    ('data/runtime/p1-information-offline-2026-10-21/deployment-protection.json', '12eacc42f8c270ed73905b86c2a44266de6136274754f639c937ca20ec01210a'),
    ('data/runtime/p1-information-offline-2026-10-21/document-links.json', 'dd176d52bbacb7b4386490447b5c1c65e7d9853b09861b7decf30fdcd65b72e5'),
    ('data/runtime/p1-information-offline-2026-10-21/examples.log', '6cb32e406301f5d0385221032c9545964ae9ab8739b4cc4045e67fbf210a711c'),
    ('data/runtime/p1-information-offline-2026-10-21/final-source.json', '29df94693095cee19d8054bfa9fb3b416b4cde5a11a91053f231715b072dd896'),
    ('data/runtime/p1-information-offline-2026-10-21/final-source.zip', 'b8c5ab5ca921f7aca709cbe8a9020df1338a607e889b44ab40e70654c5b02ce3'),
    ('data/runtime/p1-information-offline-2026-10-21/finalize.py', 'fb5d70c3d1adddcd363e4f2590c035bb8eebd168a5d0235d3689d2ca00580707'),
    ('data/runtime/p1-information-offline-2026-10-21/fmt.log', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ('data/runtime/p1-information-offline-2026-10-21/negative-verification.json', 'ca40aea60fab17df6e809a9cd412ca59ae00ac50bc2b7a5eedcfc61a22ee6224'),
    ('data/runtime/p1-information-offline-2026-10-21/protection-check.json', 'fe0e097aa5738f4f68906ddbedf60987f6fefeaa7328622d403daf38c8e2f998'),
    ('data/runtime/p1-information-offline-2026-10-21/python.log', 'be53ce2a7db3fd729c805bd2144dd677ead22eef2c74c40625518b8d95c6f384'),
    ('data/runtime/p1-information-offline-2026-10-21/review.json', '1439e6b5af0ee0c87b22caa52474f83571e219b496c254d398fef73d810d36cc'),
    ('data/runtime/p1-information-offline-2026-10-21/run-rust.py', '9fd7b960590e3baad01ea38235dc3f0ebf19c210aa9f74f70f1daf3b85a50f90'),
    ('data/runtime/p1-information-offline-2026-10-21/rust-counts.json', '782a562f9ea4ec9c413e8c9a193e098e47bcb8eb8bd7cdb176b5c21f27e4d7e5'),
    ('data/runtime/p1-information-offline-2026-10-21/rust-verification.json', '8a3ddcaac20f97577c6bd08b90d66f62d2af5ddd847aa6cad3ecc6ae103e89c6'),
    ('data/runtime/p1-information-offline-2026-10-21/samples-negative.json', '3aed0c42b1f14d807a5ffe399148ffc25f85f157413af0d81a09200878406aec'),
    ('data/runtime/p1-information-offline-2026-10-21/skipped-tests.json', 'a2ec35c886e24f1a0aceaf328b84532a37b388e2b4f78ff91606e9c28ed5b8bf'),
    ('data/runtime/p1-information-offline-2026-10-21/source-protection.json', '6c267181dab312f70b6572537556a57f8f30935ae17b374456663835c65a4a27'),
    ('data/runtime/p1-information-offline-2026-10-21/tool-source.json', '89cedf419d96842a2b249ceb72e75c512ef03d2abba22a89bdb16b7f0ee34ee3'),
    ('data/runtime/p1-information-offline-2026-10-21/tool-source.zip', 'db5a19bd4e857b73069859f87c4f2a23b21e94397deb9d98448df2f4491a3c4c'),
    ('data/runtime/p1-information-offline-2026-10-21/verification-final.json', '0e0677a13bf14da35f0732db610c9a1fef46d9d27846c8152de151b4093b2f76'),
    ('data/runtime/p1-information-offline-2026-10-21/workspace.log', 'a6097e166387326c5d2eaeb75c1a13760f294659719b91e73dee1208b4ad0a7c'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/acceptance.json', '0e88c82501c4bbc229d6326b6b789411a93426f9474a02cd0e83e2c6cacbfcf7'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/bad-cases.json', '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/before.json', '0b0310d23ac1567bde6d36dc5dd4b989d9d85600bcefe861e3279caedf91228a'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/check-negatives.py', '375781a74abb57fbb0a40b557385ad2f335ad7c8287358e99856c3d74eed7e22'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/clippy.log', 'eaa5224346351eb5545a8a70faf9c9e02cbf1d1b9ca2a9cecdaf1988119e5f88'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/delivery-checkpoint.json', '88b59f43ac5b9be3e1d04f5db89e37a8c84c4072cb60ee917e824ebdb3831090'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/document-links.json', 'b614f5f0990d0271bc666b6ad21966a4ad839e479ce78c627ac57ee67ba7918f'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/examples.log', '88fbff542b183fa4058408ac3316f5dfb94dff904d742b341ce743d7988646dc'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/final-source.json', '9e6039ad02221f553b1d0eccbaeee65992e910fa1c43013a8ac3f5c10ab7cc6f'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/final-source.zip', '71ef8d4c89a97da0b15d961ef2637851e3a804e3379a821b13b57695ecf63d32'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/finalize.py', '47d098c0fe985e9e8f5aabed2fce766f568b5b4f67a095269e438b85e3b35525'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/fmt.log', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/focused.log', '87c22e3761a58845e8e068f3affbb0d5b93aa2dc80f9891d609bfc786d508fee'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/negative-verification.json', '561679b28a77b2320c576f6fd344db62a202bf261889cb51ca51fd681e0bbd04'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/overwrite-cli.log', 'e5ee1fd75e3fb9f69d0f9f60e7e2ac60cf9dc16baa166296f08ffee8365ea97d'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/prepare-attempt1-cli.log', '2beb18f01e712096432172ddb1625bc2524a36978350eceb84689747f1d577da'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/prepare-cli.log', '2beb18f01e712096432172ddb1625bc2524a36978350eceb84689747f1d577da'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/prepare-final-cli.log', '2beb18f01e712096432172ddb1625bc2524a36978350eceb84689747f1d577da'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/prepare-final-run.json', '9e11db9dab8642577d628a82ea2322a9d79d88a35846396d983bca986b6f6dc5'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/prepare-run.json', '78902527b85c194d2b7feeb7128f1901d723af17c9fe92f9981be935cdc5de61'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/python-counts.json', '9eabc1adce9978f5e7a0156e1a3a2517e7ba6d2eb7937f60275aeffcc202cb49'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/python-run.json', 'df54047939c0b7e795e5254e0bd6ada9af5704096ed91bff5da1ca3ac3b987ac'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/python.log', '71a7a8d19e3a30ae2b25cf7d7bce8a56ba9d7f0bdaa15f13539c290077d3d533'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/rejected-source-cli.log', '218cb379449eb9b859475d8ce6b3825f655bc0a174ac9a92259199ce6a020068'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/rejected-source/prepared-cases.json', '0e5cc6d04178b22cfb70b84692008f7b3cbbff3c12132d2eb6a6854e69c3681b'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/rejected-source/report.json', 'c6f173b4a68b5202cb1d4cfe79610ad9c3b71efb50f8cf5c3abee5e3f575b4bf'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/research-attempt1/prepared-cases.json', 'c011380c1cf5dda73ce98af7e8530e92b2e0f1faa1930a308d77d624b9d9503e'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/research-attempt1/report.json', '722657aa5f0788f5a9dbcbe41d0a021146a284560ffa6a89b210feae4762a056'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/prepared-cases.json', '235d218426e9a14fdc000ca2e81a64b00cac394f247d0c53029dc1c2e4c2b022'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/report.json', '22536f6031adc88eae4bb7e2ada4f9ff374a2d227e66927e084180552e12b073'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/research/prepared-cases.json', '235d218426e9a14fdc000ca2e81a64b00cac394f247d0c53029dc1c2e4c2b022'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/research/report.json', '22536f6031adc88eae4bb7e2ada4f9ff374a2d227e66927e084180552e12b073'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/run-prepare.py', 'f840c81fb3d6a86da5860be142d9ba768c8fef4f60a6db3cefdfaa35b688f52e'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/run-python.py', 'bb39945bd427067d0e03a9b7cd619e117739f6e24dea7e2f49d4c9043194bddb'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/rust-and-review.json', '594886c5a6275d479bcdec7ba75fcf039c994fb8c3f97ce479456e759ff3e949'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/source-diff.json', '958b5b447d59eec7e5a04405f49f375412c37ef307831a0e87502e0112af9f16'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/tool-source.json', 'c16b096fb7ef2ec1878097cfbcc8096d939a809a847d3da1f583114241e3579b'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/tool-source.zip', '66e5980442def848f9c3bf544320a31fb44884cdb98dccb52fe05cde95d245cb'),
    ('data/runtime/p1-prompt-probes-offline-2026-10-21/workspace.log', 'd1332e089dc6e63910d1f997f6f409333c8624c77eab97add4aac84dc11d6b49'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/acceptance.json', '5fda5ef58e8b45813af0a79dbc0459354a533eb08aa6ade03f5288db6bc00833'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/audit-attempt1-cli.log', '62a1adeaa7e8e0a3dd6eeb9add161c4246cf35842a67ab910549b18744134d8c'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/audit-attempt1.json', '70fcf0cbba140ad3541a3e79c70833ef2d0937f2dc2ca8169cfd233614ac82e5'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/audit-cli.log', '62a1adeaa7e8e0a3dd6eeb9add161c4246cf35842a67ab910549b18744134d8c'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/audit-final-cli.log', '62a1adeaa7e8e0a3dd6eeb9add161c4246cf35842a67ab910549b18744134d8c'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/audit-final-run.json', '953f0c8840be5d5aea80a26e2e589667a57099d83e89215e6fd309560bc48b14'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/audit-final.json', 'f76de5c71883b3df72aa55e308707174ec0264419c355796e4edf49ad54157ca'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/audit-run.json', '99cb914503f9c9ce29ff583f348dd37df2e518d33a8c5acbf49d9238e09c4cd1'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/audit.json', '141c00378aa371bb0344f93bc5ba90c410ca6b176e4c1e5acac0f603b3e1a8b1'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/before.json', '6c1e0eb7d4224b945d09b964623eb5bb1b72505c76bc6b9fa99f4fd9393ee1bb'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/clippy.log', '4ade3827c7c1e73d800a8dad948f4387d0102ea87a9a983e05a825eec6926a39'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/contract.json', '75008591ab7d00c56412a3694a9bab07ead8aac8a723ba7a51b1f3c9ad8f5c41'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/corpus-paths.json', '362a029dcde72a7448d61c28ff0ae32fa6f44abf4e5bcd3d0a025b35e8bc820a'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/delivery-checkpoint.json', '05941d82f0dbe740fbac9bda60213abfac2e4a7a08d03131b5339d665f85b30e'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/document-links.json', '9bf73a2896456079bfb16fa27f9b628d5c95d9683c6d9aca19a0f8d45159a656'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/examples.log', '692e4823ca89309a70c9b3a9ce2a27c88bbe245beb4d7bc32feeed912d1fbd82'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/final-source.json', '2eca18c30ab94a1c97f472953d77085d1d155f75dd2739725f52f0d27b75b1a0'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/final-source.zip', '09742d705fa3bb2b9907c20901c916db3836124ceddbad2bfad78e799838927a'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/finalize.py', '4d1e3a7310d931cfc28dcd0a0562181057e85a4910ec66491ed5d98fef3d422a'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/fmt.log', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/negative-verification.json', 'fc73d8214224530e6532b08fb5309750f44c68a3c1e4b30802d822ea01ec0e79'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/pipeline-final-tests.log', 'f2bdb91d7ed5152fb51b97372cc943883adb7af781101fe409225b0491006060'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/pipeline-tests.log', 'b94766da912c1a2b7ec83714d5342704d42a7707605dfa689f9fff9ec68c21cb'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/post-schema-source.json', 'b8488a773d4c26f13a7d1758b74955bfa24d9cb02b2ee904db75bd13dcbcee6f'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/post-schema-source.zip', 'edf8f4edf55bfc1ec98a812e42abe99932a7230e2f6f5e66878a9e0d63af3a9a'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/python-final.log', 'ace129061af0cb26452c09b86f8fe4e222133c1cba88606b94133367690188a5'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/python.log', '6aa0164097ec09bcd25802911f176abbf58ab7322a8abd5d750513fd5c6ac640'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/review-final.json', '422a81f677adc9ee28d6cef8d9b4c76dc77aaf2234a4d83236fca4cf182a2967'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/review.json', '3584e554ef86f12f06a1a025125c969a7c35a28dcb328b82aae54c9de543a1b9'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/run-checks.py', '5491c3283fc20cc5b6e816348ce3a34fc2243be5f6bdfbc0593a29f7a6a21ec5'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/schema-negative-after.json', '99a9238613509efbc1c0fc4fb612408353235b373c1c80644308f7a2c0d19398'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/schema-negative-before.json', '56d09c4278a69016cc00e053177196f0f0aea391830d1f104017a0d2352d4662'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/skipped-tests-final.json', '6fb94919394ab17a2ede0b850924591e96a1749968f67d5798fd310f77743086'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/skipped-tests.json', 'a2ec35c886e24f1a0aceaf328b84532a37b388e2b4f78ff91606e9c28ed5b8bf'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/source-diff.json', '5301ac702e0113de20a5350d4aa075337fd03839809dcf597c45ea6989a71e9a'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/terminal-action-negative-cli.log', '1ee5f78c620c2f20c1b963cc0a3b661d74849b0e124e55f5b01d55d97aeba2f7'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/terminal-action-negative-samples.json', '4c8b7ce95281e784958f8be81925e70628e3f9ce7e6a9c238f622c44f4fc8232'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/terminal-action-negative.json', '6627d3e2410472c3875e911c0bb54a4d9ccd3df12cb84b50b37f2548ecb6afcf'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/tool-source.json', 'ecd25e192e0222f2cad1cca9b2c73ecfced33f174c449153380e48d553a2f3a1'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/tool-source.zip', 'c716abe04b7784ae8007a8c166f14f15aa3c305bdabc696f2aadb4df88d1a9ae'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/validation-source.json', '478dad10d5fd45703443e80a2b09de7d51ae6c046386e4b7feefc3545856754a'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/validation-source.zip', 'cb687c0cabd495706f4d4348f7487daea12dcd049a8fc03bd4cbbf45f5e7f0b1'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/verification-counts.json', 'd8156d132c9a94485a73f222451fa6865e710cf2946f5e657749480bb98e7d4d'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/verification-final-counts.json', '2162071c985e3c41169141f3607565e248e63e30c70aaa3f8693e38cc08a50dd'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/verification.json', 'd250b43a95752a52fa52cd0bbb0fbc9d58d665f94d94553428cd32c10fb0fc5a'),
    ('data/runtime/p1-shuffle-route-offline-2026-10-21/workspace.log', '101292b840524b1d58f90496bf90a1985c678a4fe193f0f024e108e9c533d0f6'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl', '0e50a03837676b8b19a1409b9ffa06bc7798ff61254109c10025c7733a3c410b'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/0096581994be19db6093ccb0c05f4e7332ec585fd73c5deca3ffb1ad5b2179a2.json', '0096581994be19db6093ccb0c05f4e7332ec585fd73c5deca3ffb1ad5b2179a2'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/0d0a46c18503bd926de88b2cd6596eb3d77fe92cb403feb900c8b1b4bc1a6c42.json', '0d0a46c18503bd926de88b2cd6596eb3d77fe92cb403feb900c8b1b4bc1a6c42'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/0f480095a0ecb0030357f4cbeb7ff30cb5c2079f1d80743ef7553732e1fcc64f.json', '0f480095a0ecb0030357f4cbeb7ff30cb5c2079f1d80743ef7553732e1fcc64f'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/108627d162c4df55de15d584141be85700efc1188debb36bf5f05424ae98fc0c.json', '108627d162c4df55de15d584141be85700efc1188debb36bf5f05424ae98fc0c'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/1ac8feb88e94f7d8e149489910085a2a5cdaf22c5e85ac3d0751fe3c8ba34f6a.json', '1ac8feb88e94f7d8e149489910085a2a5cdaf22c5e85ac3d0751fe3c8ba34f6a'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/3c7633ebb1b420a91a46ddf607e21ebf041178d7bdc98f52db377773268824e7.json', '3c7633ebb1b420a91a46ddf607e21ebf041178d7bdc98f52db377773268824e7'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/6da20460081cc6c12b3fb8f23a4fbf67987489e40f37a9fbb131f76d633c5851.json', '6da20460081cc6c12b3fb8f23a4fbf67987489e40f37a9fbb131f76d633c5851'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/8758e274cf90b0766ea7d445721b3e780972c9501462cde1a05d5f92448dda59.json', '8758e274cf90b0766ea7d445721b3e780972c9501462cde1a05d5f92448dda59'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/8ec93178fed913a769418feaf9d765ef283baa5f9200c927a00df2ca56c24f77.json', '8ec93178fed913a769418feaf9d765ef283baa5f9200c927a00df2ca56c24f77'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/a10ceaa3be4a7631d1df4de4f741614e446ecd57485b3d7763d6a5d8e7d0a4a5.json', 'a10ceaa3be4a7631d1df4de4f741614e446ecd57485b3d7763d6a5d8e7d0a4a5'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/a9978f1d4cff10190eb05a9e5d482312f6d00b36ad7d4f9d85b26fc714682500.json', 'a9978f1d4cff10190eb05a9e5d482312f6d00b36ad7d4f9d85b26fc714682500'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/aa728fbd0c4769e62275c43014940040a11292fb0fd36fcc885e7e0f47ff81c8.json', 'aa728fbd0c4769e62275c43014940040a11292fb0fd36fcc885e7e0f47ff81c8'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/ae2e4f1702f451fc26f6842cd231929f4368a6b2afd7692e903bfbb9aec983f4.json', 'ae2e4f1702f451fc26f6842cd231929f4368a6b2afd7692e903bfbb9aec983f4'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/d9d5b4e28f1e67035c15a12443ee0406b26a2a917ddb64fd2244ee34dfdeaa90.json', 'd9d5b4e28f1e67035c15a12443ee0406b26a2a917ddb64fd2244ee34dfdeaa90'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/dcf257d453a7795cd98a39c2b037dfeefdbaa3dc2b3e856965aee15a6afd6db9.json', 'dcf257d453a7795cd98a39c2b037dfeefdbaa3dc2b3e856965aee15a6afd6db9'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/f88b2c886391994adfea466b0cf65581e635e7126e8acc8cf4f5ecedb1f67f6d.json', 'f88b2c886391994adfea466b0cf65581e635e7126e8acc8cf4f5ecedb1f67f6d'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/f8d5463940ff2a8d4f17f7a628a1477a20c88f5836f7445efa7d1852c4e29351.json', 'f8d5463940ff2a8d4f17f7a628a1477a20c88f5836f7445efa7d1852c4e29351'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/events/0d29df2ab3f939b12abcf78384a7343a0bf5005a7c5179716d9d6315b705e317.json', '0d29df2ab3f939b12abcf78384a7343a0bf5005a7c5179716d9d6315b705e317'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/events/4eee261c8b94f5b143a1ede4e345db9f091147daba9a7aba103a2fc129bdc6fb.json', '4eee261c8b94f5b143a1ede4e345db9f091147daba9a7aba103a2fc129bdc6fb'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/events/5c20de4d7a0206ae2a71ebe9ec705627d595cf5e0ffe2a06c84e3b433a84e7b9.json', '5c20de4d7a0206ae2a71ebe9ec705627d595cf5e0ffe2a06c84e3b433a84e7b9'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/events/646fb57bec20ddc8d62f31ba972ffbdd94a8e18feb218ad0e1cf57a4ec522abc.json', '646fb57bec20ddc8d62f31ba972ffbdd94a8e18feb218ad0e1cf57a4ec522abc'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/events/76fff6e31e4a7c62628f7cc57f064ac8f5597693d66d0e9d25363999736aa036.json', '76fff6e31e4a7c62628f7cc57f064ac8f5597693d66d0e9d25363999736aa036'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/events/b33d9cf490a5bf519997869d974ecb0822829c67651329dbdcad6a2f57b621b2.json', 'b33d9cf490a5bf519997869d974ecb0822829c67651329dbdcad6a2f57b621b2'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/results/01eaf40274c7a00a730bbb6710fc65b0098b9d787bb86f98c30168e7dc99ad92.json', '01eaf40274c7a00a730bbb6710fc65b0098b9d787bb86f98c30168e7dc99ad92'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/results/148e7f2eeeaf9b7fd4bf394b45955e819e16d614bfaa204d441e7d5699ff2a9c.json', '148e7f2eeeaf9b7fd4bf394b45955e819e16d614bfaa204d441e7d5699ff2a9c'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/results/3f2157a1d4ed185a84118509e5ab9f270281cdd1859b89f4656035134dcc90a2.json', '3f2157a1d4ed185a84118509e5ab9f270281cdd1859b89f4656035134dcc90a2'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/results/40b765809afe79479bc3d2b98ff72747ea546b87190022b9057dde54fc82e9a6.json', '40b765809afe79479bc3d2b98ff72747ea546b87190022b9057dde54fc82e9a6'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/results/b080a01ce2996bef384c575778dedea23ee672f6c2abcfee6f7e09bbe7b44b64.json', 'b080a01ce2996bef384c575778dedea23ee672f6c2abcfee6f7e09bbe7b44b64'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/results/bbba08843a3bfbace171c298076fc02f86719514c8824768abe2a6278820556a.json', 'bbba08843a3bfbace171c298076fc02f86719514c8824768abe2a6278820556a'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/results/bfd6502192f0b616c8450c082000f8bd738392267f935c9bbcde058cfea17173.json', 'bfd6502192f0b616c8450c082000f8bd738392267f935c9bbcde058cfea17173'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl.blobs/results/e9266d134176f5e53f074efeab7dc0360f5d5188dc950c3f5419640753e76ae4.json', 'e9266d134176f5e53f074efeab7dc0360f5d5188dc950c3f5419640753e76ae4'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/rabbit-empty.json', '3d05204902a41a6cf6e1c285dcfcda829eed46fc998a6a34307eabc7cdc86362'),
    ('data/runtime/p1-state-native-2026-10-20/research/native/rabbit-shuffle.json', '37b4027a6e670cf9a01e2462899a42acaa1fceabbda9dea04facb78e845a530a'),
    ('data/runtime/p1-terminal-2026-10-20/research/native/calls.jsonl', '3fd2aa6d1ff18f5eb1fe7100fe8fb4c36e9b73795e0749aa362b0bea9ea93ef2'),
    ('data/runtime/p1-terminal-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/0984cfffd169a38788899f0ce455808cbd956608f7222eaa8e0303435e9cf926.json', '0984cfffd169a38788899f0ce455808cbd956608f7222eaa8e0303435e9cf926'),
    ('data/runtime/p1-terminal-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/4c7318de554ac2db97b206cd95101429740edf18b8d77affb725830fe170c296.json', '4c7318de554ac2db97b206cd95101429740edf18b8d77affb725830fe170c296'),
    ('data/runtime/p1-terminal-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/99c0dd8ef276ef78ea998841139245ae464aad9686bfaeaba14da79d9b5f709a.json', '99c0dd8ef276ef78ea998841139245ae464aad9686bfaeaba14da79d9b5f709a'),
    ('data/runtime/p1-terminal-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/e02a884ecb000b3bcac4f10b961e85c0eb620ad1104a3b8aef146436ca66f2bf.json', 'e02a884ecb000b3bcac4f10b961e85c0eb620ad1104a3b8aef146436ca66f2bf'),
    ('data/runtime/p1-terminal-2026-10-20/research/native/calls.jsonl.blobs/events/646fb57bec20ddc8d62f31ba972ffbdd94a8e18feb218ad0e1cf57a4ec522abc.json', '646fb57bec20ddc8d62f31ba972ffbdd94a8e18feb218ad0e1cf57a4ec522abc'),
    ('data/runtime/p1-terminal-2026-10-20/research/native/calls.jsonl.blobs/results/d49b1d53d65bba092d69c001eafdf6fe36d9b64a9e89bf662dacb4a8bdea8541.json', 'd49b1d53d65bba092d69c001eafdf6fe36d9b64a9e89bf662dacb4a8bdea8541'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/acceptance.json', '737d97e912da5af282acf29d75361e9dec5ffaf06b019dfa43736a21bb3fbe49'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/before.json', '127bbcff1142ec533630fb78da2090f44bdc721c5b81b19d530ae698caaecd4c'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/build-archive.py', '9607da83a61a1a62ef2dfed4bbc0810cc055819cbd68ce6f8aedd9ab6ad75392'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/build-final.json', '128dec8f7fee4cb67b48ce8f3f6d1666c386296ee3194a65aec097981bd12fdf'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/build-native.json', 'f95babcbb16251a2db6a4bf55774fc98587d06d6c36d8860633fc1230ab5835d'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/clippy.log', '9c8242d9a38678766f1cc1125bd4156207b2837a5a0ba236de4e5371277293ad'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/document-links.json', 'f6d2a4ed707cd7ff65e42a5acd8dd17c58ffe78481cc36cb6b44eae3481d74ef'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/evaluate-pairs.py', 'b1744ba2cfb8e126e40995438b2b47ed0b11874b3c4e016710f2194116f682fd'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/examples.log', '7355561d96c4e727381595c815b228be76a890c1100ce394cfedef9d08f02ada'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/final-source.json', 'f3ec3d26e15cfbf74e2952f701baa914a000d3e1ec1329d3cff3c8a37e0c0f3e'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/final-source.zip', '4093766367b96a20acc09068b8f3749bbc3bd30a479bbadb4a893128084a09d2'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/finalize.py', 'ac4286fb6b907464bb8493b368f518ca67fbb488620eafd9ed0a356d5733aff7'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/fmt.log', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/historical-receipts.json', '5239729ba8f949af4b9be32888b0edc3acd4b4068686f0e1817b1689985561db'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/history-audit-cli.log', 'e3adca3110d81ece8f1438b48c9e0273b24f2ceb8eb3210e58180ee7ecd7411e'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/history-audit-native.json', 'f6ced1f251cfba06204d124d90c57678e13f5e2f363e6ecc532fb8b951460362'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/native-artifacts/terminal-evaluate.exe', 'f5d94b180304b2198b1b2e6b1a32bfb0e4d43b3016ae6eb72b3748c529955b13'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/native-close.json', '5bb2a0555ef514a74c82efe90d1c907ef6b219c7cc1fa29dab0320104312c7bf'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/native-end.json', '06dcc4ac95d003786d3102a83ba34de480fc042253f3f174f921ffd6ad8a0f2d'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/native-evidence-review.json', '77cde4d2f4c4294b6c70d2fb71315c532421a2131b99f745db44ab88e6ee8c8d'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/native-execute.log', '9545a1448e4cd63488ace7f977e4369eb2d50d8054f349ed40920ddc8ca82e51'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/native-receipts-final.json', '8e331ad0ea14e9e2bdd80bf44ad6338f70e31de9159d379ef7ec135add9f91dd'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/native-receipts-native.json', '218bb821563d4afeefbe7fea680ba99198e809b22831190b09e7834ab74baf9b'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/native-source.json', '01fa146707ad53c94b2eeeb425cfe5470d64df3e947fcb2988fff8d1480abb98'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/native-source.zip', '3147955b1ee941848afd8bc3c68e0e0035ee89eb9c3fae8b7dd9f97fede90eec'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/ordinary-candidate.toml', 'bcb60daec0f12b87e0019424832396ffc282ae294a97c17053dccf5bf2d705df'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/prepare.log', 'd9e83036bd3f98d60a6783fc70c072fcffbfdfa957f4f06b553793105e517bf2'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/python-final.log', '0447415161675d28076adbb56ef0fae491910cf0a488a214afa40e172f5a8438'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/python-frozen.log', '5c2360a3bb9f7eef34fe3809313f4427cb7bf65865f2b1eb769b1c8a86e37870'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/python.log', '46f5e161e5d94bce93a614791f0594abb63e16f7b04f06ebeb14bec3d1f70997'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/research/evaluation-terminal-shuffle-end-final-default-v1.json', '8e536ff882fcadc0e544415a361b57b242a3814744e164402dd96f3c6138c0c1'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/research/evaluation-terminal-shuffle-end-final.json', 'a5f9c6067e538cd7395b2ad5e6eb2e280375a555e16edd56a0bf7d28a3bdde04'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/research/evaluation-terminal-shuffle-end-native-default-v1.json', '559649b6fe3391c80b227edb8b6404caf413d1386f6b34aeb49fb08e9f487246'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/research/evaluation-terminal-shuffle-end-native.json', '5e7cf2f02037db84b98df058e276a4222ab7e05ed2082e8085959a00158b8a4f'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/research/evaluation-terminal-tournament-final-default-v1.json', 'd9e9ce6f9096aa02a3e258f29a3aa8bc3ca977fa0d710df68e851220957e8cd0'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/research/evaluation-terminal-tournament-final.json', '3b8a56d18f1f2a3b0c08f2a8794014034600949b02a4692c7ada5c95e6213cad'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/research/evaluation-terminal-tournament-native-default-v1.json', '05ed49b7ddfe6768d693ea6d0fd26a4f7b332e4de516f1c7f8269c4cd9fdf7c5'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/research/evaluation-terminal-tournament-native.json', '9811013b4854f3394f032c1888a47a240a6eb4c18319c3876be3ac8829867380'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/review.json', '80c6ec7f4c4233c0e639600b05ed9b222c1b79a4b3eaa168cff3963da8f9b4ef'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/run-batch.py', 'a35578affc5d7a58171cf2ce8438b8bf957eba9662491566c10331f0698c1208'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/skipped-tests.json', 'a8e57344bc4b1db8d1732838922c5f481312536f5b7f5a68a50445da64541dd7'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/tournament-candidate.toml', '49ee1b57d20e3718f49fdea53db29dbdfc645e149e1b6c285499df32aae569f0'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/verification-final.json', 'f0fa86716b90ae76421f64b228cc42744a6e47f2de61373aabb8da52bb1c544c'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/verification.json', '76f13c8e2bde891bb7964a84836b9c3e7a4f1d61f3e54d520a5f65c529efeaba'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/verify.py', 'a509fd7c5afeb2e81e1b2af070abf470c2df525e9de01c9ba4578e6555c1835d'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/workspace-final.json', '3bf9d0aacba8c9cd534edaac7a0d459b4be9f5c0988bb35fe52820055d3fe9f7'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/workspace-native.json', '21c965b855355b77a0d90de03e5330797825aff35e8ee5a11dfaea96250132b5'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/workspace.log', '19fe9bf96727826208a6fcf20ac29dd0d409251eb1e5425b00ff2c42d6b1320a'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/zero-call-resume.json', 'b68a113effb3481354deaea1c7159017804f36c17a4ff8389fc629340d79665e'),
    ('data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21/zero-call-resume.log', '9545a1448e4cd63488ace7f977e4369eb2d50d8054f349ed40920ddc8ca82e51'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl', '68b134725597f62a888dd182b25bb0fb16cb2dbfcaf5154009b2242dc4bcc473'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/1cc848efdd0c221bc75d54b0f8b91681520db7b1c03ceb0b7eebfc3ea857a845.json', '1cc848efdd0c221bc75d54b0f8b91681520db7b1c03ceb0b7eebfc3ea857a845'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/43b3a1645e6bc747e3d35291bb1b6988ea20e67ad8bdcbc609a51a9d96871578.json', '43b3a1645e6bc747e3d35291bb1b6988ea20e67ad8bdcbc609a51a9d96871578'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/6ab73e54305c26fafb6d399f3d5e1316e20e1589322b84fe91eb6a27fae36a2f.json', '6ab73e54305c26fafb6d399f3d5e1316e20e1589322b84fe91eb6a27fae36a2f'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/748e1286ec2ddecb53c08ff055ce9a88e6c5a8b7fa3f48a63933cbf1aec42c78.json', '748e1286ec2ddecb53c08ff055ce9a88e6c5a8b7fa3f48a63933cbf1aec42c78'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/c070105e1c9038b61e255d638d7b44a27de36448a5cd388ed43d684968fae65e.json', 'c070105e1c9038b61e255d638d7b44a27de36448a5cd388ed43d684968fae65e'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/cd9ff073b2d87dbc90e4a68c22619e75a088d1a7e0611b8ef3e602386aeda9eb.json', 'cd9ff073b2d87dbc90e4a68c22619e75a088d1a7e0611b8ef3e602386aeda9eb'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/eb065167176b420f74224165cf03508c19472b0cc6912c7f4491fb5f9ff19b0e.json', 'eb065167176b420f74224165cf03508c19472b0cc6912c7f4491fb5f9ff19b0e'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/f26706222e6438a31b96b02bffcaae88d5f364bd03a6b181b3af7e716aa3f0ce.json', 'f26706222e6438a31b96b02bffcaae88d5f364bd03a6b181b3af7e716aa3f0ce'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/f5ae42c670a626c4c17f38b3b0a043e17941258634a543ed3ec2bd8a3f472f70.json', 'f5ae42c670a626c4c17f38b3b0a043e17941258634a543ed3ec2bd8a3f472f70'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/events/0d29df2ab3f939b12abcf78384a7343a0bf5005a7c5179716d9d6315b705e317.json', '0d29df2ab3f939b12abcf78384a7343a0bf5005a7c5179716d9d6315b705e317'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/events/389380369d33ea67107c4389908072de9b22965a9031e2346d4b2c13519232ca.json', '389380369d33ea67107c4389908072de9b22965a9031e2346d4b2c13519232ca'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/events/76fff6e31e4a7c62628f7cc57f064ac8f5597693d66d0e9d25363999736aa036.json', '76fff6e31e4a7c62628f7cc57f064ac8f5597693d66d0e9d25363999736aa036'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/events/b33d9cf490a5bf519997869d974ecb0822829c67651329dbdcad6a2f57b621b2.json', 'b33d9cf490a5bf519997869d974ecb0822829c67651329dbdcad6a2f57b621b2'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/results/0f741dbf90518c645c7bf4d8ec67604ee42ccb78bba4059eea687e6ebd96ac0e.json', '0f741dbf90518c645c7bf4d8ec67604ee42ccb78bba4059eea687e6ebd96ac0e'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/results/2d6c1b15b0ba16298c6ace44fc4c0c8fd0999a0418a369b2363f573fef5b14f1.json', '2d6c1b15b0ba16298c6ace44fc4c0c8fd0999a0418a369b2363f573fef5b14f1'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/results/cf349d3c59a643894c9b7ff9e7b9e25e3b02685ae8e81eb36df34c2309a8a92b.json', 'cf349d3c59a643894c9b7ff9e7b9e25e3b02685ae8e81eb36df34c2309a8a92b'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl.blobs/results/e6762259332ef0e8a66289c41af755c92b2cf5812aac44d081465a894a95284d.json', 'e6762259332ef0e8a66289c41af755c92b2cf5812aac44d081465a894a95284d'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/manifest.json', '46a4649d57c1a8d090ab36222322e93d0bee6ec4c3e896fb4553b0573e17d752'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/summary-61728604e2a9fb444a2abd082789cfb06e3a45ce8c1d477d8ab1407df0364bc0.json', '61728604e2a9fb444a2abd082789cfb06e3a45ce8c1d477d8ab1407df0364bc0'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/terminal-shuffle-end-input.json', 'bbdfb7da81bf87b6e3c9bf898922c21d221f506604d1a653aa4c26a26bfabfb5'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/terminal-shuffle-end-request.json', '0831cf62ec6587625543e946658be21c58b2aab30d73aedf1d3249597b2353f7'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/terminal-shuffle-end.json', '3b391ca175f00910570fde0542a95970c028bc85b7c6623fee01d4d71e428dc7'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/terminal-tournament-input.json', 'd77ef9495c3155bb36289159623f7fc7fba3f8f6195551ea15d56421e5e00f2f'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/terminal-tournament-request.json', '8af1d9ffaa5b470a13a3365c46075d962c788a6cb6dc9383dc00adcb04939d5c'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/native/terminal-tournament.json', '6eb9199124e344356af387c31f83e2955187b0dff1919a4847923258cd9ea059'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/window-start.binding.json', '2bcca8f766c9327449cc775181941ae556e7cf37acb78851db93c89affcedb1b'),
    ('data/runtime/p1-terminal-followup-2026-10-20/research/window-start.json', 'b95a4137d8b0cf77cea8d5b02ae21df2c27f1f9548070e2e4f80db4671cf61ef'),
    ('data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl', '624b4843dc9cd09e07588074b2b4ecbd91737316c70e922a183f0dd9a5f137b0'),
    ('data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/1dec0f52f55110d24ca348b3d7f0829c48f77b3ef71959eb73558ca74cd99604.json', '1dec0f52f55110d24ca348b3d7f0829c48f77b3ef71959eb73558ca74cd99604'),
    ('data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/2609670e9d03a6fb6c26e766a491b4fe466327aceb73f2e28f51f2602a03a742.json', '2609670e9d03a6fb6c26e766a491b4fe466327aceb73f2e28f51f2602a03a742'),
    ('data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/4a52729d288e7811c89e55f15b30fdf5a4e88fa592f240f41476ad499d32189b.json', '4a52729d288e7811c89e55f15b30fdf5a4e88fa592f240f41476ad499d32189b'),
    ('data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/9130a7a4dd3b882e83e2796719fb13b407e683a49cb81849014fb0d01f517087.json', '9130a7a4dd3b882e83e2796719fb13b407e683a49cb81849014fb0d01f517087'),
    ('data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl.blobs/checkpoints/dd096c9f97b4587273021cb6a11cedf07355c71604dedbdcdcfc8688678de9f3.json', 'dd096c9f97b4587273021cb6a11cedf07355c71604dedbdcdcfc8688678de9f3'),
    ('data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl.blobs/events/646fb57bec20ddc8d62f31ba972ffbdd94a8e18feb218ad0e1cf57a4ec522abc.json', '646fb57bec20ddc8d62f31ba972ffbdd94a8e18feb218ad0e1cf57a4ec522abc'),
    ('data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl.blobs/results/01ba55970d585e005f29963646ebeef9edb9ad7ec592414053682648e8b6ab56.json', '01ba55970d585e005f29963646ebeef9edb9ad7ec592414053682648e8b6ab56'),
    ('data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl.blobs/results/6215e756c8eb5657ccc6da3d8e8c47bcc11717300f264184d7f0b2f679296faf.json', '6215e756c8eb5657ccc6da3d8e8c47bcc11717300f264184d7f0b2f679296faf'),
    ('data/runtime/p1-terminal-smoke-2026-10-20/research/native/terminal-rabbit.json', '1f40071c55e16a346d26e0aa51fc829e8c75a5eefede064b7cfe76e76310be97'),
    ('data/runtime/script/official/c57103969.lua', 'f616f84335cdc031435b491d078cb6b49660959075d6e95307f143f354bd2f65'),
    ('data/runtime/script/official/c58074572.lua', 'df0569217bb3659ed774d21a158c86bb9aec65bca7f5725f03df97b479c5f9ac'),
    ('data/runtime/script/official/c90502999.lua', '67d95d32e1b6023c41516b0f15657af60121aa5b072dc85bb273fc1280912497'),
    ('data/runtime/script/utility.lua', 'ace5e7811d8e9863ba0604cf7d90747e4ee010e11d30c4e1ebca29e82a5cb13c'),
    ('data/runtime/scripts.json', '69bf6f9d3fe444fd53890c60bde877f97b753f8d3e218a6349615d09f6740d91'),
    ('data/snapshots/.gitkeep', '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'),
    ('data/snapshots/active.json', '81824634073c0bc515d4716db477b40103c974a649dcdb196c5fbbf801f72879'),
    ('data/snapshots/banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783.json', 'a6344cd77c4db6dcfab02d03110954fa1c2717422f71da302970f427564506c9'),
    ('data/snapshots/catalog-1b0564fd61eec4730828fea1d48391aa1598bca3157c255454a8dcf487485d6d.json', '3c0fa6249f4e5172488bf325f8d659070cfefb3d93115b7ec690e0486da4cbf7'),
    ('data/tmp/ocgcore-source/duel.cpp', '5c40deecee0047b5d2ba51031dd545eb89374ff5194c10a893bbc9c07fe257c1'),
    ('data/tmp/ocgcore-source/effect_constants.h', '6d14bc8ba1a1aa955815266fcb3db8b49ebf8174385bfd885a881f899c7041c6'),
    ('data/tmp/ocgcore-source/field.cpp', '9b6aa4916a8e2f7e95cab570be886e22751c197b320f15acdf1fa7de3c5dadfd'),
    ('data/tmp/ocgcore-source/ocgapi_constants.h', '191315f0c37bdc2fc086dee457bfc8ebb10b27cb1f063d26d5776465f9dbc4aa'),
    ('data/tmp/ocgcore-source/playerop.cpp', 'a9ff2c499476f70afb4afa9d3880a0070bcd54f4baf9f116cd9e79f7107c9e97'),
    ('data/tmp/ocgcore-source/processor.cpp', 'd051d6a006baa9ad4a590d4bcc185bff112e3ed7df256ff25cd8c0ff7beaf085'),
    ('dist/ygo-local/ASH_STRATEGY_PLANNING.md', '5a8be2bd50f57913790daa099bab9d8ae3e7e009f66df04fe929a5bbf17f1523'),
    ('dist/ygo-local/BREAK_SWORD_VERIFICATION.md', '2f5c27c062e2d4818549d986da564f606e9272f2fdf8403b08375cc273acd1d7'),
    ('dist/ygo-local/DEPLOYMENT.md', '0d3e2ddb66e54f27f140e412b8360bcb147742ac0334e5abeb292278825e8559'),
    ('dist/ygo-local/GOAL_PLANNING.md', 'f2b660205a05bdc12e5b2db5a5bcc2fe6fad6848ac6b11d28b2ed822b17064f0'),
    ('dist/ygo-local/RECOVERY_PLANNING.md', 'a44f50ae4064ff07cfda41c715c8d2bdbbe32d67ce4d02e23e1ed1e282a8fd23'),
    ('dist/ygo-local/SEMANTIC_PLANNING.md', '6a9e439b41f89b8c068bc0966db2d56abfb3119c7f0c2ae6ed87d25f6c63f179'),
    ('dist/ygo-local/TESTING.md', '32d9866dc20ad0db3867c5483c8b93495b0b30e482f882eaa6617eba2df7a626'),
    ('dist/ygo-local/build-hashes.json', '9087487fd6af97885c8d55968cf9f95d0480e1fa6daef70b680961f779407baf'),
    ('dist/ygo-local/configs/engine.example.toml', 'f84b1ac649e6677248082807ead2f3987f7c81ce0e9cecba9ef80139671c3409'),
    ('dist/ygo-local/configs/engine.toml', '3b802b320b714f02e13c88c52372247ea81e5991a864cf58f946d300dfb2844d'),
    ('dist/ygo-local/configs/scoring.toml', 'cea84439b296b7dd14fcd433f63959ae66e7fa1bc0deaf71dd9a0763db7c49a4'),
    ('dist/ygo-local/fixtures/ash-recovery.cases.json', '3849797035936843317d7aa6a4546d5d7099d947001591e2e17f42206f7f3c6b'),
    ('dist/ygo-local/fixtures/ash-recovery.request.json', 'c3c1adf6ba831b4eedf35135ee6a0f6890ef07dcc00eb3ffef108f28f8180b75'),
    ('dist/ygo-local/fixtures/ash-strategy.request.json', 'bd33eb4e91d56237ea2d671c8c4565f268350b058f00a601a8263d79db0069e6'),
    ('dist/ygo-local/fixtures/break-sword.request.json', '5cb82fb66202111eef413b03fceec6f44bc18617969517c547099ce022988e47'),
    ('dist/ygo-local/fixtures/goal-availability.request.json', '063bec9143a04b308f0c622f6fd295ba9e144da1ed71218eb2d5adee21d9227a'),
    ('dist/ygo-local/fixtures/goal-break-history.request.json', 'a421b74157e1987d529288c83db2ea778303381a6dd7bddf202e409e7737128c'),
    ('dist/ygo-local/fixtures/goal-budget-partial.request.json', 'a91575dd9215cb8c08970f11f98678a4016bf4334c32877f8e9f62110324df95'),
    ('dist/ygo-local/fixtures/goal-budget.request.json', '98c2fc60a0cca9c7d9628654211144deadbc41a73158c2f0a514432935d581a1'),
    ('dist/ygo-local/fixtures/goal-cherubini.request.json', '5a39252254c6d5ec632f4ba854697b5878b67ccf220c4b9ec8f694e16a0c7fd7'),
    ('dist/ygo-local/fixtures/goal-continuation.request.json', '3e6d20fe3b6372fe28d45ad84c00a3bcbc42f099ec5e23840b9c1daddd01aa6c'),
    ('dist/ygo-local/fixtures/goal-initial.request.json', '5763115858785469b38d859376de5d49eb959fb030e5a3727f0d54787eaa10f6'),
    ('dist/ygo-local/fixtures/goal-no-discard.request.json', '8c348a19c551804e0162541bf874b0c09e54b6685a28c410169240ff4abbac97'),
    ('dist/ygo-local/fixtures/goal-no-target.request.json', '874512dbec3ddfb104cb1bfa222820db6ad3eb01a927e84c40fcec0fe71aa15f'),
    ('dist/ygo-local/fixtures/goal-rusty.request.json', '5b07b6808a78ce3ce10154d7b9b240ac9af0c2cb80a32083b859f3264774dedb'),
    ('dist/ygo-local/fixtures/goal-shared-resource.request.json', '7184d5f31d48f879560efbc12598a2bb963ff6e99025d1634242a957724df322'),
    ('dist/ygo-local/fixtures/goal-short-continuation.request.json', '14c17866f971706e542b2715458f74b794533efc63bae2756fc5e2f3da5ffd9f'),
    ('dist/ygo-local/fixtures/goal-unsupported.request.json', 'c7ad589b115c480206f59d1d0f7afd0598952be8d655c7a6ac280f6dc7c03eda'),
    ('dist/ygo-local/fixtures/goal-used-effect.request.json', 'e2c810ca604cbf0614f46e0122e82309f1e95638951ca3f7ed5cc1a25550364a'),
    ('dist/ygo-local/fixtures/phantom.engine-cases.json', '0c0efca5f9fed2fdc913643208ad523d65de594df6cf27b9aa15831994b3efb3'),
    ('dist/ygo-local/fixtures/phantom.fixed-hands.json', 'aa6f057dcd6285735a6ce1b97e3efb05c353502463469fcd479ce5393ab55f5b'),
    ('dist/ygo-local/fixtures/phantom.request.json', '4fed0b965495e4e7795a456013d06a4e74dd2a0fe1c136cf26805717a79ee0a6'),
    ('dist/ygo-local/fixtures/rabbit.request.json', 'bd5f0427dbd68583b203702a9c8950e2263791c3a62b2685ca89773ea1631378'),
    ('dist/ygo-local/knowledge/phantom-v1.json', 'f1bc86de6bd2e0e7a7672d3561a47fb4d4bf40720972b9fcc8e2f13711750467'),
    ('dist/ygo-local/knowledge/phantom-v2.json', '919db1d36ac3e92362a4591dd26f68d9635e8c0c917af34db9325a34e2804e04'),
    ('dist/ygo-local/schemas/banlist.schema.json', '298d4b87673862b32db9ffa2d2470746fd80f15faaf67b2ca42efe7f2c6f2e4b'),
    ('dist/ygo-local/schemas/card.schema.json', '922cc9075a299c2f788dd5267d8acdad10e7af8e29def245a607388789dbba33'),
    ('dist/ygo-local/schemas/catalog.schema.json', '087e5188f1d132eedc96969a3472e73296c3f7e9684b5d123459b75808019155'),
    ('dist/ygo-local/schemas/combo-request.schema.json', '2d813522a3891ac16273f73c96328ac114cc36241a100d314ebe1e5c163ecda8'),
    ('dist/ygo-local/schemas/combo-result-v3.schema.json', '70150aa8c280843e4ddc47e8368c9cc1f4d1acd7cec3e5eaf3e63a23eeb8148d'),
    ('dist/ygo-local/schemas/combo-result-v4.schema.json', 'f06f65b384c217a5a68b0b48a5c1ec392769a0432f4d45475fc4af84f72b7fda'),
    ('dist/ygo-local/schemas/combo-result-v5.schema.json', '3331e44340895650436b31fb7ed20457de2f4758afdeea1e6726b08ca5cfb7f1'),
    ('dist/ygo-local/schemas/combo-result.schema.json', '4c4cf804631a817e08c7eb6a34ce5b6e68fd6c0646240ab9251a128567649fa5'),
    ('dist/ygo-local/schemas/deck-request.schema.json', '4a6e1f38762811637fd67f53824020c1884f6057d80f656839eb986c43fde4bd'),
    ('dist/ygo-local/schemas/effect-cases.schema.json', '5fac92809072d891ab3b607f42c35eca162aeaa8bb9a83179258906a609d53cd'),
    ('dist/ygo-local/schemas/effect-verification.schema.json', '195164318c367a9b8f1cfa85085f0c22d56bd4531408e6d60cb48cd0a9ed13d4'),
    ('dist/ygo-local/schemas/first-turn-cases.schema.json', 'd1191ac98a352d1a9a3238b8d3702d76fb4a7b0190d48a8cb942316c23c4549b'),
    ('dist/ygo-local/schemas/first-turn-runtime.schema.json', '40d5f719428c6bf221c44c94a4ef0ed1ea8a98ef74293a331384b8439a4f6a49'),
    ('dist/ygo-local/schemas/first-turn-verification.schema.json', '4631f4abe19ded4a67ea49b6384e18435780dadfbcf10c111178706d355e8da1'),
    ('dist/ygo-local/schemas/goal.schema.json', '305c7c8968e61225d68a591253e1ffbed44a1e68bce59fc287883adf880b035c'),
    ('dist/ygo-local/schemas/knowledge-v2.schema.json', 'ad0cd4d0c9588f5abdfb41bab8248ca278d6af8c0ca9cd3915da0c8b7775fe5a'),
    ('dist/ygo-local/schemas/knowledge.schema.json', 'a2aa559a9f8bc6dc61122ed76329487fc9c937a3ac2ec94e5450cf00aa508468'),
    ('dist/ygo-local/schemas/plan-arm-v4.schema.json', 'e4c95a944164b17b06553587fad5ac08c305f197f8b05267e21231ed0217a7cd'),
    ('dist/ygo-local/schemas/plan-arm-v5.schema.json', '2ca5ba511aa09a29ca7c7bfb75c8e6fcb1d6679a01a3f2450c8c7e8cc68838d7'),
    ('dist/ygo-local/schemas/plan-request-v2.schema.json', 'aa8f7df01a40f16f86ff99ef2b9514f7fc2a4abbbd6a3f9be5f4a775362c9bf4'),
    ('dist/ygo-local/schemas/plan-request-v3.schema.json', '04f01ab2f17370768bdaa6d4c67af276a18088d084507bb28113dfc7d56ed419'),
    ('dist/ygo-local/schemas/plan-request-v4.schema.json', '8747f6b7a98234f0038e4cbd144b18c53ada6f0f96241ade10166db7b05907da'),
    ('dist/ygo-local/schemas/plan-request-v5.schema.json', '3661ae627607cb98bf44d45c96ab9cb07d56d0ac312ea140a55f0c51a7218695'),
    ('dist/ygo-local/schemas/plan-request.schema.json', 'fca651412792ef0029a074e6109f7c16cff3a0e5d577f12cfc532fa8866f9ae7'),
    ('dist/ygo-local/schemas/plan-result-v2.schema.json', '3eae53d0e7bc4092e75951904fa09ad53df239417863d7b63b4127731a68beab'),
    ('dist/ygo-local/schemas/plan-result-v3.schema.json', 'a5e533a34c5cf7ecc2e01457f355df8403ae522f63b851b8bd94b6f2c4d4fea9'),
    ('dist/ygo-local/schemas/plan-result-v4.schema.json', '9640a1248541ed9da465159a7e088cdb4be4f5b1d00ad11ec386c3549d841c59'),
    ('dist/ygo-local/schemas/plan-result-v5.schema.json', '4c91666e8f62cd768084b7483ee4ae46ede18ba6badbf9d765bca91de38a0431'),
    ('dist/ygo-local/schemas/plan-result.schema.json', '6aa623238f05def1e6f24a70e2a5ad4a12431e861bcb73124dc2a23badbb8730'),
    ('dist/ygo-local/ygo-engine-worker.exe', 'ad4a592981535144190ec44e0dd8c4aca951ec21c0206a1346961484f37fd11c'),
    ('dist/ygo-local/ygo.cmd', '76cc764a8523a35e5c5fb50e865664e8325456adad797b3b9ea54a03dae5ac18'),
    ('dist/ygo-local/ygo.exe', '54804730b3a507c0143c627d5e5c61b2acc03964c9a7cda7c803b6101432a89f'),
    ('target/debug/ygo-engine-worker.exe', 'a384b35aff160049b3381f15bfc35e17cf373a1ada54986b8c884bde09c78c7e'),
)


@dataclass(frozen=True, slots=True)
class _PinnedFile:
    """A fixed source file identity; it contains no parsed or validated state."""

    role: str
    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class _PinnedArchive:
    """The byte and source-list identity for one immutable source archive."""

    role: str
    archive_path: str
    file_list_path: str
    archive_sha256: str
    file_list_sha256: str
    source_identity: str
    file_count: int
    head: str


# The acceptance-pinned evidence inventory is itself a fixed source input.
# Keep its entries literal here so a live inventory cannot redefine the pins
# that are used to verify it.
_CONFIRMATION_INVENTORY_PINS: tuple[tuple[str, str], ...] = (
    ("build-record.json", "a576968b9cdcc69fce1791a262b6b57d4e58e81c2f4ab77918f2ad35d15f718b"),
    ("final-build/build-record.json", "4d710511006e7f94bce8f30f44a3c61f8a7e24a7f62e881f158aa285fe02babf"),
    ("final-build/native-artifacts/curry-option-confirmation.exe", "87815703649b64432ac1e38d324d50f3aebb845c15d5ada35574d10611cf10e7"),
    ("final-build/native-artifacts/ygo-cli.exe", "2cc25aed9807c39153471c1f6bdff169966fa24507549a9461a441a3a56edf62"),
    ("final-build/native-artifacts/ygo-engine-worker.exe", "441c9c227c7c2487c1d08326409427dfd496bf7833ff378b4b97204308e4b4c1"),
    ("final-build/source-native-file-list.json", "808ea72c18a58c26136e130b13d22da7bd766565551c52a5a33f2d39c05f30fe"),
    ("final-build/source-native.zip", "c9c479323ee3344ed0b5debadc2d1ca539ca8b51df391df23c9734fa605a65e0"),
    ("identity.json", "219431f0d6e3e0852db4e52e1fe650f5ee6489f67209ca8496c8616ea28924a4"),
    ("native-artifacts/curry-option-confirmation.exe", "f9c3c9925599952c2ccf9e724c57e76140fe5f24b6949331e292dc7ff17b5c22"),
    ("native-artifacts/ygo-cli.exe", "2f0813f3e5caf791d745a024714584f17510ee994a54051f85906f510a0a2bfc"),
    ("native-artifacts/ygo-engine-worker.exe", "87c2f44ab0e64d72870c0879cc6ac78895bc43023a492512c2893480e313f376"),
    ("ordinary-candidate.toml", "eb1fb7fdb4307b0e7d5a2944916c00efaf8cfe319d7957a0f6b69962e11847a8"),
    ("process-diagnostics/preflight_only-47b46cb6fc564f46a1b8d15640a64925.json", "4cddd741871cedbe5064fe18f621cbffde549a2626fecf80e00f2b3a1cf2efa1"),
    ("process-diagnostics/preflight_only-47b46cb6fc564f46a1b8d15640a64925.stderr.bin", "465114f0c37f7cb417d747548bc5d31d8328497608e5bb0d7a118796aaa3e708"),
    ("process-diagnostics/preflight_only-47b46cb6fc564f46a1b8d15640a64925.stdout.bin", "2778cccc2c5cfb763d96bff995773e085ffea120f7f3b45b2807444d1f5d60fe"),
    ("research/manifest.json", "727f04b865e43661df591b33eb79e07cd959bc115ff5b33b5b798f8c243c9ad9"),
    ("research/normal-attempt-observation.json", "941b6ca1494c68358330a671a03056ff54ed825ecd0ae91c1f8716603e327f28"),
    ("research/prepared.json", "1f6582c48d554288b975ab3ee4dadf44b18803039ef6f78e102fa10ac648236e"),
    ("research/stage-1-input-seal.json", "640882238b268fcba43b703a83c187acae361c0a0f0642aee07d3a97aed8b1b8"),
    ("research/stage-1-input.json", "72112d343ac8dddb7153a31c4b3a8ccd3f0ea6daa1e11c1d2bd7931baca1ccb0"),
    ("research/stage-1-request.json", "31b0738e3b0753573b501f31eaadf13f0731684f8be718c8e8bdc6779d00da6f"),
    ("research/summary.json", "49c2402a6603f9c895d2a07cd906e9406bdf7819a11491d834c86739d03b4b04"),
    ("research/verification.json", "29310c469e3f7dc3a330588d479c8c09d4ae92dc78def368a14518cd73d01f43"),
    ("source-native-file-list.json", "da8d20ded68207065c62cb56cb23b96928359facac0abecd6dc003ccedc15e06"),
    ("source-native.zip", "37b3d0c97478e566c8496f68a18508b4810e2997debcd2ca2ec148cc5afc84fe"),
    ("tournament-candidate.toml", "65eb3098fdcd4f85e0698f81a37efdb448fabdc332b5612fb76c4abaa2b1a3c9"),
    ("verification/cargo-build-final-hash-check.log", "877322c570db729ccb1155948e83cdadb5b3bed158dc41f8cd9e1616f58277b0"),
    ("verification/cargo-build-final-hash-check.log.exit-code", "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"),
    ("verification/cargo-clippy.log", "84c72ea4e97a0afa0ea706227ed66ebf2668b1f83b9f6f3dba87d46bf3091248"),
    ("verification/cargo-clippy.log.exit-code", "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"),
    ("verification/cargo-fmt.log", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("verification/cargo-fmt.log.exit-code", "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"),
    ("verification/cargo-test-examples.log", "53d71ba387ec57cfa11d44cc1eaa6463d6f8ad0ec8fe9dd9b0cd5c2bcfc0b7c3"),
    ("verification/cargo-test-examples.log.exit-code", "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"),
    ("verification/cargo-test-workspace.log", "3792ef4084a5e137c10fce0c249d8ea425ff5d1ce5ff286cb9328fdad6afe888"),
    ("verification/cargo-test-workspace.log.exit-code", "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"),
    ("verification/independent-review.json", "4f14d075174ce0781ffb7e0e017ed3f72fb9b2af26190decd4883d3384f35781"),
    ("verification/python-unittest-final.log", "57e519ca8ff5cc1222260d6ddcac5816d396396f26d8c9c13e9f8473f516f2ae"),
    ("verification/python-unittest-final.log.exit-code", "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"),
    ("window-start.json", "4c370619a88a45842e24f662e495edf310f907a07ac45f05933ae5d82c30445e"),
)


@dataclass(frozen=True, slots=True)
class _SourceDescription:
    """Pure immutable pins propagated through the read-only verification tree."""

    role: str
    files: tuple[_PinnedFile, ...] = ()
    archives: tuple[_PinnedArchive, ...] = ()
    semantic_hashes: tuple[tuple[str, str], ...] = ()
    archive_differences: tuple[tuple[str, tuple[str, ...]], ...] = ()
    dataset_counts: tuple[tuple[str, int], ...] = ()
    children: tuple["_SourceDescription", ...] = ()
    baseline_relative: str = BASELINE_RELATIVE.as_posix()
    output_relative_v1: str = OUTPUT_RELATIVE.as_posix()
    output_relative_v2: str = OUTPUT_V2_RELATIVE.as_posix()

    def file_sha256(self, relative_path: str) -> str:
        matches = [item.sha256 for item in self.files if item.relative_path == relative_path]
        if matches:
            if len(set(matches)) != 1:
                raise KeyError("source_description_file_pin_ambiguous")
            return matches[0]
        for child in self.children:
            try:
                matches.append(child.file_sha256(relative_path))
            except KeyError:
                pass
        if not matches or len(set(matches)) != 1:
            raise KeyError("source_description_file_pin_missing")
        return matches[0]

    def file_sha256_role(self, role: str) -> str:
        matches = [item.sha256 for item in self.files if item.role == role]
        if matches:
            if len(set(matches)) != 1:
                raise KeyError("source_description_file_role_ambiguous")
            return matches[0]
        for child in self.children:
            try:
                matches.append(child.file_sha256_role(role))
            except KeyError:
                pass
        if not matches or len(set(matches)) != 1:
            raise KeyError("source_description_file_role_missing")
        return matches[0]

    def archive(self, role: str) -> _PinnedArchive:
        matches = [item for item in self.archives if item.role == role]
        if matches:
            if len(matches) != 1:
                raise KeyError("source_description_archive_pin_ambiguous")
            return matches[0]
        for child in self.children:
            try:
                matches.append(child.archive(role))
            except KeyError:
                pass
        if len(matches) != 1:
            raise KeyError("source_description_archive_pin_missing")
        return matches[0]

    def semantic_sha256(self, role: str) -> str:
        matches = [value for key, value in self.semantic_hashes if key == role]
        if matches:
            if len(set(matches)) != 1:
                raise KeyError("source_description_semantic_pin_ambiguous")
            return matches[0]
        for child in self.children:
            try:
                matches.append(child.semantic_sha256(role))
            except KeyError:
                pass
        if not matches or len(set(matches)) != 1:
            raise KeyError("source_description_semantic_pin_missing")
        return matches[0]

    def differences(self, name: str) -> tuple[str, ...]:
        matches = [value for key, value in self.archive_differences if key == name]
        if matches:
            if len(set(matches)) != 1:
                raise KeyError("source_description_archive_difference_ambiguous")
            return matches[0]
        for child in self.children:
            try:
                matches.append(child.differences(name))
            except KeyError:
                pass
        if len(matches) != 1:
            raise KeyError("source_description_archive_difference_missing")
        return matches[0]

    def dataset_count(self, name: str) -> int:
        matches = [value for key, value in self.dataset_counts if key == name]
        # Counts are scoped to the nearest verifier node.  A nested history
        # can, for example, report its 26-call prefix while the top audit
        # reports the accumulated 32-call chain.  Local-first lookup keeps
        # those fixed facts explicit without making the source description a
        # flat, ambiguous bag of counters.
        if matches:
            if len(set(matches)) != 1:
                raise KeyError("source_description_dataset_count_ambiguous")
            return matches[0]
        for child in self.children:
            try:
                matches.append(child.dataset_count(name))
            except KeyError:
                pass
        if not matches or len({item for item in matches}) != 1:
            raise KeyError("source_description_dataset_count_missing")
        return matches[0]

    def child(self, role: str) -> "_SourceDescription":
        matches = [item for item in self.children if item.role == role]
        if len(matches) != 1:
            raise KeyError("source_description_child_missing")
        return matches[0]


def _historical_dataset_counts(sources: _SourceDescription) -> tuple[int, int, int]:
    """Read accumulated ledger counts from the immutable source description."""
    history = sources.child("asset_audit").child("historical_chain")
    return (
        history.dataset_count("historical_consumed"),
        history.dataset_count("historical_unknown"),
        history.dataset_count("historical_ledgers"),
    )


def _production_source_description() -> _SourceDescription:
    """Describe the fixed production sources without carrying validation results."""
    from ygo_eval import (
        curry_asset_binding_audit as asset_audit_module,
        native_curry_option_validation as curry_module,
        native_tenki_placement as placement_history_module,
        native_tenki_placement_confirmation as placement_confirmation_module,
        native_tenki_placement_validation as validation_module,
        tenki_confirmation_runner_audit as runner_audit_module,
        tenki_placement_diagnostics as placement_diagnostics_module,
    )

    ARCHIVE_ANCHORS = asset_audit_module.ARCHIVE_ANCHORS
    CURRY_BASELINE_RELATIVE = asset_audit_module.BASELINE_RELATIVE
    FROZEN_FILES = asset_audit_module.FROZEN_FILES
    HASH_ANCHORS = asset_audit_module.HASH_ANCHORS
    ORIGINAL_PROCESS_FILES = asset_audit_module.ORIGINAL_PROCESS_FILES
    ASSET_AUDIT_RELATIVE = asset_audit_module.OUTPUT_RELATIVE
    ASSET_HISTORICAL_CONSUMED = asset_audit_module.HISTORICAL_CONSUMED
    ASSET_HISTORICAL_LEDGER_COUNT = asset_audit_module.HISTORICAL_LEDGER_COUNT
    ASSET_HISTORICAL_UNKNOWN = asset_audit_module.HISTORICAL_UNKNOWN
    CURRY_ALLOWED_ARCHIVE_DIFFS = asset_audit_module.ALLOWED_ARCHIVE_DIFFS
    CONFIRMATION_AUDIT_SHA256 = curry_module.CONFIRMATION_AUDIT_SHA256
    CONFIRMATION_DELIVERY_SHA256 = curry_module.CONFIRMATION_DELIVERY_SHA256
    CURRY_ACCEPTANCE_SHA256 = curry_module.BASELINE_ACCEPTANCE_SHA256
    CURRY_DELIVERY_SHA256 = curry_module.BASELINE_DELIVERY_SHA256
    CURRY_NATIVE_FILE_LIST_SHA256 = curry_module.BASELINE_NATIVE_FILE_LIST_SHA256
    PINNED_INPUT_SHA256 = curry_module.PINNED_INPUT_SHA256
    PREPARATION_PATH = curry_module.PREPARATION_PATH
    PREPARATION_REPORT_PATH = curry_module.PREPARATION_REPORT_PATH
    PREPARATION_ACCEPTANCE_PATH = curry_module.PREPARATION_ACCEPTANCE_PATH
    FROZEN_CASES_PATH = curry_module.FROZEN_CASES_PATH
    OPERATIONS_SOURCE_SHA256 = curry_module.OPERATIONS_SOURCE_SHA256
    HISTORICAL_SOURCE_TRANSITION = curry_module.HISTORICAL_SOURCE_TRANSITION
    RUNNER_CONFIRMATION_CONTEXT = runner_audit_module.CONFIRMATION_CONTEXT
    CONFIRMATION_LEDGER_SHA256 = runner_audit_module.CONFIRMATION_LEDGER_SHA256
    RUNNER_CONFIRMATION_DELIVERY_SHA256 = runner_audit_module.DELIVERY_SHA256
    RUNNER_CONFIRMATION_RELATIVE = runner_audit_module.EXPERIMENT_RELATIVE
    PLACEMENT_DIAGNOSTICS_RELATIVE = placement_diagnostics_module.DIAGNOSTICS_RELATIVE
    PLACEMENT_EXPERIMENT_DELIVERY_SHA256 = placement_diagnostics_module.EXPERIMENT_DELIVERY_SHA256
    PLACEMENT_ADDENDUM_SHA256 = placement_diagnostics_module.EXPERIMENT_ADDENDUM_SHA256
    PLACEMENT_DETAILS_SHA256 = placement_diagnostics_module.EXPERIMENT_DETAILS_SHA256
    PLACEMENT_DIAGNOSTIC_ARCHIVE_SHA256 = placement_diagnostics_module.NATIVE_SOURCE_ARCHIVE_SHA256
    PLACEMENT_DIAGNOSTIC_LIST_SHA256 = placement_diagnostics_module.NATIVE_SOURCE_FILE_LIST_SHA256
    PLACEMENT_FINAL_ARCHIVE_SHA256 = placement_diagnostics_module.FINAL_SOURCE_ARCHIVE_SHA256
    PLACEMENT_FINAL_LIST_SHA256 = placement_diagnostics_module.FINAL_SOURCE_FILE_LIST_SHA256
    PLACEMENT_MANIFEST_SHA256 = placement_diagnostics_module.MANIFEST_SHA256
    PLACEMENT_PREPARED_SHA256 = placement_diagnostics_module.PREPARED_SHA256
    PLACEMENT_REQUEST_SHA256 = placement_diagnostics_module.STAGE1_REQUEST_SHA256
    PLACEMENT_INPUT_SHA256 = placement_diagnostics_module.STAGE1_INPUT_SHA256
    PLACEMENT_SEAL_SHA256 = placement_diagnostics_module.STAGE1_SEAL_SHA256
    PLACEMENT_CONTEXT = placement_diagnostics_module.PLACEMENT_CONTEXT
    PLACEMENT_LEDGER_SHA256 = placement_diagnostics_module.PLACEMENT_LEDGER_SHA256
    PLACEMENT_SUMMARY_SHA256 = placement_diagnostics_module.PLACEMENT_SUMMARY_SHA256
    PLACEMENT_HISTORICAL_BUILD = placement_diagnostics_module.HISTORICAL_NATIVE_BUILD
    PLACEMENT_HISTORICAL_RUNNER = placement_diagnostics_module.HISTORICAL_NATIVE_RUNNER_SHA256
    PLACEMENT_HISTORICAL_SOURCE = placement_diagnostics_module.HISTORICAL_NATIVE_SOURCE
    PLACEMENT_PRECHECK_ARCHIVE_SHA256 = placement_confirmation_module.PRECHECK_ARCHIVE_SHA256
    PLACEMENT_PRECHECK_LIST_SHA256 = placement_confirmation_module.PRECHECK_LIST_SHA256
    PLACEMENT_PRECHECK_SOURCE = placement_confirmation_module.PRECHECK_SOURCE
    PLACEMENT_FINAL_SOURCE = placement_confirmation_module.FINAL_SOURCE
    PLACEMENT_CONFIRMATION_FINAL_ARCHIVE_SHA256 = placement_confirmation_module.FINAL_ARCHIVE_SHA256
    PLACEMENT_CONFIRMATION_FINAL_LIST_SHA256 = placement_confirmation_module.FINAL_LIST_SHA256
    PLACEMENT_CONFIRMATION_ACCEPTANCE_SHA256 = placement_confirmation_module.ACCEPTANCE_SHA256
    PLACEMENT_CONFIRMATION_DELIVERY_SHA256 = placement_confirmation_module.DELIVERY_SHA256
    PLACEMENT_CONFIRMATION_PREFLIGHT_SHA256 = placement_confirmation_module.PREFLIGHT_REPORT_SHA256
    OLD_LEDGER_CONTRACTS = placement_confirmation_module.OLD_LEDGER_CONTRACTS
    OLD_PLACEMENT_RELATIVE = placement_confirmation_module.OLD_PLACEMENT_RELATIVE
    PROMPT_BASELINE_RELATIVE = placement_confirmation_module.PROMPT_BASELINE_RELATIVE
    BEFORE_SHA256 = placement_history_module.BEFORE_SHA256
    FROZEN_CASES_SHA256 = placement_history_module.FROZEN_CASES_SHA256
    OLD_RUNNER_SHA256 = placement_history_module.OLD_RUNNER_SHA256
    OLD_STAGE1_SHA256 = placement_history_module.OLD_STAGE1_SHA256
    OLD_STAGE2_REQUEST_SHA256 = placement_history_module.OLD_STAGE2_REQUEST_SHA256
    OLD_STAGE2_SHA256 = placement_history_module.OLD_STAGE2_SHA256
    PAUSE_ACCEPTANCE_SHA256 = placement_history_module.PAUSE_ACCEPTANCE_SHA256
    PAUSED_DELIVERY_CHECKPOINT_SHA256 = placement_history_module.PAUSED_DELIVERY_CHECKPOINT_SHA256
    PREPARATION_RELATIVE = placement_history_module.PREPARATION_RELATIVE
    PREPARATION_SHA256 = placement_history_module.PREPARATION_SHA256
    RECOVERY_ACCEPTANCE_SHA256 = placement_history_module.RECOVERY_ACCEPTANCE_SHA256
    RECOVERY_CHECKPOINT_SHA256 = placement_history_module.RECOVERY_CHECKPOINT_SHA256
    TRANSITION_FILE_PATH = placement_history_module.TRANSITION_FILE_PATH
    VALIDATION_SCOPE = validation_module.VALIDATION_SCOPE
    _old_ledger_contracts = OLD_LEDGER_CONTRACTS
    placement_confirmation = placement_confirmation_module

    def files(prefix: str, relative_root: str, values: dict[str, str]) -> tuple[_PinnedFile, ...]:
        return tuple(
            _PinnedFile(
                f"{prefix}_{path.replace('/', '_')}",
                f"{relative_root.rstrip('/')}/{path}",
                expected,
            )
            for path, expected in values.items()
        )

    def archive_pin(
        role: str, archive_path: str, file_list_path: str,
        archive_sha256: str, list_sha256: str, source_identity: str,
        file_count: int, head: str = EXPECTED_HEAD,
    ) -> _PinnedArchive:
        return _PinnedArchive(
            role, archive_path, file_list_path, archive_sha256, list_sha256,
            source_identity, file_count, head,
        )

    def old_curry_files() -> tuple[_PinnedFile, ...]:
        root = CURRY_BASELINE_RELATIVE.as_posix()
        values = {
            "build-record.json": HASH_ANCHORS["native_build_record"],
            "final-build/build-record.json": HASH_ANCHORS["final_build_record"],
            "research/manifest.json": HASH_ANCHORS["manifest"],
            "research/prepared.json": HASH_ANCHORS["prepared"],
            "research/summary.json": HASH_ANCHORS["summary"],
            "research/stage-1-request.json": FROZEN_FILES["stage1_request"],
            "research/stage-1-input.json": FROZEN_FILES["stage1_input"],
            "research/stage-1-input-seal.json": FROZEN_FILES["stage1_seal"],
            "identity.json": FROZEN_FILES["identity"],
            "window-start.json": FROZEN_FILES["window_start"],
            "process-diagnostics/preflight_only-d3e880ecf8d04c56a110a3d777e21a2e.json": ORIGINAL_PROCESS_FILES["metadata"],
            "process-diagnostics/preflight_only-d3e880ecf8d04c56a110a3d777e21a2e.stdout.bin": ORIGINAL_PROCESS_FILES["stdout"],
            "native-artifacts/ygo-cli.exe": "00395cd2e209746ba7295d07782fd64ce635a960273c511469e0b0a89959e089",
            "native-artifacts/curry-option-validation.exe": "57e119a1232b91dd57d13a5803475398589d2a801cc95ea27790a813326ed85f",
            "native-artifacts/ygo-engine-worker.exe": "087fe574ac8d21a10befdbdad9ccfbc871805e643b6669e3fab520c8eb7fcb6d",
            "final-build/native-artifacts/ygo-cli.exe": "00395cd2e209746ba7295d07782fd64ce635a960273c511469e0b0a89959e089",
            "final-build/native-artifacts/curry-option-validation.exe": "57e119a1232b91dd57d13a5803475398589d2a801cc95ea27790a813326ed85f",
            "final-build/native-artifacts/ygo-engine-worker.exe": "087fe574ac8d21a10befdbdad9ccfbc871805e643b6669e3fab520c8eb7fcb6d",
        }
        return files("curry_baseline", root, values)

    def curry_archives() -> tuple[_PinnedArchive, _PinnedArchive]:
        root = CURRY_BASELINE_RELATIVE.as_posix()
        return (
            archive_pin(
                "curry_native_archive", f"{root}/source-native.zip",
                f"{root}/source-native-file-list.json",
                ARCHIVE_ANCHORS["native_time"]["archive_sha256"],
                ARCHIVE_ANCHORS["native_time"]["file_list_sha256"],
                ARCHIVE_ANCHORS["native_time"]["source_identity"],
                ARCHIVE_ANCHORS["native_time"]["file_count"],
            ),
            archive_pin(
                "curry_final_archive", f"{root}/final-build/source-native.zip",
                f"{root}/final-build/source-native-file-list.json",
                ARCHIVE_ANCHORS["final"]["archive_sha256"],
                ARCHIVE_ANCHORS["final"]["file_list_sha256"],
                ARCHIVE_ANCHORS["final"]["source_identity"],
                ARCHIVE_ANCHORS["final"]["file_count"],
            ),
        )

    def validation_output_files() -> tuple[_PinnedFile, ...]:
        root = validation_module.VALIDATION_SCOPE.output_root.as_posix()
        prompt_root = placement_confirmation_module.PROMPT_BASELINE_RELATIVE.as_posix()
        return (
            _PinnedFile("curry_validation_acceptance", f"{root}/acceptance.json",
                        "242e0f5e1839f132d5b091963ba9917691536ae0913e7beeca6fc62635d7f4f9"),
            _PinnedFile("curry_validation_delivery", f"{root}/final-build/delivery.json",
                        validation_module.VALIDATION_SCOPE.delivery_sha256),
            _PinnedFile("curry_validation_manifest", f"{root}/research/manifest.json",
                        "dfcf3243fda55805e6c9deb2ed8cc722f2bcc534acfdf075261ef455227a35d2"),
            _PinnedFile("curry_validation_prepared", f"{root}/research/prepared.json",
                        "032e11b6c3a04f1d17e2de241bd2f3167d9505acc98075e76a3f57febd64aa92"),
            _PinnedFile("curry_validation_summary", f"{root}/research/summary.json",
                        "9b250b347a9f05c3eef8d321f6eba259d389d0cb1a9f4c1db0a84b205b8eee49"),
            _PinnedFile("curry_validation_verification", f"{root}/research/verification.json",
                        "836ef6447087290496ec9ef1a6e6f6492b1859b526099f3cc45b83bddfafd669"),
            _PinnedFile("curry_validation_ledger", f"{root}/research/calls.jsonl",
                        "4244d92bd17413861bc92d4618803bc647dd05cab074189e678be8429f89971c"),
            _PinnedFile("curry_validation_prompt_stage1",
                        f"{prompt_root}/research/stage-1.json", OLD_STAGE1_SHA256),
            _PinnedFile("curry_validation_prompt_stage2_request",
                        f"{prompt_root}/research/stage-2-request.json",
                        OLD_STAGE2_REQUEST_SHA256),
            _PinnedFile("curry_validation_preparation", PREPARATION_RELATIVE.as_posix(),
                        PREPARATION_SHA256),
            _PinnedFile("curry_validation_banlist", "data/runtime/banlist.json",
                        "a6344cd77c4db6dcfab02d03110954fa1c2717422f71da302970f427564506c9"),
        )

    def validation_output_archives() -> tuple[_PinnedArchive, _PinnedArchive]:
        root = validation_module.VALIDATION_SCOPE.output_root.as_posix()
        return (
            archive_pin(
                "curry_native_archive", f"{root}/source-native.zip",
                f"{root}/source-native-file-list.json",
                "8c8c5d676d34ae03161491cd0a6dcedd5cc7c47d5ed2ecabdfbf4231c6e34e7e",
                "fd02e8e722a38b0edfdfc0058c9d4007f1059edfe3c641c8b4a2774a00939653",
                "e9538276391f0e08bfa707534aeab6c8e663784da8fcd9a97dc5ea0e9eb6e8f0",
                683, EXPECTED_HEAD,
            ),
            archive_pin(
                "curry_final_archive", f"{root}/final-build/source-final.zip",
                f"{root}/final-build/source-final-file-list.json",
                "e024ef670ae2b6278f8db0efee30729837ecc886a0a09ea4d327574ff287033a",
                "bbfeb6977a085e9fd20220f2de7c48dbfd3865fe67a05b8b43340669f746d0b3",
                "cd3945980e20e0f44443a67a4722e4da86a27e7fae3f57fe2aaf7c57ac12533d",
                684, EXPECTED_HEAD,
            ),
        )

    def old_ledger_files(contracts) -> tuple[_PinnedFile, ...]:
        return tuple(
            _PinnedFile(f"historical_ledger_{name}", path, expected)
            for name, path, expected, *_rest in contracts
        )

    def ledger_consumption_counts():
        return tuple(
            (f"ledger_{contract[0]}_consumed", contract[3])
            for contract in OLD_LEDGER_CONTRACTS
        )

    baseline = BASELINE_RELATIVE.as_posix()
    confirmation = _SourceDescription(
        role="confirmation",
        files=(
            _PinnedFile("acceptance", f"{baseline}/acceptance.json", ACCEPTANCE_SHA256),
            _PinnedFile("delivery", f"{baseline}/final-build/delivery.json", DELIVERY_SHA256),
            _PinnedFile("evidence_inventory", f"{baseline}/evidence-inventory.json", INVENTORY_SHA256),
            *(
                _PinnedFile(
                    f"confirmation_inventory_entry_{index:03d}",
                    f"{baseline}/{relative_path}",
                    expected,
                )
                for index, (relative_path, expected) in enumerate(_CONFIRMATION_INVENTORY_PINS, 1)
            ),
        ),
        archives=(
            _PinnedArchive(
                "confirmation_native_archive", f"{baseline}/source-native.zip",
                f"{baseline}/source-native-file-list.json", NATIVE_ARCHIVE_SHA256,
                NATIVE_LIST_SHA256, NATIVE_SOURCE_IDENTITY, 501, EXPECTED_HEAD,
            ),
            _PinnedArchive(
                "confirmation_final_archive", f"{baseline}/final-build/source-native.zip",
                f"{baseline}/final-build/source-native-file-list.json", FINAL_ARCHIVE_SHA256,
                FINAL_LIST_SHA256, FINAL_SOURCE_IDENTITY, 502, EXPECTED_HEAD,
            ),
        ),
        semantic_hashes=(
            ("base_request", PINNED_INPUT_SHA256["base_request"]),
            ("candidate_case", PINNED_INPUT_SHA256["candidate_case"]),
        ),
        archive_differences=(("confirmation", tuple(sorted(ALLOWED_ARCHIVE_DIFFS))),),
        dataset_counts=(
            ("evidence_inventory_entries", 40),
            ("evidence_inventory_bytes", 60_054_498),
        ),
        children=(
            _SourceDescription(
                role="static_preparation",
                files=(
                    _PinnedFile("preparation", PREPARATION_PATH.as_posix(), PINNED_INPUT_SHA256["preparation"]),
                    _PinnedFile("preparation_report", PREPARATION_REPORT_PATH.as_posix(), PINNED_INPUT_SHA256["preparation_report"]),
                    _PinnedFile("preparation_acceptance", PREPARATION_ACCEPTANCE_PATH.as_posix(), PINNED_INPUT_SHA256["preparation_acceptance"]),
                    _PinnedFile("operations_source", "data/tmp/ocgcore-source/operations.cpp", OPERATIONS_SOURCE_SHA256),
                    _PinnedFile("adapter_codec", HISTORICAL_SOURCE_TRANSITION["path"], HISTORICAL_SOURCE_TRANSITION["current_sha256"]),
                    _PinnedFile("frozen_cases", FROZEN_CASES_PATH.as_posix(), "de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879"),
                ),
                semantic_hashes=(
                    ("candidate_case", PINNED_INPUT_SHA256["candidate_case"]),
                    ("base_request", PINNED_INPUT_SHA256["base_request"]),
                    ("baseline_frozen_cases", "de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879"),
                ),
                baseline_relative=PREPARATION_PATH.as_posix().rsplit("/", 1)[0],
            ),
            _SourceDescription(
                role="asset_audit",
                files=(
                    _PinnedFile("asset_audit_audit", f"{ASSET_AUDIT_RELATIVE.as_posix()}/audit-report.json", CONFIRMATION_AUDIT_SHA256),
                    _PinnedFile("asset_audit_delivery", f"{ASSET_AUDIT_RELATIVE.as_posix()}/final-build/delivery.json", CONFIRMATION_DELIVERY_SHA256),
                    _PinnedFile("asset_audit_build_record", f"{ASSET_AUDIT_RELATIVE.as_posix()}/build-record.json", "da933dbae09031d5646cbed1eccdcafc403e3378e071f85e70d6d4b0945429e2"),
                    _PinnedFile("asset_audit_final_build_record", f"{ASSET_AUDIT_RELATIVE.as_posix()}/final-build/build-record.json", "f3e6657b4433f9d449bcb6372f527adad03da8ec85666677ef83f26aaf35f9dd"),
                    _PinnedFile("asset_audit_source_identity", f"{ASSET_AUDIT_RELATIVE.as_posix()}/source-identity.json", "f3aaed042aeb642bd3362b5f9f8b24fd8798a5dfe45e25778756eb757bfbb7ed"),
                    _PinnedFile("asset_audit_final_source_identity", f"{ASSET_AUDIT_RELATIVE.as_posix()}/final-build/source-identity.json", "b6977086d3c8edddd5a513696ff203e6b08fce29a7360fb45ca72af3897db190"),
                    _PinnedFile("asset_audit_native_archive", f"{ASSET_AUDIT_RELATIVE.as_posix()}/source-native.zip", "a235cf00ee038196782e1e33992bc7719d5dce9169d56d204f5d99167a5fbbde"),
                    _PinnedFile("asset_audit_native_list", f"{ASSET_AUDIT_RELATIVE.as_posix()}/source-native-file-list.json", "75b21e3fd265ffac5c9bca78c4d067c6a479f937d07461733ef8fec73e005aff"),
                    _PinnedFile("asset_audit_final_archive", f"{ASSET_AUDIT_RELATIVE.as_posix()}/final-build/source-native.zip", "3043c1f6a0c3128f0f9caeeda60901e4c20442f90d07ee94b36642c4dd4b040f"),
                    _PinnedFile("asset_audit_final_list", f"{ASSET_AUDIT_RELATIVE.as_posix()}/final-build/source-native-file-list.json", "7568bfbce96d69a74f3e50e6d4312e51a79bd959c647d8b9a2389c019638ca05"),
                ),
                archives=(
                    archive_pin("asset_audit_native_archive", f"{ASSET_AUDIT_RELATIVE.as_posix()}/source-native.zip", f"{ASSET_AUDIT_RELATIVE.as_posix()}/source-native-file-list.json", "a235cf00ee038196782e1e33992bc7719d5dce9169d56d204f5d99167a5fbbde", "75b21e3fd265ffac5c9bca78c4d067c6a479f937d07461733ef8fec73e005aff", "43f4518145e6fa0157896c96f6d48dcd9df89c80f24d64bfc6a116b6be7e62f2", 498),
                    archive_pin("asset_audit_final_archive", f"{ASSET_AUDIT_RELATIVE.as_posix()}/final-build/source-native.zip", f"{ASSET_AUDIT_RELATIVE.as_posix()}/final-build/source-native-file-list.json", "3043c1f6a0c3128f0f9caeeda60901e4c20442f90d07ee94b36642c4dd4b040f", "7568bfbce96d69a74f3e50e6d4312e51a79bd959c647d8b9a2389c019638ca05", "2a9f15766a3da34016e1b9b790f7f530809fceb4a6a761f37ce16451334a271b", 499),
                ),
                dataset_counts=(
                    ("historical_consumed", ASSET_HISTORICAL_CONSUMED),
                    ("historical_unknown", ASSET_HISTORICAL_UNKNOWN),
                    ("historical_ledgers", ASSET_HISTORICAL_LEDGER_COUNT),
                    ("asset_audit_inputs", 548),
                    ("historical_material_inputs", 518),
                    ("asset_audit_protected_files", 24),
                    ("asset_audit_source_files", 498),
                ),
                baseline_relative=ASSET_AUDIT_RELATIVE.as_posix(),
                children=(
                    _SourceDescription(
                        role="asset_audit_scope",
                        files=old_curry_files(),
                        archives=curry_archives(),
                        semantic_hashes=(
                            ("base_request", PINNED_INPUT_SHA256["base_request"]),
                            ("candidate_case", PINNED_INPUT_SHA256["candidate_case"]),
                            ("historical_codec", HISTORICAL_SOURCE_TRANSITION["historical_sha256"]),
                            ("current_codec", HISTORICAL_SOURCE_TRANSITION["current_sha256"]),
                        ),
                        archive_differences=(("curry_baseline", tuple(sorted(CURRY_ALLOWED_ARCHIVE_DIFFS))),),
                        dataset_counts=(("historical_consumed", 32), ("historical_unknown", 0)),
                        baseline_relative=CURRY_BASELINE_RELATIVE.as_posix(),
                    ),
                    _SourceDescription(
                        role="historical_chain",
                        dataset_counts=(
                            ("previous_consumed", 26), ("previous_unknown", 0),
                            ("previous_ledger_count", 7),
                            ("confirmation_consumed", 0), ("confirmation_unknown", 0),
                            ("current_consumed", 6), ("current_unknown", 0),
                            ("historical_consumed", 32), ("historical_unknown", 0),
                            ("historical_ledgers", 9),
                        ),
                        children=(
                            _SourceDescription(
                                role="curry_baseline",
                                files=validation_output_files(),
                                archives=validation_output_archives(),
                                semantic_hashes=(
                                    ("historical_codec", HISTORICAL_SOURCE_TRANSITION["historical_sha256"]),
                                    ("current_codec", HISTORICAL_SOURCE_TRANSITION["current_sha256"]),
                                ),
                                archive_differences=(("curry_baseline", tuple(sorted(CURRY_ALLOWED_ARCHIVE_DIFFS))),),
                                dataset_counts=(("historical_consumed", 32), ("historical_unknown", 0)),
                                baseline_relative=validation_module.VALIDATION_SCOPE.output_root.as_posix(),
                                children=(
                                    _SourceDescription(
                                        role="validation_baseline",
                                        files=(
                                            _PinnedFile("validation_delivery", f"{VALIDATION_SCOPE.baseline_root.as_posix()}/final-build/delivery.json", VALIDATION_SCOPE.delivery_sha256),
                                            _PinnedFile("validation_archive", f"{VALIDATION_SCOPE.baseline_root.as_posix()}/final-build/source-native.zip", "87771094a6c6680096210e9e4e50efb68dc708d53e2f9982e0e0c982959f873d"),
                                            _PinnedFile("validation_file_list", f"{VALIDATION_SCOPE.baseline_root.as_posix()}/final-build/source-native-file-list.json", "ef1a6d1ef25fd770e608f58238c67739416bf37f370ab316dcd2a4a62a22bd3b"),
                                            _PinnedFile("validation_source_identity", f"{VALIDATION_SCOPE.baseline_root.as_posix()}/final-build/source-identity.json", "7e75738c929ba58761e2a2107de75894264d0cab3fd46a48340e97de1f06cabd"),
                                            _PinnedFile("validation_build_record", f"{VALIDATION_SCOPE.baseline_root.as_posix()}/final-build/build-record.json", "ae8143df6ed75a346d5af81c71c6354a18869ff0a559385d9d2b5e1fb29b4e84"),
                                            _PinnedFile("validation_runner", f"{VALIDATION_SCOPE.baseline_root.as_posix()}/final-build/native-artifacts/tenki-placement-probe.exe", "6f05feb89dad8ea92d771f4fe22a8e24a9d119aa410f0f0f66a3d02024000d8c"),
                                            _PinnedFile("validation_audit_report", f"{VALIDATION_SCOPE.baseline_root.as_posix()}/audit-report.json", "b07115ed2e9dc7e5048cd7ed702e8b0b5712f279244d4141a7dfc22e1d62afbd"),
                                        ),
                                        archives=(archive_pin(
                                            "validation_final_archive",
                                            f"{VALIDATION_SCOPE.baseline_root.as_posix()}/final-build/source-native.zip",
                                            f"{VALIDATION_SCOPE.baseline_root.as_posix()}/final-build/source-native-file-list.json",
                                            "87771094a6c6680096210e9e4e50efb68dc708d53e2f9982e0e0c982959f873d",
                                            "ef1a6d1ef25fd770e608f58238c67739416bf37f370ab316dcd2a4a62a22bd3b",
                                            "7e75738c929ba58761e2a2107de75894264d0cab3fd46a48340e97de1f06cabd",
                                            534,
                                        ),),
                                        dataset_counts=(("validation_historical_consumed", 26), ("validation_historical_unknown", 0), ("validation_historical_ledgers", 7)),
                                        baseline_relative=VALIDATION_SCOPE.baseline_root.as_posix(),
                                        children=(
                                            _SourceDescription(
                                                role="runner_confirmation",
                                                files=(
                                                    _PinnedFile("runner_delivery", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/final-build/delivery.json", RUNNER_CONFIRMATION_DELIVERY_SHA256),
                                                    _PinnedFile("runner_manifest", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/research/manifest.json", "66742c97cb9d004ede81a132b71f73969020c55dea6a6f5eee9ae1e748b61dc2"),
                                                    _PinnedFile("runner_request", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/research/stage-1-request.json", "fac2455f2b2876bc9f28666252bdc8326dcd16cf95c63335230f2d49eac9a134"),
                                                    _PinnedFile("runner_input", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/research/stage-1-input.json", "92a255d301d8a07b8a5d1a4db7d7a208040a0a06daf19cb26e69b9bb0c01dfdd"),
                                                    _PinnedFile("runner_seal", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/research/stage-1-input-seal.json", "b7af94a967c1919727f8fbb8a7f452dab5bbfbe512381c2474a3a52959e8f13e"),
                                                    _PinnedFile("runner_prepared", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/research/prepared.json", "6b31517e79cdf28659ebd96d5a35970fcb528675f4d870f931ab856eae020646"),
                                                    _PinnedFile("runner_stage1_report", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/research/stage-1-report.json", "1dd7f3a6896e82a1ccabce5f64c8e55bbb05bd301ae0d70d87ebd1a1da068899"),
                                                    _PinnedFile("runner_summary", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/research/summary.json", "40e5ff9de6af10b4d4b49d35836d0a57af82ca92e0431bbe443b7a5771941510"),
                                                    _PinnedFile("runner_verification", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/research/verification.json", "49470ac70582e50a889a79e31b638f006cceaf02812060c918a2092c27984892"),
                                                    _PinnedFile("runner_identity", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/identity.json", "6e818f8345ef79955dc48918e305a2da48a0ad85ece55ac39e05f4feb84c236a"),
                                                    _PinnedFile("runner_window", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/window-start.json", "b671e4f97f38484bfc02d1faf2c6af7cff7b714521f511fe5cca88f137b447e2"),
                                                    _PinnedFile("runner_native_build", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/build-record.json", "fbd62aae847d0e18529b755e030a21d997d9f78bfb3e7cd9661e134f97d8fd01"),
                                                    _PinnedFile("runner_final_build", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/final-build/build-record.json", "c190c4515af119570dcce410ed3e3e8797d0a66ad980be5c5169e3c5b6ad89a4"),
                                                    _PinnedFile("runner_final_source_identity", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/final-build/source-identity.json", "121832b3a213ba67bcd7b056b481a98a075e34c75c8ee916e340b81d61f9294e"),
                                                    _PinnedFile("runner_native_worker", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/native-artifacts/ygo-engine-worker.exe", "39610bbf4dd32fc3dbc29801463db485f2e4d42dfb3533f18739d29e542537c9"),
                                                    _PinnedFile("runner_native_runner", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/native-artifacts/tenki-placement-probe.exe", "5b951a1d93384c9ce2d8c78b943de729ee67670b8444d010699aba0471db5224"),
                                                    _PinnedFile("runner_native_cli", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/native-artifacts/ygo-cli.exe", "50d377576e27df55dff918b2a0fefd14e8c5ef227cb389218e9ef5f69350c3c3"),
                                                ) + old_ledger_files(OLD_LEDGER_CONTRACTS) + (
                                                    _PinnedFile("runner_current_ledger", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/research/calls.jsonl", CONFIRMATION_LEDGER_SHA256),
                                                    _PinnedFile("runner_checkpoint_blob", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/research/calls.jsonl.blobs/checkpoints/" + "dfc73a5ee5702dee0c00e1e4ce47e2e953371e5d4fca9aa1fa13eaabeb0ea80d.json", "dfc73a5ee5702dee0c00e1e4ce47e2e953371e5d4fca9aa1fa13eaabeb0ea80d"),
                                                ),
                                                archives=(
                                                    archive_pin("runner_native_archive", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/source-native.zip", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/source-native-file-list.json", "a4c85682032597f1fe512a8c59eea498c8426b7f25e9f61b736f57051da55801", "48d4477b91d6bbf70d54722f4849378599706e7d52dcd036c634e5a2e3a6f3fe", "554891b51a1316ae68b145559930e95264e64470da6e1240969ae41ed96df133", 510),
                                                    archive_pin("runner_final_archive", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/final-build/source-native.zip", f"{RUNNER_CONFIRMATION_RELATIVE.as_posix()}/final-build/source-native-file-list.json", "0bda44e2a69e0e450a022786e9065411d6f39199df4d2c5f99de883c53833a2c", "7354006bc4e72b9e8660c6c4d2caeb04d9563bc6e0af737587330587afd46981", "2ed6dea8570785537f142dc94b5871ba702f5eedb0956c042995a0d2e62082e2", 511),
                                                ),
                                                semantic_hashes=(("runner_stage1_request", "fac2455f2b2876bc9f28666252bdc8326dcd16cf95c63335230f2d49eac9a134"), ("runner_confirmation_context", RUNNER_CONFIRMATION_CONTEXT)),
                                                dataset_counts=(("historical_consumed", 26), ("ledger_count", 8)),
                                                baseline_relative=RUNNER_CONFIRMATION_RELATIVE.as_posix(),
                                                children=(
                                                    _SourceDescription(role="historical_ledgers", files=old_ledger_files(OLD_LEDGER_CONTRACTS), dataset_counts=(("ledger_count", 7), ("consumed", 26), *ledger_consumption_counts()), baseline_relative="data/runtime"),
                                                    _SourceDescription(
                                                        role="placement_confirmation",
                                                        files=(
                                                            _PinnedFile("placement_acceptance", f"{PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix()}/final-build/acceptance.json", PLACEMENT_CONFIRMATION_ACCEPTANCE_SHA256),
                                                            _PinnedFile("placement_delivery", f"{PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix()}/final-build/delivery.json", PLACEMENT_CONFIRMATION_DELIVERY_SHA256),
                                                            _PinnedFile("placement_preflight_report", f"{PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix()}/preflight-report.json", PLACEMENT_CONFIRMATION_PREFLIGHT_SHA256),
                                                            _PinnedFile("placement_experiment_delivery", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/final-build/delivery.json", PLACEMENT_EXPERIMENT_DELIVERY_SHA256),
                                                            _PinnedFile("placement_addendum", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/final-build/delivery-addendum.json", PLACEMENT_ADDENDUM_SHA256),
                                                            _PinnedFile("placement_details", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/verification/test-exclusion-details.json", PLACEMENT_DETAILS_SHA256),
                                                            _PinnedFile("placement_manifest", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/research/manifest.json", PLACEMENT_MANIFEST_SHA256),
                                                            _PinnedFile("placement_prepared", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/research/prepared.json", PLACEMENT_PREPARED_SHA256),
                                                            _PinnedFile("placement_request", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/research/stage-1-request.json", PLACEMENT_REQUEST_SHA256),
                                                            _PinnedFile("placement_input", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/research/stage-1-input.json", PLACEMENT_INPUT_SHA256),
                                                            _PinnedFile("placement_seal", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/research/stage-1-input-seal.json", PLACEMENT_SEAL_SHA256),
                                                            _PinnedFile("placement_summary", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/research/summary.json", PLACEMENT_SUMMARY_SHA256),
                                                            _PinnedFile("placement_ledger", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/research/calls.jsonl", PLACEMENT_LEDGER_SHA256),
                                                            _PinnedFile("placement_identity", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/identity.json", "d5b443434cfabf1c6328ea4ae39e7bf642518649efda1898dd7d4dc4ee8be545"),
                                                            _PinnedFile("placement_native_build", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/build-record.json", "2bdee9ce580f517ad74ce28a93ec54215cdd5c191d99bd2e87d5d9ddc93cfa9b"),
                                                            _PinnedFile("placement_native_archive", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/source-native.zip", "4ab49ab6b1fe4545681729ec1243de76151d3c1b64f15a5d3bb3b7adf2b809bb"),
                                                            _PinnedFile("placement_native_list", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/source-native-file-list.json", "90f6a24b9a57a5f1d61e4a0d29406653d10f9e6f3325ff51c21a0de352f10e12"),
                                                            _PinnedFile("placement_final_archive", f"{PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix()}/final-build/source-native.zip", PLACEMENT_CONFIRMATION_FINAL_ARCHIVE_SHA256),
                                                            _PinnedFile("placement_final_list", f"{PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix()}/final-build/source-native-file-list.json", PLACEMENT_CONFIRMATION_FINAL_LIST_SHA256),
                                                            _PinnedFile("placement_precheck_archive", f"{PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix()}/verification/source-audit-strict-dedupe/source-native.zip", PLACEMENT_PRECHECK_ARCHIVE_SHA256),
                                                            _PinnedFile("placement_precheck_list", f"{PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix()}/verification/source-audit-strict-dedupe/source-native-file-list.json", PLACEMENT_PRECHECK_LIST_SHA256),
                                                            _PinnedFile("placement_transition", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/baseline-transition.json", "adca03b129b8e17ae69165fadd00276967c9038b6c0c1efc55241f79c7051789"),
                                                        ) + old_ledger_files(OLD_LEDGER_CONTRACTS),
                                                        archives=(
                                                            archive_pin("placement_native_archive", f"{PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix()}/verification/source-audit-strict-dedupe/source-native.zip", f"{PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix()}/verification/source-audit-strict-dedupe/source-native-file-list.json", PLACEMENT_PRECHECK_ARCHIVE_SHA256, PLACEMENT_PRECHECK_LIST_SHA256, PLACEMENT_PRECHECK_SOURCE, 458),
                                                            archive_pin("placement_final_archive", f"{PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix()}/final-build/source-native.zip", f"{PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix()}/final-build/source-native-file-list.json", PLACEMENT_CONFIRMATION_FINAL_ARCHIVE_SHA256, PLACEMENT_CONFIRMATION_FINAL_LIST_SHA256, PLACEMENT_FINAL_SOURCE, 459),
                                                            archive_pin("placement_history_archive", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/source-native.zip", f"{OLD_PLACEMENT_RELATIVE.as_posix()}/source-native-file-list.json", "4ab49ab6b1fe4545681729ec1243de76151d3c1b64f15a5d3bb3b7adf2b809bb", "90f6a24b9a57a5f1d61e4a0d29406653d10f9e6f3325ff51c21a0de352f10e12", PLACEMENT_HISTORICAL_SOURCE, 401),
                                                        ),
                                                        semantic_hashes=(("placement_historical_build", PLACEMENT_HISTORICAL_BUILD), ("placement_historical_runner", PLACEMENT_HISTORICAL_RUNNER), ("placement_context", PLACEMENT_CONTEXT)),
                                                        archive_differences=(("placement_confirmation", tuple(sorted(placement_confirmation.DOC_ONLY_CHANGES))),),
                                                        dataset_counts=(
                                                            ("historical_consumed", 26), ("ledger_count", 7),
                                                            ("placement_python_skipped", 7),
                                                            ("placement_rust_ignored", 36),
                                                            ("placement_examples_ignored", 0),
                                                            *ledger_consumption_counts(),
                                                        ),
                                                        baseline_relative=PLACEMENT_DIAGNOSTICS_RELATIVE.as_posix(),
                                                        children=(
                                                            _SourceDescription(
                                                                role="historical_ledgers",
                                                                files=old_ledger_files(OLD_LEDGER_CONTRACTS),
                                                                dataset_counts=(("ledger_count", 7), ("consumed", 26), *ledger_consumption_counts()),
                                                                baseline_relative="data/runtime",
                                                            ),
                                                            _SourceDescription(
                                                                role="baseline",
                                                                files=(
                                                                    *(_PinnedFile("baseline_protected", path, sha) for path, sha in _TENKI_BASELINE_PROTECTED_PINS),
                                                                    _PinnedFile("baseline_before", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/before.json", BEFORE_SHA256),
                                                                    _PinnedFile("baseline_pause_acceptance", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/pause-acceptance.json", PAUSE_ACCEPTANCE_SHA256),
                                                                    _PinnedFile("baseline_delivery_checkpoint", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/delivery-checkpoint.json", PAUSED_DELIVERY_CHECKPOINT_SHA256),
                                                                    _PinnedFile("baseline_recovery_acceptance", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/recovery-2026-10-22/recovery-acceptance.json", RECOVERY_ACCEPTANCE_SHA256),
                                                                    _PinnedFile("baseline_recovery_checkpoint", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/recovery-2026-10-22/recovery-checkpoint.json", RECOVERY_CHECKPOINT_SHA256),
                                                                    _PinnedFile("baseline_prompt_stage1", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/research/stage-1.json", OLD_STAGE1_SHA256),
                                                                    _PinnedFile("baseline_prompt_stage1_input", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/research/stage-1-input.json", "b2b08b1f02538af815829bb1b618f948bf65fb6654755ccfba968991ea2fe913"),
                                                                    _PinnedFile("baseline_prompt_stage1_request", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/research/stage-1-request.json", "08e2679fa801a1aba4dc3e0e2645bbc7f6fd495d6094b03c5fbd15141af9331c"),
                                                                    _PinnedFile("baseline_prompt_stage2", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/research/stage-2.json", OLD_STAGE2_SHA256),
                                                                    _PinnedFile("baseline_prompt_stage2_request", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/research/stage-2-request.json", OLD_STAGE2_REQUEST_SHA256),
                                                                    _PinnedFile("baseline_old_runner", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/native-artifacts/prompt-probe.exe", OLD_RUNNER_SHA256),
                                                                    _PinnedFile("baseline_preparation", PREPARATION_RELATIVE.as_posix(), PREPARATION_SHA256),
                                                                    _PinnedFile("baseline_previous_report", "data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/report.json", "22536f6031adc88eae4bb7e2ada4f9ff374a2d227e66927e084180552e12b073"),
                                                                    _PinnedFile("baseline_previous_manifest", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/research/manifest.json", "efd59421277bb88be3cb524627f230a6dff088495a747ecd7717dc78abf41773"),
                                                                    _PinnedFile("baseline_transition", TRANSITION_FILE_PATH.as_posix(), "adca03b129b8e17ae69165fadd00276967c9038b6c0c1efc55241f79c7051789"),
                                                                ),
                                                                archives=(archive_pin("baseline_archive", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/recovery-2026-10-22/final-source.zip", f"{PROMPT_BASELINE_RELATIVE.as_posix()}/recovery-2026-10-22/source-file-list.json", "0ec2f8a618035eb18bebfc45b656e00ef69f00d8feeae2b4710ec759daf977d4", "364907befbb71fa9e67188494393c7f85e4b823de3bc4dc4660514f51dd203bd", "8bcd16e223a69e2053e37e2b380a7b8849bd540292661e79c327585b13496868", 390),),
                                                                semantic_hashes=(
                                                                    ("baseline_pause_source_identity", "6a838b72d583eb9c5bd3a5ff13c140c3a1782cfc19dc84562624c4a3c0a3da76"),
                                                                    ("baseline_frozen_cases", FROZEN_CASES_SHA256),
                                                                    ("transition_old_worker_sha256", placement_history_module.TRANSITION_OLD_SHA256),
                                                                    ("transition_new_worker_sha256", placement_history_module.TRANSITION_V2_NEW_SHA256),
                                                                    ("curry_scope_codec_old_sha256", placement_history_module.CURRY_SCOPE_PROTECTED_SOURCE_CHANGE["old_sha256"]),
                                                                    ("curry_scope_codec_sha256", placement_history_module.CURRY_SCOPE_PROTECTED_SOURCE_CHANGE["new_sha256"]),
                                                                ),
                                                                dataset_counts=(("baseline_recovery_old_ledger_entries", 5), ("pause_evidence_count", 61), ("recovery_evidence_count", 16), ("protected_file_count", 366), ("historical_consumed", 26), ("placement_python_skipped", 7), ("placement_rust_ignored", 36), ("placement_examples_ignored", 0), *ledger_consumption_counts()),
                                                                baseline_relative=PROMPT_BASELINE_RELATIVE.as_posix(),
                                                            ),
                                                        ),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        baseline_relative=BASELINE_RELATIVE.as_posix(),
        output_relative_v1=OUTPUT_RELATIVE.as_posix(),
        output_relative_v2=OUTPUT_V2_RELATIVE.as_posix(),
    )
    return confirmation

def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-version", type=int, choices=(1, 2), default=1)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _require(condition: bool, diagnostic: str) -> None:
    if not condition:
        raise ValueError(diagnostic)


def _read(path: Path, expected: str | None = None) -> tuple[bytes, str]:
    raw = safe_path(path).read_bytes()
    found = _sha(raw)
    _require(expected is None or found == expected, "frozen_input_hash_mismatch")
    return raw, found


def _safe_relative(root: Path, relative: str) -> Path:
    value = Path(relative)
    _require(
        isinstance(relative, str) and relative and not value.is_absolute()
        and "\\" not in relative and ":" not in relative and ".." not in value.parts,
        "unsafe_relative_input_path",
    )
    path = _absolute(root / value)
    _require(path.is_relative_to(_absolute(root)), "unsafe_relative_input_path")
    return safe_path(path)


def _record(root: Path, role: str, path: Path, expected: str | None = None) -> dict[str, Any]:
    absolute = _absolute(path)
    _require(absolute.is_relative_to(_absolute(root)), "input_outside_repository")
    raw, found = _read(absolute, expected)
    return {
        "role": role,
        "path": absolute.relative_to(_absolute(root)).as_posix(),
        "sha256": found,
        "bytes": len(raw),
    }


def _verify_evidence_inventory(
    baseline: Path, acceptance: dict, delivery: dict,
    *, _sources: _SourceDescription | None = None,
) -> tuple[dict, list[dict]]:
    sources = _sources or _production_source_description()
    inventory_path = baseline / "evidence-inventory.json"
    inventory_pin = sources.file_sha256(inventory_path.relative_to(baseline.parent.parent.parent).as_posix())
    inventory_raw, inventory_hash = _read(inventory_path, inventory_pin)
    inventory = strict_json(inventory_raw)
    entry_count = sources.dataset_count("evidence_inventory_entries")
    total_bytes_expected = sources.dataset_count("evidence_inventory_bytes")
    _require(
        inventory.get("schema_version") == 1
        and inventory.get("kind") == "curry_option_confirmation_evidence_inventory"
        and inventory.get("scope") == "curry-option-confirmation-v1"
        and inventory.get("measured_root") == sources.baseline_relative
        and inventory.get("entry_count") == entry_count
        and isinstance(inventory.get("entries"), list)
        and len(inventory["entries"]) == entry_count
        and inventory.get("accessible_file_bytes") == total_bytes_expected
        and inventory.get("complete_for_measured_root") is True
        and inventory.get("access_errors") == [],
        "evidence_inventory_contract_mismatch",
    )
    _require(
        acceptance.get("evidence_inventory", {}).get("path") == "evidence-inventory.json"
        and acceptance.get("evidence_inventory", {}).get("sha256") == inventory_hash
        and acceptance.get("evidence_inventory", {}).get("covered_entries") == entry_count
        and acceptance.get("evidence_inventory", {}).get("covered_bytes") == total_bytes_expected
        and delivery.get("evidence_inventory", {}).get("sha256") == inventory_hash,
        "evidence_inventory_anchor_mismatch",
    )
    seen: set[str] = set()
    records = []
    total_bytes = 0
    for item in inventory["entries"]:
        _require(isinstance(item, dict) and set(item) == {"path", "sha256", "bytes"}, "evidence_inventory_entry_invalid")
        relative = item["path"]
        _require(relative not in seen and HASH.fullmatch(item["sha256"]) is not None, "evidence_inventory_entry_invalid")
        seen.add(relative)
        path = _safe_relative(baseline, relative)
        raw, found = _read(path, item["sha256"])
        _require(len(raw) == item["bytes"], "evidence_inventory_size_mismatch")
        total_bytes += len(raw)
        records.append({
            "role": f"confirmation_evidence_file_{len(records) + 1:03d}",
            "path": (Path(sources.baseline_relative) / relative).as_posix(),
            "sha256": found,
            "bytes": len(raw),
        })
    _require(total_bytes == inventory["accessible_file_bytes"], "evidence_inventory_total_mismatch")
    excluded = set(inventory.get("excluded_from_measurement", []))
    _require(excluded == {"acceptance.json", "evidence-inventory.json", "final-build/delivery.json"}, "evidence_inventory_exclusions_invalid")
    return inventory, records


def _verify_source_archive(
    archive_path: Path,
    list_path: Path,
    *,
    expected_archive_sha256: str | None,
    expected_list_sha256: str | None,
    expected_identity: str,
    expected_count: int,
    expected_head: str = EXPECTED_HEAD,
) -> tuple[dict[str, str], dict[str, Any]]:
    archive_raw, archive_hash = _read(archive_path, expected_archive_sha256)
    list_raw, list_hash = _read(list_path, expected_list_sha256)
    listing = strict_json(list_raw)
    files = listing.get("files") if isinstance(listing, dict) else None
    _require(isinstance(listing, dict), "source_archive_file_list_invalid")
    _require(
        listing.get("schema_version") == 1
        and listing.get("kind") == "workspace_source_archive"
        and listing.get("head") == expected_head
        and listing.get("source_identity") == expected_identity
        and listing.get("file_count") == expected_count
        and isinstance(files, dict)
        and len(files) == expected_count
        and digest(canonical({"head": expected_head, "files": files})) == expected_identity,
        "source_archive_file_list_invalid",
    )
    for name, expected in files.items():
        part = Path(name)
        _require(
            isinstance(name, str) and name and not part.is_absolute() and "\\" not in name
            and ":" not in name and ".." not in part.parts and HASH.fullmatch(expected) is not None,
            "source_archive_entry_invalid",
        )
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            _require(len(names) == len(set(names)) and set(names) == set(files), "source_archive_membership_invalid")
            for name, expected in files.items():
                _require(_sha(archive.read(name)) == expected, "source_archive_member_hash_mismatch")
    except (OSError, zipfile.BadZipFile, KeyError):
        raise ValueError("source_archive_invalid") from None
    return files, {
        "archive_sha256": archive_hash,
        "archive_bytes": len(archive_raw),
        "file_list_sha256": list_hash,
        "source_identity": expected_identity,
        "file_count": expected_count,
    }


def verify_source_archive_pair(
    native_archive: Path,
    native_list: Path,
    final_archive: Path,
    final_list: Path,
    *,
    expected_native_count: int = 501,
    expected_final_count: int = 502,
    expected_native_archive_sha256: str | None = NATIVE_ARCHIVE_SHA256,
    expected_native_list_sha256: str | None = NATIVE_LIST_SHA256,
    expected_native_identity: str = NATIVE_SOURCE_IDENTITY,
    expected_final_archive_sha256: str | None = FINAL_ARCHIVE_SHA256,
    expected_final_list_sha256: str | None = FINAL_LIST_SHA256,
    expected_final_identity: str = FINAL_SOURCE_IDENTITY,
    expected_head: str = EXPECTED_HEAD,
    expected_differences: tuple[str, ...] = tuple(sorted(ALLOWED_ARCHIVE_DIFFS)),
) -> dict[str, Any]:
    """Verify the archived source snapshots and their exact documented delta."""
    native, native_record = _verify_source_archive(
        native_archive, native_list,
        expected_archive_sha256=expected_native_archive_sha256,
        expected_list_sha256=expected_native_list_sha256,
        expected_identity=expected_native_identity,
        expected_count=expected_native_count,
        expected_head=expected_head,
    )
    final, final_record = _verify_source_archive(
        final_archive, final_list,
        expected_archive_sha256=expected_final_archive_sha256,
        expected_list_sha256=expected_final_list_sha256,
        expected_identity=expected_final_identity,
        expected_count=expected_final_count,
        expected_head=expected_head,
    )
    differences = sorted(name for name in native.keys() | final.keys() if native.get(name) != final.get(name))
    _require(
        set(differences) == set(expected_differences),
        "source_archive_difference_set_invalid",
    )
    return {
        "native": native_record,
        "final": final_record,
        "native_file_count": len(native),
        "final_file_count": len(final),
        "differences": differences,
    }


def audit_hash_role_semantics(
    files: dict[str, Path], preparation: dict, expected_hashes: dict[str, str]
) -> dict[str, Any]:
    """Reproduce the old container-file mismatch, then run the shared repaired gate."""
    from ygo_eval.native_curry_option_validation import (
        _capture_manifest_input_state,
        _verify_manifest_input_state,
    )

    semantic_hashes, raw_snapshot = _capture_manifest_input_state(files, preparation)
    legacy_mismatches = []
    for role in ("base_request", "candidate_case"):
        path = _absolute(files[role])
        actual_raw_hash = raw_snapshot[path]
        if expected_hashes.get(role) != actual_raw_hash:
            legacy_mismatches.append({
                "role": role,
                "expected_object_sha256": expected_hashes.get(role),
                "container_file_sha256": actual_raw_hash,
                "actual_object_sha256": semantic_hashes.get(role),
            })
    _verify_manifest_input_state(files, preparation, expected_hashes)
    return {
        "semantic_sha256": semantic_hashes,
        "raw_file_sha256": {path.as_posix(): value for path, value in raw_snapshot.items()},
        "legacy_raw_mismatches": legacy_mismatches,
        "repaired_gate_passed": True,
    }


def verify_archived_refusal_source_members(
    authenticated_files: dict[str, str],
    members: dict[str, bytes],
    records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Bind the two archived source members to an already authenticated file list."""
    result = records if records is not None else []
    for role, relative in (
        ("native_module", NATIVE_SOURCE_PATH),
        ("research_module", RESEARCH_SOURCE_PATH),
    ):
        expected = authenticated_files.get(relative)
        raw = members.get(relative)
        found = _sha(raw) if isinstance(raw, bytes) else None
        valid = isinstance(expected, str) and HASH.fullmatch(expected) is not None and found == expected
        result.append({
            "role": role,
            "path": relative,
            "expected_sha256": expected,
            "actual_sha256": found,
            "status": "passed" if valid else "failed",
        })
        _require(valid, "archived_source_member_hash_mismatch")
    return result


def manifest_role_input_records(
    repo: Path, files: dict[str, Path], raw_snapshot: dict[str, str],
) -> list[dict[str, Any]]:
    """Record raw container files while semantic object hashes remain separate."""
    result = []
    for role, path in files.items():
        absolute = _absolute(path)
        raw_hash = raw_snapshot.get(absolute.as_posix())
        _require(isinstance(raw_hash, str) and HASH.fullmatch(raw_hash) is not None,
                 "manifest_role_raw_snapshot_missing")
        result.append(_record(repo, "manifest_role_" + role, path, raw_hash))
    return result


def _confirmation_source_baseline(repo: Path) -> Path:
    """Return the fixed asset-audit root that supplied the confirmation delivery."""
    from ygo_eval.native_curry_option_validation import CONFIRMATION_SCOPE

    return _absolute(repo / CONFIRMATION_SCOPE.baseline_root)


def new_report(
    report_version: int = 1, *, _sources: _SourceDescription | None = None,
) -> dict[str, Any]:
    if report_version not in (1, 2):
        raise ValueError("audit_report_version_invalid")
    sources = _sources or _production_source_description()
    baseline = sources.baseline_relative
    report = {
        "schema_version": report_version,
        "kind": "curry_input_recovery_audit" if report_version == 1 else "curry_input_recovery_audit_v2",
        "status": "incomplete",
        "failure_checkpoint": None,
        "anchors": {
            "acceptance_sha256": sources.file_sha256(f"{baseline}/acceptance.json"),
            "delivery_sha256": sources.file_sha256(f"{baseline}/final-build/delivery.json"),
            "inventory_sha256": sources.file_sha256(f"{baseline}/evidence-inventory.json"),
        },
        "tool_identity": None,
        "checks": {name: "not_run" for name in CHECK_NAMES},
        "native_calls": 0,
        "execution_ready": False,
        "process_actions": {
            "runner_started": False,
            "worker_started": False,
            "ffi_called": False,
            "writable_ledger_opened": False,
        },
        "historical": {
            "consumed": None,
            "unknown": None,
            "ledger_count": None,
            "verified_without_writable_journal": False,
            "input_set_sha256": None,
        },
        "confirmation_scope": {
            "scope": "curry-option-confirmation-v1",
            "prepared": None,
            "execution_ready": False,
            "new_consumed": None,
            "cumulative_consumed": None,
            "new_unknown": None,
            "unconsumed_slots_sealed": 7,
            "native_validation_passed": False,
        },
        "hash_mismatch": None,
        "historical_exit_observation": {
            "observation_exit_code": 1,
            "archived_refusal_branch_return_code": 2,
            "historical_exit_code_certified": False,
            "raw_normal_stdout_stderr_saved": False,
        },
        "source_archives": [],
        "source_archive_differences": [],
        "inputs": [],
        "qualifications": dict(FLAGS),
        "diagnostics": [],
        "elapsed_seconds": 0.0,
    }
    if report_version == 2:
        report["historical_exit_observation"] = {
            "observation_exit_code": None,
            "archived_refusal_branch_return_code": None,
            "historical_exit_code_certified": False,
            "raw_normal_stdout_stderr_saved": False,
        }
        report["archived_source_members"] = []
        report["stability"] = {
            "source_identity": "not_collected",
            "confirmation_tree": "not_collected",
            "protected_material": "not_collected",
            "confirmation_ledger_absence": "not_collected",
            "ledger_absent_before": None,
            "ledger_absent_after": None,
        }
    return report


def validate_report(
    report: dict[str, Any], *, _sources: _SourceDescription | None = None,
) -> bool:
    sources = _sources or _production_source_description()
    baseline = sources.baseline_relative
    expected_consumed, expected_unknown, expected_ledger_count = _historical_dataset_counts(sources)
    version = report.get("schema_version") if isinstance(report, dict) else None
    _require(version in (1, 2), "audit_schema_version_invalid")
    _require(isinstance(report, dict) and report.get("kind") == (
        "curry_input_recovery_audit" if version == 1 else "curry_input_recovery_audit_v2"
    ), "audit_kind_invalid")
    _require(report.get("status") in {"passed", "failed", "incomplete"}, "audit_status_invalid")
    checkpoint = report.get("failure_checkpoint")
    _require(checkpoint is None or checkpoint in CHECK_NAMES, "audit_failure_checkpoint_invalid")
    _require(report.get("anchors") == {
        "acceptance_sha256": sources.file_sha256(f"{baseline}/acceptance.json"),
        "delivery_sha256": sources.file_sha256(f"{baseline}/final-build/delivery.json"),
        "inventory_sha256": sources.file_sha256(f"{baseline}/evidence-inventory.json"),
    }, "audit_anchor_set_invalid")
    tool_identity = report.get("tool_identity")
    _require(
        tool_identity is None
        or (isinstance(tool_identity, dict)
            and set(tool_identity) == {"head", "identity", "file_count"}
            and isinstance(tool_identity.get("head"), str)
            and HASH.fullmatch(tool_identity.get("identity", "")) is not None
            and type(tool_identity.get("file_count")) is int
            and tool_identity["file_count"] > 0),
        "audit_tool_identity_invalid",
    )
    _require(report.get("native_calls") == 0 and report.get("execution_ready") is False, "audit_scope_invalid")
    _require(report.get("process_actions") == {
        "runner_started": False, "worker_started": False,
        "ffi_called": False, "writable_ledger_opened": False,
    }, "audit_process_action_invalid")
    _require(report.get("qualifications") == FLAGS, "audit_qualification_invalid")
    history = report.get("historical")
    _require(
        isinstance(history, dict)
        and (history.get("consumed"), history.get("unknown"), history.get("ledger_count"))
        in {(None, None, None), (expected_consumed, expected_unknown, expected_ledger_count)}
        and type(history.get("verified_without_writable_journal")) is bool
        and (history.get("verified_without_writable_journal") is True)
        == (history.get("consumed") == expected_consumed),
        "audit_history_accounting_invalid",
    )
    _require(
        history.get("input_set_sha256") is None
        or HASH.fullmatch(history.get("input_set_sha256", "")) is not None,
        "audit_history_input_hash_invalid",
    )
    scope = report.get("confirmation_scope")
    _require(
        isinstance(scope, dict)
        and scope.get("scope") == "curry-option-confirmation-v1"
        and scope.get("execution_ready") is False
        and scope.get("new_consumed") is None
        and scope.get("cumulative_consumed") is None
        and scope.get("new_unknown") is None
        and scope.get("unconsumed_slots_sealed") == 7
        and scope.get("native_validation_passed") is False,
        "confirmation_consumption_must_remain_unknown",
    )
    observation = report.get("historical_exit_observation")
    if version == 1:
        _require(observation == {
            "observation_exit_code": 1,
            "archived_refusal_branch_return_code": 2,
            "historical_exit_code_certified": False,
            "raw_normal_stdout_stderr_saved": False,
        }, "historical_exit_observation_invalid")
    else:
        _require(
            isinstance(observation, dict)
            and observation.get("observation_exit_code") in (None, 1)
            and observation.get("archived_refusal_branch_return_code") in (None, 2)
            and observation.get("historical_exit_code_certified") is False
            and observation.get("raw_normal_stdout_stderr_saved") is False,
            "historical_exit_observation_invalid",
        )
        stability = report.get("stability")
        statuses = {"not_collected", "passed", "failed", "verification_failed"}
        _require(
            isinstance(stability, dict)
            and set(stability) == {
                "source_identity", "confirmation_tree", "protected_material",
                "confirmation_ledger_absence", "ledger_absent_before", "ledger_absent_after",
            }
            and all(stability.get(key) in statuses for key in (
                "source_identity", "confirmation_tree", "protected_material", "confirmation_ledger_absence"
            ))
            and all(stability.get(key) in (None, True, False) for key in (
                "ledger_absent_before", "ledger_absent_after"
            )),
            "audit_stability_record_invalid",
        )
        _require(isinstance(report.get("archived_source_members"), list), "archived_source_members_invalid")
        role_paths = {
            "native_module": NATIVE_SOURCE_PATH,
            "research_module": RESEARCH_SOURCE_PATH,
        }
        for item in report["archived_source_members"]:
            hashes_match = (
                item.get("expected_sha256") is not None
                and item.get("actual_sha256") is not None
                and item.get("expected_sha256") == item.get("actual_sha256")
            ) if isinstance(item, dict) else False
            _require(
                isinstance(item, dict)
                and set(item) == {"role", "path", "expected_sha256", "actual_sha256", "status"}
                and item.get("role") in {"native_module", "research_module"}
                and item.get("path") == role_paths.get(item.get("role"))
                and (item.get("expected_sha256") is None or HASH.fullmatch(item["expected_sha256"]))
                and (item.get("actual_sha256") is None or HASH.fullmatch(item["actual_sha256"]))
                and item.get("status") in {"passed", "failed"},
                "archived_source_member_record_invalid",
            )
            _require(
                (item["status"] == "passed") == hashes_match,
                "archived_source_member_hash_status_mismatch",
            )
    checks = report.get("checks")
    _require(
        isinstance(checks, dict) and set(checks) == set(CHECK_NAMES)
        and all(value in {"not_run", "passed", "failed"} for value in checks.values()),
        "audit_checks_invalid",
    )
    if version == 2:
        _require(
            (observation["observation_exit_code"] == 1)
            == (checks["evidence_inventory"] == "passed")
            and (observation["archived_refusal_branch_return_code"] == 2)
            == (checks["source_archives"] == "passed"),
            "historical_exit_observation_checkpoint_mismatch",
        )
    _require(isinstance(report.get("diagnostics"), list), "audit_diagnostics_invalid")
    for diagnostic in report["diagnostics"]:
        _require(isinstance(diagnostic, str) and re.fullmatch(r"[a-z][a-z0-9_]{1,90}", diagnostic) is not None, "audit_diagnostic_invalid")
    for item in report.get("inputs", []):
        relative = item.get("path") if isinstance(item, dict) else None
        _require(
            isinstance(relative, str) and not Path(relative).is_absolute()
            and "\\" not in relative and ":" not in relative and ".." not in Path(relative).parts
            and re.fullmatch(r"[a-z][a-z0-9_-]{1,100}", item.get("role", "")) is not None
            and HASH.fullmatch(item.get("sha256", "")) is not None
            and type(item.get("bytes")) is int and item["bytes"] >= 0,
            "audit_input_record_invalid",
        )
    if report.get("hash_mismatch") is not None:
        mismatch = report["hash_mismatch"]
        _require(
            isinstance(mismatch, dict)
            and mismatch.get("first_legacy_mismatch_role") == "base_request"
            and mismatch.get("legacy_comparison") == "raw_container_file_sha256"
            and mismatch.get("manifest_role_hashing") == "canonical_extracted_object_sha256"
            and mismatch.get("repaired_shared_gate_passed") is True
            and isinstance(mismatch.get("legacy_raw_mismatches"), list)
            and [item.get("role") for item in mismatch["legacy_raw_mismatches"]] == ["base_request", "candidate_case"],
            "audit_hash_mismatch_diagnosis_invalid",
        )
    if report["status"] == "passed":
        _require(
            checkpoint is None
            and all(value == "passed" for value in checks.values())
            and history.get("consumed") == expected_consumed
            and report.get("hash_mismatch", {}).get("repaired_shared_gate_passed") is True
            and len(report.get("source_archives", [])) == 2
            and report.get("source_archive_differences") == list(sources.differences("confirmation"))
            and tool_identity is not None
            and scope.get("prepared") is True,
            "audit_success_claim_invalid",
        )
        if version == 2:
            member_records = report["archived_source_members"]
            _require(
                {item["role"] for item in member_records} == {"native_module", "research_module"}
                and all(item["status"] == "passed" for item in member_records)
                and observation["observation_exit_code"] == 1
                and observation["archived_refusal_branch_return_code"] == 2
                and all(value == "passed" for value in report["stability"].values()
                        if isinstance(value, str))
                and report["stability"]["ledger_absent_before"] is True
                and report["stability"]["ledger_absent_after"] is True,
                "audit_v2_success_claim_invalid",
            )
    elif report["status"] == "failed":
        _require(
            checkpoint in CHECK_NAMES and checks.get(checkpoint) == "failed",
            "audit_failure_checkpoint_inconsistent",
        )
        if version == 2:
            order = {name: index for index, name in enumerate(CHECK_NAMES)}
            index = order[checkpoint]
            _require(
                all(checks[name] == "passed" for name in CHECK_NAMES[:index])
                and all(checks[name] == "not_run" for name in CHECK_NAMES[index + 1:]),
                "audit_v2_failure_progression_invalid",
            )
    return True


def _snapshot_tree(root: Path) -> dict[str, dict[str, Any]]:
    root = safe_path(root, file=False)
    result: dict[str, dict[str, Any]] = {}
    for item in sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()):
        if item.is_dir():
            safe_path(item, file=False)
            result[item.relative_to(root).as_posix()] = {"kind": "directory"}
        else:
            raw, found = _read(item)
            result[item.relative_to(root).as_posix()] = {"kind": "file", "sha256": found, "bytes": len(raw)}
    return result


def _verify_confirmation_material(
    repo: Path, baseline: Path, report: dict,
    *, _sources: _SourceDescription | None = None,
) -> tuple[dict, dict[Path, str]]:
    sources = _sources or _production_source_description()
    from ygo_eval.native_curry_option_validation import (
        CONFIRMATION_SCOPE,
        FROZEN_CASES_PATH,
        PREPARATION_PATH,
        PREPARATION_REPORT_PATH,
        PREPARATION_ACCEPTANCE_PATH,
        _capture_manifest_input_state,
        _curry_manifest_files,
        _pinned_inputs,
        _protected_curry_hash,
        _resolve_curry_banlist_path,
        _verify_confirmation_baseline,
        _verify_manifest_input_state,
        _verify_saved_confirmation_build_and_archive,
        verify_curry_preparation,
    )

    report["failure_checkpoint"] = "acceptance_delivery_anchors"
    before_tree = _snapshot_tree(baseline)
    acceptance_path = baseline / "acceptance.json"
    delivery_path = baseline / "final-build/delivery.json"
    acceptance_expected = sources.file_sha256(acceptance_path.relative_to(repo).as_posix())
    delivery_expected = sources.file_sha256(delivery_path.relative_to(repo).as_posix())
    inventory_path = baseline / "evidence-inventory.json"
    inventory_expected = sources.file_sha256(inventory_path.relative_to(repo).as_posix())
    acceptance_raw, acceptance_hash = _read(acceptance_path, acceptance_expected)
    delivery_raw, delivery_hash = _read(delivery_path, delivery_expected)
    acceptance = strict_json(acceptance_raw)
    delivery = strict_json(delivery_raw)
    expected_accounting = {
        "cumulative_consumed": None,
        "historical_consumed": 32,
        "historical_unknown": 0,
        "new_consumed": None,
        "new_unknown": None,
        "status": "unknown_without_authenticated_ledger",
    }
    _require(
        acceptance.get("schema_version") == 1
        and acceptance.get("kind") == "native_curry_option_confirmation_acceptance"
        and acceptance.get("scope") == CONFIRMATION_SCOPE.scope
        and acceptance.get("status") == "partial"
        and acceptance.get("accounting") == expected_accounting
        and acceptance.get("qualification") == {
            "complete_action_coverage": False,
            "global_optimality": False,
            "issuance_evidence": "unknown",
            "native_probability_verified": False,
            "proof_ready": False,
            "successful": False,
        },
        "confirmation_acceptance_content_invalid",
    )
    _require(
        delivery.get("schema_version") == 1
        and delivery.get("kind") == "native_curry_option_confirmation_delivery"
        and delivery.get("status") == "partial_stopped_before_authenticated_stage"
        and delivery.get("accounting") == expected_accounting
        and delivery.get("qualification") == acceptance["qualification"]
        and delivery.get("scope", {}).get("id") == CONFIRMATION_SCOPE.scope
        and delivery.get("scope", {}).get("request_limit") == 7
        and delivery.get("scope", {}).get("wall_seconds_limit") == 7200
        and delivery.get("prepared", {}).get("prepared") is True
        and delivery.get("prepared", {}).get("execution_ready") is True
        and delivery.get("prepared", {}).get("native_calls") == 0
        and delivery.get("verification", {}).get("valid") is False
        and delivery.get("normal_attempt", {}).get("exit_code") == 1
        and delivery.get("normal_attempt", {}).get("worker_request_consumption") is None
        and delivery.get("normal_attempt", {}).get("authenticated_ledger_present") is False,
        "confirmation_delivery_content_invalid",
    )
    observation = strict_json(_read(baseline / "research/normal-attempt-observation.json")[0])
    _require(
        observation.get("kind") == "curry_option_confirmation_normal_attempt_observation"
        and observation.get("exit_code") == 1
        and observation.get("worker_request_consumption") is None
        and observation.get("normal_process_diagnostic_present") is False
        and observation.get("raw_process_output_saved") is False,
        "normal_attempt_observation_invalid",
    )
    # Acceptance and delivery are independently anchored here. The observation
    # file's claimed exit code remains unknown until inventory authenticates it.
    report["checks"]["acceptance_delivery_anchors"] = "passed"
    report["failure_checkpoint"] = "evidence_inventory"
    inventory, inventory_records = _verify_evidence_inventory(
        baseline, acceptance, delivery, _sources=sources,
    )
    report["inputs"].extend([
        _record(repo, "confirmation_acceptance", acceptance_path, acceptance_hash),
        _record(repo, "confirmation_delivery", delivery_path, delivery_hash),
        _record(repo, "confirmation_evidence_inventory", inventory_path, inventory_expected),
        _record(repo, "normal_attempt_observation", baseline / "research/normal-attempt-observation.json"),
        *inventory_records,
    ])
    if report["schema_version"] == 2:
        report["historical_exit_observation"]["observation_exit_code"] = observation["exit_code"]
    report["checks"]["evidence_inventory"] = "passed"

    report["failure_checkpoint"] = "source_archives"
    native_archive_pin = sources.archive("confirmation_native_archive")
    final_archive_pin = sources.archive("confirmation_final_archive")
    pair = verify_source_archive_pair(
        baseline / "source-native.zip", baseline / "source-native-file-list.json",
        baseline / "final-build/source-native.zip", baseline / "final-build/source-native-file-list.json",
        expected_native_count=native_archive_pin.file_count,
        expected_final_count=final_archive_pin.file_count,
        expected_native_archive_sha256=native_archive_pin.archive_sha256,
        expected_native_list_sha256=native_archive_pin.file_list_sha256,
        expected_native_identity=native_archive_pin.source_identity,
        expected_final_archive_sha256=final_archive_pin.archive_sha256,
        expected_final_list_sha256=final_archive_pin.file_list_sha256,
        expected_final_identity=final_archive_pin.source_identity,
        expected_head=native_archive_pin.head,
        expected_differences=sources.differences("confirmation"),
    )
    _require(
        delivery.get("source", {}).get("identity") == final_archive_pin.source_identity
        and delivery.get("source", {}).get("file_count") == final_archive_pin.file_count
        and delivery.get("source", {}).get("archive", {}).get("sha256") == final_archive_pin.archive_sha256
        and delivery.get("source", {}).get("file_list", {}).get("sha256") == final_archive_pin.file_list_sha256,
        "delivery_source_archive_binding_invalid",
    )
    _require(
        pair["differences"] == sorted(sources.differences("confirmation")),
        "confirmation_source_archive_difference_set_invalid",
    )
    report["source_archives"] = [pair["native"], pair["final"]]
    report["source_archives"][0]["role"] = "native_time"
    report["source_archives"][1]["role"] = "final"
    report["source_archive_differences"] = pair["differences"]
    report["inputs"].extend([
        _record(repo, "native_source_archive", baseline / "source-native.zip", native_archive_pin.archive_sha256),
        _record(repo, "native_source_file_list", baseline / "source-native-file-list.json", native_archive_pin.file_list_sha256),
        _record(repo, "final_source_archive", baseline / "final-build/source-native.zip", final_archive_pin.archive_sha256),
        _record(repo, "final_source_file_list", baseline / "final-build/source-native-file-list.json", final_archive_pin.file_list_sha256),
    ])
    native_source, native_list = _verify_source_archive(
        baseline / "source-native.zip", baseline / "source-native-file-list.json",
        expected_archive_sha256=native_archive_pin.archive_sha256,
        expected_list_sha256=native_archive_pin.file_list_sha256,
        expected_identity=native_archive_pin.source_identity,
        expected_count=native_archive_pin.file_count,
        expected_head=native_archive_pin.head,
    )
    final_source, final_list = _verify_source_archive(
        baseline / "final-build/source-native.zip", baseline / "final-build/source-native-file-list.json",
        expected_archive_sha256=final_archive_pin.archive_sha256,
        expected_list_sha256=final_archive_pin.file_list_sha256,
        expected_identity=final_archive_pin.source_identity,
        expected_count=final_archive_pin.file_count,
        expected_head=final_archive_pin.head,
    )
    with zipfile.ZipFile(baseline / "source-native.zip") as archive:
        old_code = archive.read(NATIVE_SOURCE_PATH)
        old_research = archive.read(RESEARCH_SOURCE_PATH)
    member_bytes = {NATIVE_SOURCE_PATH: old_code, RESEARCH_SOURCE_PATH: old_research}
    if report["schema_version"] == 2:
        verify_archived_refusal_source_members(
            native_source, member_bytes, report["archived_source_members"],
        )
    else:
        verify_archived_refusal_source_members(native_source, member_bytes)
    old_code_text = old_code.decode("utf-8")
    old_research_text = old_research.decode("utf-8")
    _require(
        "for role, path in frozen_paths.items()" in old_code_text
        and '_sha(safe_path(path).read_bytes()) != manifest["input_sha256"].get(role)' in old_code_text
        and 'hashes["base_request"] = _sha(_case_encode(preparation["base_request"]))' in old_code_text
        and 'hashes["candidate_case"] = _sha(_case_encode(preparation["candidate_case"]))' in old_code_text
        and "native-curry-option-confirmation refused: frozen input, build, ledger, or output check failed" in old_research_text,
        "archived_raw_hash_comparison_not_found",
    )
    _require(
        "return 2" in old_research_text[
            old_research_text.index("if args.command == 'native-curry-option-confirmation':"):
            old_research_text.index("if args.command == 'audit-tenki-placement-preflight':")
        ],
        "archived_refusal_return_code_not_found",
    )
    if report["schema_version"] == 2:
        archived_return = _archived_refusal_return_code(old_research_text)
        _require(archived_return == 2, "archived_refusal_return_code_not_found")
        report["historical_exit_observation"]["archived_refusal_branch_return_code"] = archived_return
    report["checks"]["source_archives"] = "passed"

    report["failure_checkpoint"] = "frozen_input_binding"
    from ygo_eval.native_curry_option_validation import (
        _case_encode,
        _confirmation_protected_hash,
    )
    manifest_path = baseline / "research/manifest.json"
    manifest_raw, manifest_hash = _read(manifest_path)
    manifest = strict_json(manifest_raw)
    _require(
        manifest.get("schema_version") == 1
        and manifest.get("kind") == "native_curry_option_confirmation_manifest"
        and manifest.get("scope") == CONFIRMATION_SCOPE.scope
        and manifest.get("batch_kind") == CONFIRMATION_SCOPE.batch_kind
        and manifest.get("old_consumed") == 32
        and manifest.get("limit") == 7
        and manifest.get("wall_seconds") == 7200
        and digest(canonical({key: value for key, value in manifest.items() if key != "context"})) == manifest.get("context"),
        "confirmation_manifest_binding_invalid",
    )
    preparation = verify_curry_preparation(
        repo=repo,
        preparation=repo / PREPARATION_PATH,
        preparation_report=repo / PREPARATION_REPORT_PATH,
        preparation_acceptance=repo / PREPARATION_ACCEPTANCE_PATH,
        cases_path=repo / FROZEN_CASES_PATH,
        operations_source=repo / "data/tmp/ocgcore-source/operations.cpp",
        _sources=sources.child("static_preparation"),
    )
    input_paths = {
        "runner": baseline / "native-artifacts/curry-option-confirmation.exe",
        "worker": baseline / "native-artifacts/ygo-engine-worker.exe",
        "build_record": baseline / "build-record.json",
        "identity": baseline / "identity.json",
        "window_start": baseline / "window-start.json",
        "cli": baseline / "native-artifacts/ygo-cli.exe",
        "source_archive": baseline / "source-native.zip",
        "source_file_list": baseline / "source-native-file-list.json",
        "ordinary_config": baseline / "ordinary-candidate.toml",
        "tournament_config": baseline / "tournament-candidate.toml",
    }
    banlist_path = _resolve_banlist(repo, preparation["base_request_entry"].get("banlist_path", ""))
    manifest_files = _curry_manifest_files(repo, baseline, input_paths, preparation, banlist_path, CONFIRMATION_SCOPE)
    semantic_hashes, raw_snapshot = _capture_manifest_input_state(manifest_files, preparation)
    raw_container_hashes = {
        role: raw_snapshot[_absolute(manifest_files[role])]
        for role in ("base_request", "candidate_case")
    }
    legacy_mismatches = [
        {
            "role": role,
            "expected_object_sha256": manifest.get("input_sha256", {}).get(role),
            "container_file_sha256": raw_container_hashes[role],
            "actual_object_sha256": semantic_hashes.get(role),
        }
        for role in ("base_request", "candidate_case")
        if manifest.get("input_sha256", {}).get(role) != raw_container_hashes[role]
    ]
    raw_protections = _verify_manifest_input_state(
        manifest_files, preparation, manifest.get("input_sha256", {}),
    )
    _require(
        [item["role"] for item in legacy_mismatches] == ["base_request", "candidate_case"]
        and semantic_hashes["base_request"] == manifest["input_sha256"]["base_request"]
        and semantic_hashes["candidate_case"] == manifest["input_sha256"]["candidate_case"],
        "frozen_role_hash_repair_binding_invalid",
    )
    report["hash_mismatch"] = {
        "legacy_comparison": "raw_container_file_sha256",
        "manifest_role_hashing": "canonical_extracted_object_sha256",
        "first_legacy_mismatch_role": "base_request",
        "legacy_raw_mismatches": legacy_mismatches,
        "semantic_sha256": {role: semantic_hashes[role] for role in ("base_request", "candidate_case")},
        "container_file_sha256": raw_container_hashes,
        "repaired_shared_gate_passed": True,
        "old_confirmation_report_rewritten": False,
    }
    report["inputs"].append(_record(repo, "confirmation_manifest", manifest_path, manifest_hash))
    raw_file_hashes = {path.as_posix(): value for path, value in raw_snapshot.items()}
    report["inputs"].extend(manifest_role_input_records(repo, manifest_files, raw_file_hashes))

    request_path = baseline / "research/stage-1-request.json"
    input_path = baseline / "research/stage-1-input.json"
    seal_path = baseline / "research/stage-1-input-seal.json"
    request_raw, request_hash = _read(request_path)
    request = strict_json(request_raw)
    input_raw, input_hash = _read(input_path)
    invocation = strict_json(input_raw)
    seal_raw, seal_hash = _read(seal_path)
    seal = strict_json(seal_raw)
    _require(
        request == manifest.get("request")
        and digest(canonical(request)) == manifest.get("stage1_request_sha256")
        and invocation.get("context") == manifest.get("context")
        and invocation.get("stage") == 1
        and invocation.get("batch_kind") == CONFIRMATION_SCOPE.batch_kind
        and invocation.get("request") == request
        and invocation.get("expected_identity") == manifest.get("assets", {}).get("ordinary")
        and seal == {
            "schema_version": 1,
            "kind": CONFIRMATION_SCOPE.input_seal_kind,
            "context": manifest.get("context"),
            "stage": 1,
            "input_sha256": input_hash,
        },
        "confirmation_request_input_or_seal_binding_invalid",
    )
    prepared_path = baseline / "research/prepared.json"
    prepared_raw, prepared_hash = _read(prepared_path)
    prepared = strict_json(prepared_raw)
    _require(
        prepared.get("context") == manifest.get("context")
        and prepared.get("prepared") is True
        and prepared.get("execution_ready") is True
        and prepared.get("native_calls") == 0
        and prepared.get("manifest_sha256") == manifest_hash
        and prepared.get("stage1_request_sha256") == manifest.get("stage1_request_sha256")
        and prepared.get("stage1_input_sha256") == input_hash,
        "confirmation_prepared_binding_invalid",
    )
    _verify_saved_confirmation_build_and_archive(baseline, manifest, input_paths)
    identity_raw, identity_hash = _read(input_paths["identity"])
    identity = strict_json(identity_raw)
    _require(
        identity.get("kind") == "workspace_identity"
        and identity.get("consistent") is True
        and digest(canonical({key: value for key, value in identity.items() if key != "identity"})) == identity.get("identity")
        and identity.get("runtimes", {}).get("ordinary") == manifest.get("assets", {}).get("ordinary"),
        "confirmation_identity_binding_invalid",
    )
    window = strict_json(_read(input_paths["window_start"])[0])
    _require(
        window.get("scope") == CONFIRMATION_SCOPE.scope
        and window.get("limit") == 7 and window.get("wall_seconds") == 7200
        and window.get("started_at") == manifest.get("started_at"),
        "confirmation_window_binding_invalid",
    )
    # This report audits immutable input readiness only; it never authorizes
    # another normal attempt, even when the old prepared record is valid.
    report["confirmation_scope"]["prepared"] = True
    report["inputs"].extend([
        _record(repo, "stage1_request", request_path, request_hash),
        _record(repo, "stage1_input", input_path, input_hash),
        _record(repo, "stage1_input_seal", seal_path, seal_hash),
        _record(repo, "prepared", prepared_path, prepared_hash),
        _record(repo, "workspace_identity", input_paths["identity"], identity_hash),
    ])
    report["checks"]["frozen_input_binding"] = "passed"

    report["failure_checkpoint"] = "historical_ledgers"
    if report["schema_version"] == 2:
        ledger_path = baseline / "research/calls.jsonl"
        ledger_absent = not ledger_path.exists() and not ledger_path.is_symlink()
        report["stability"]["ledger_absent_before"] = ledger_absent
        report["stability"]["confirmation_ledger_absence"] = "passed" if ledger_absent else "failed"
        _require(ledger_absent, "confirmation_charge_ledger_unexpected")
    baseline_result, baseline_protected = _verify_confirmation_baseline(
        repo, _confirmation_source_baseline(repo),
        _sources=sources.child("asset_audit"),
    )
    from ygo_eval.curry_asset_binding_audit import _verify_historical_chain

    history, history_protected = _verify_historical_chain(
        repo,
        _sources=sources.child("asset_audit").child("historical_chain"),
    )
    expected_consumed, expected_unknown, expected_ledger_count = _historical_dataset_counts(sources)
    _require(
        history.get("consumed") == expected_consumed
        and history.get("unknown") == expected_unknown
        and history.get("ledger_count") == expected_ledger_count
        and history.get("verified_without_writable_journal") is True,
        "historical_ledger_totals_mismatch",
    )
    report["historical"] = {
        "consumed": history["consumed"],
        "unknown": history["unknown"],
        "ledger_count": history["ledger_count"],
        "verified_without_writable_journal": True,
        "input_set_sha256": history.get("input_set_sha256"),
    }
    # The ledger chain has its own completed verification boundary. Keep that
    # result when the following, independent old-material protection sweep
    # fails so the report reflects the actual checkpoint reached.
    report["checks"]["historical_ledgers"] = "passed"
    report["failure_checkpoint"] = "old_material_protection"
    protected = {**baseline_protected, **history_protected}
    report["_private_protected_expected"] = protected
    report["_private_protected_material_status"] = "pending"
    try:
        protected_records = _protected_records(repo, protected)
    except Exception as error:
        report["_private_protected_material_status"] = (
            "failed" if str(error) == "historical_protected_input_changed" else "verification_failed"
        )
        raise
    report["_private_protected_material_status"] = "passed"
    report["inputs"].extend(protected_records)
    report["checks"]["old_material_protection"] = "passed"

    # Preserve the unresolved normal attempt and do not reinterpret its exit code.
    archived_return = _archived_refusal_return_code(old_research_text)
    _require(archived_return == 2, "archived_refusal_return_code_not_found")
    report["historical_exit_observation"]["archived_refusal_branch_return_code"] = archived_return
    report["failure_checkpoint"] = "input_stability"
    protected = {**baseline_protected, **history_protected, **raw_protections}
    report["checks"]["input_stability"] = "passed"
    report["_private_protected"] = protected
    report["_private_before_tree"] = before_tree
    report["_private_baseline_result"] = baseline_result
    return report


def _resolve_banlist(repo: Path, value: str | Path) -> Path:
    from ygo_eval.native_curry_option_validation import _resolve_curry_banlist_path

    try:
        return _resolve_curry_banlist_path(repo, value)
    except (OSError, ValueError):
        raise ValueError("curry_fixed_banlist_path_invalid") from None


def _archived_refusal_return_code(source: str) -> int | None:
    marker = "if args.command == 'native-curry-option-confirmation':"
    end_marker = "if args.command == 'audit-tenki-placement-preflight':"
    if marker not in source or end_marker not in source:
        return None
    block = source[source.index(marker):source.index(end_marker)]
    if "native-curry-option-confirmation refused: frozen input, build, ledger, or output check failed" not in block:
        return None
    return 2 if "return 2" in block else None


def _protected_records(repo: Path, protected: dict[Path, str]) -> list[dict]:
    from ygo_eval.native_curry_option_validation import _confirmation_protected_hash

    records = []
    for index, (path, expected) in enumerate(sorted(protected.items(), key=lambda item: item[0].as_posix()), 1):
        absolute = _absolute(path)
        _require(absolute.is_relative_to(_absolute(repo)), "historical_input_outside_repository")
        found = _confirmation_protected_hash(absolute, repo)
        _require(found == expected, "historical_protected_input_changed")
        records.append({
            "role": f"historical_material_{index:04d}",
            "path": absolute.relative_to(_absolute(repo)).as_posix(),
            "sha256": found,
            "bytes": 0 if absolute.is_dir() else len(_read(absolute)[0]),
        })
    return records


def _safe_diagnostic(error: BaseException) -> str:
    value = str(error)
    return value if re.fullmatch(r"[a-z][a-z0-9_]{1,90}", value) else "curry_input_recovery_audit_failed"


def _write_report(output_path: Path, report: dict) -> None:
    raw = canonical(report)
    with output_path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def audit_to_output(
    args: argparse.Namespace, repo: Path | None = None,
    *, _sources: _SourceDescription | None = None,
    _clock: Any = time.monotonic,
) -> dict[str, Any]:
    repo = _absolute(repo or Path(__file__).resolve().parents[2])
    sources = _sources or _production_source_description()
    baseline = _absolute(args.baseline_dir)
    report_version = getattr(args, "report_version", 1)
    _require(type(report_version) is int and report_version in (1, 2), "audit_report_version_invalid")
    output_relative = sources.output_relative_v1 if report_version == 1 else sources.output_relative_v2
    output_root = repo / output_relative
    output_path = _absolute(args.output)
    _require(baseline == repo / sources.baseline_relative, "fixed_confirmation_baseline_required")
    _require(output_path == output_root / "audit-report.json", "fixed_recovery_output_required")
    ignored = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    _require(any(line.strip().strip("/") == "data/runtime" for line in ignored), "ignored_output_contract_missing")
    _require(not output_root.exists() and not output_root.is_symlink(), "recovery_output_root_exists")
    for parent in reversed(output_root.parents):
        if parent == repo.parent:
            break
        if parent.exists() or parent.is_symlink():
            info = parent.lstat()
            _require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, "linked_output_parent_rejected")
    output_root.mkdir(parents=True, exist_ok=False)
    return _run_audit(
        repo, baseline, output_root, output_path,
        report_version=report_version, _sources=sources, _clock=_clock,
    )


def _run_audit(
    repo: Path, baseline: Path, output_root: Path, output_path: Path, *,
    report_version: int = 1, _sources: _SourceDescription | None = None,
    _clock: Any = time.monotonic,
) -> dict[str, Any]:
    sources = _sources or _production_source_description()
    start = _clock()
    report = new_report(report_version, _sources=sources)
    source_before = None
    baseline_before = None
    source_collection_attempted = False
    baseline_collection_attempted = False
    try:
        from ygo_data.identity import stable_source

        source_collection_attempted = True
        source_before = stable_source(repo)
        report["tool_identity"] = {
            "head": source_before["head"],
            "identity": source_before["identity"],
            "file_count": len(source_before["files"]),
        }
        if report_version == 2:
            baseline_collection_attempted = True
            baseline_before = _snapshot_tree(baseline)
            report["stability"]["source_identity"] = "passed"
            report["stability"]["confirmation_tree"] = "passed"
            ledger = baseline / "research/calls.jsonl"
            ledger_absent = not ledger.exists() and not ledger.is_symlink()
            report["stability"]["ledger_absent_before"] = ledger_absent
            report["stability"]["confirmation_ledger_absence"] = "passed" if ledger_absent else "failed"
        material = _verify_confirmation_material(repo, baseline, report, _sources=sources)
        protected = material.pop("_private_protected")
        before_tree = material.pop("_private_before_tree")
        material.pop("_private_baseline_result")
        from ygo_eval.native_curry_option_validation import _confirmation_protected_hash

        report["failure_checkpoint"] = "input_stability"
        for path, expected in protected.items():
            _require(_confirmation_protected_hash(path, repo) == expected, "historical_material_changed_during_audit")
        _require(_snapshot_tree(baseline) == before_tree, "confirmation_material_changed_during_audit")
        source_after = stable_source(repo)
        _require(source_after == source_before, "audit_tool_source_changed_during_audit")
        if report_version == 2:
            report["stability"]["protected_material"] = "passed"
            report["stability"]["confirmation_tree"] = "passed"
            report["stability"]["source_identity"] = "passed"
        report["status"] = "passed"
        report["failure_checkpoint"] = None
    except Exception as error:
        report["status"] = "failed"
        report["diagnostics"].append(_safe_diagnostic(error))
        if report_version == 2:
            if source_collection_attempted and source_before is None:
                report["stability"]["source_identity"] = "verification_failed"
            if baseline_collection_attempted and baseline_before is None:
                report["stability"]["confirmation_tree"] = "verification_failed"
        checkpoint = report.get("failure_checkpoint")
        if checkpoint not in CHECK_NAMES:
            checkpoint = next((name for name, value in report["checks"].items()
                               if value == "not_run"), "input_stability")
            report["failure_checkpoint"] = checkpoint
        report["checks"][checkpoint] = "failed"
    if report_version == 2:
        _finish_v2_stability(
            repo, baseline, report, source_before, baseline_before,
            source_collection_attempted=source_collection_attempted,
            baseline_collection_attempted=baseline_collection_attempted,
        )
    report["elapsed_seconds"] = round(_clock() - start, 6)
    report.pop("_private_protected_expected", None)
    report.pop("_private_protected_material_status", None)
    validate_report(report, _sources=sources)
    _write_report(output_path, report)
    return report


def _finish_v2_stability(
    repo: Path,
    baseline: Path,
    report: dict[str, Any],
    source_before: dict[str, Any] | None,
    baseline_before: dict[str, dict[str, Any]] | None,
    *,
    source_collection_attempted: bool = True,
    baseline_collection_attempted: bool = True,
) -> None:
    """Best-effort recheck collected sources without hiding the primary failure."""
    stability = report["stability"]
    diagnostics = report["diagnostics"]

    def fail_success(checkpoint: str, diagnostic: str) -> None:
        if report["status"] == "passed":
            report["status"] = "failed"
            report["failure_checkpoint"] = checkpoint
            report["checks"][checkpoint] = "failed"
        if diagnostic not in diagnostics:
            diagnostics.append(diagnostic)

    try:
        if source_before is None:
            stability["source_identity"] = (
                "verification_failed" if source_collection_attempted else "not_collected"
            )
        else:
            from ygo_data.identity import stable_source

            source_after = stable_source(repo)
            stability["source_identity"] = "passed" if source_after == source_before else "failed"
            if source_after != source_before:
                fail_success("input_stability", "audit_tool_source_changed_during_audit")
    except Exception:
        stability["source_identity"] = "verification_failed"
        fail_success("input_stability", "audit_tool_source_stability_unverifiable")

    try:
        if baseline_before is None:
            stability["confirmation_tree"] = (
                "verification_failed" if baseline_collection_attempted else "not_collected"
            )
        else:
            current_tree = _snapshot_tree(baseline)
            stability["confirmation_tree"] = "passed" if current_tree == baseline_before else "failed"
            if current_tree != baseline_before:
                fail_success("input_stability", "confirmation_material_changed_during_audit")
    except Exception:
        stability["confirmation_tree"] = "verification_failed"
        fail_success("input_stability", "confirmation_material_stability_unverifiable")

    try:
        from ygo_eval.native_curry_option_validation import _confirmation_protected_hash

        records = [item for item in report["inputs"]
                   if isinstance(item, dict) and item.get("role", "").startswith("historical_material_")]
        collection_status = report.get("_private_protected_material_status")
        expected = report.get("_private_protected_expected")
        if collection_status in {"failed", "verification_failed", "pending"}:
            stability["protected_material"] = (
                "verification_failed" if collection_status == "pending" else collection_status
            )
            if collection_status == "failed":
                fail_success("input_stability", "historical_protected_input_changed")
            else:
                fail_success("input_stability", "historical_protection_stability_unverifiable")
        elif isinstance(expected, dict):
            for path, expected_hash in expected.items():
                absolute = _absolute(path)
                if not absolute.is_relative_to(_absolute(repo)):
                    raise ValueError("historical_input_outside_repository")
                if _confirmation_protected_hash(absolute, repo) != expected_hash:
                    raise ValueError("historical_protected_input_changed")
            stability["protected_material"] = "passed"
        elif records:
            for item in records:
                path = _safe_relative(repo, item["path"])
                if _confirmation_protected_hash(path, repo) != item["sha256"]:
                    raise ValueError("historical_protected_input_changed")
            stability["protected_material"] = "passed"
        else:
            stability["protected_material"] = "not_collected"
    except ValueError as error:
        if str(error) == "historical_protected_input_changed":
            stability["protected_material"] = "failed"
            fail_success("input_stability", "historical_protected_input_changed")
        else:
            stability["protected_material"] = "verification_failed"
            fail_success("input_stability", "historical_protection_stability_unverifiable")
    except Exception:
        stability["protected_material"] = "verification_failed"
        fail_success("input_stability", "historical_protection_stability_unverifiable")

    try:
        ledger = baseline / "research/calls.jsonl"
        ledger_absent = not ledger.exists() and not ledger.is_symlink()
        stability["ledger_absent_after"] = ledger_absent
        before = stability.get("ledger_absent_before")
        if before is None:
            stability["confirmation_ledger_absence"] = "not_collected"
        else:
            stability["confirmation_ledger_absence"] = (
                "passed" if before is True and ledger_absent else "failed"
            )
            if before is not True or not ledger_absent:
                fail_success("historical_ledgers", "confirmation_charge_ledger_unexpected")
    except Exception:
        stability["confirmation_ledger_absence"] = "verification_failed"
        fail_success("historical_ledgers", "confirmation_charge_ledger_stability_unverifiable")
