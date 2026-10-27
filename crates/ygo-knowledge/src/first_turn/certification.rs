//! Runtime qualification from reviewed cases and fresh native audits. Frozen
//! knowledge and caller supplied status fields never mint these capabilities.
use super::{verification::*, FirstTurnKnowledge, FirstTurnRule};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::Path};
use ygo_engine_adapter::*;

const REGISTRY: &str =
    include_str!("../../../../knowledge/tournament-2026.verification-registry.json");

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ReviewedCase {
    case_id: String,
    rule_id: String,
    case_sha256: String,
    kind: CaseKind,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReviewedCases {
    schema_version: u16,
    knowledge_id: String,
    cases: Vec<ReviewedCase>,
}
impl ReviewedCases {
    pub fn builtin() -> Result<Self, String> {
        serde_json::from_str(REGISTRY).map_err(|e| e.to_string())
    }
    pub fn id(&self) -> String {
        format!(
            "reviewed-cases-{}",
            crate::hash(&serde_json::to_vec(self).unwrap())
        )
    }
    pub fn validate_suite(
        &self,
        pack: &FirstTurnKnowledge,
        suite: &NativeCases,
    ) -> Result<(), String> {
        suite.validate(pack)?;
        let builtin = Self::builtin()?;
        if self.id() != builtin.id() || self.schema_version != 1 || self.knowledge_id != pack.id() {
            return Err("unreviewed native case registry".into());
        }
        for case in &suite.cases {
            let hash = crate::hash(&serde_json::to_vec(case).unwrap());
            if !self.cases.iter().any(|r| {
                r.case_id == case.id
                    && r.rule_id == case.rule_id
                    && r.kind == case.kind
                    && r.case_sha256 == hash
            }) {
                return Err(format!(
                    "case assertions/branch are not in the reviewed registry: {}",
                    case.id
                ));
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct AshLegality {
    pub target_activation: u64,
    pub target_chain: u64,
    pub response_prompt: u64,
    pub response_activation: u64,
    pub response_chain: u64,
    pub discard_cost: u64,
    pub chain_end: u64,
    pub solving: u64,
    pub negation: u64,
    pub resolution: u64,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct CaseCertificate {
    pub case_id: String,
    pub case_sha256: String,
    pub rule_id: String,
    pub kind: CaseKind,
    pub branch: String,
    pub limitations: Vec<String>,
    pub before_sha256: String,
    pub after_sha256: String,
    pub ash: Option<AshLegality>,
}

#[derive(Clone, Debug, Serialize)]
pub struct RuleCertificate {
    pub rule_id: String,
    pub text_sha256: String,
    pub script_sha256: String,
    pub positive_cases: Vec<CaseCertificate>,
    pub counterexamples: Vec<CaseCertificate>,
    pub ash_cases: Vec<CaseCertificate>,
}

/// Intentionally has no Deserialize implementation and no public certificate
/// constructor. JSON reports must be freshly audited before obtaining this view.
pub struct VerifiedKnowledge {
    knowledge: FirstTurnKnowledge,
    reviewed: ReviewedCases,
    cases: BTreeMap<String, CaseCertificate>,
    certificates: BTreeMap<String, RuleCertificate>,
    audits: Vec<NativeVerificationReport>,
}
impl VerifiedKnowledge {
    pub fn uncertified(knowledge: FirstTurnKnowledge) -> Result<Self, String> {
        knowledge.validate()?;
        Ok(Self {
            knowledge,
            reviewed: ReviewedCases::builtin()?,
            cases: BTreeMap::new(),
            certificates: BTreeMap::new(),
            audits: vec![],
        })
    }
    pub fn knowledge(&self) -> &FirstTurnKnowledge {
        &self.knowledge
    }
    pub fn certificates(&self) -> &BTreeMap<String, RuleCertificate> {
        &self.certificates
    }
    pub fn audits(&self) -> &[NativeVerificationReport] {
        &self.audits
    }
    /// Stable semantic qualification; local paths, repeated audit debits and PE
    /// build paths remain evidence, not inputs to recommendation ordering.
    pub fn id(&self) -> String {
        format!(
            "verified-knowledge-{}",
            crate::hash(
                &serde_json::to_vec(&(
                    &self.knowledge.id(),
                    self.reviewed.id(),
                    &self.certificates
                ))
                .unwrap()
            )
        )
    }
    pub fn verified_ash_effects(&self) -> Vec<&FirstTurnRule> {
        self.knowledge
            .potential_ash_effects()
            .into_iter()
            .filter(|r| {
                self.certificates
                    .get(&r.id)
                    .is_some_and(|c| !c.ash_cases.is_empty())
            })
            .collect()
    }
    pub fn require_verified_coverage(&self) -> Result<(), String> {
        let missing = self
            .knowledge
            .rules
            .iter()
            .filter(|r| r.applicable && !self.certificates.contains_key(&r.id))
            .map(|r| r.id.as_str())
            .collect::<Vec<_>>();
        if missing.is_empty() {
            Ok(())
        } else {
            Err(format!(
                "missing paired native rule evidence: {}",
                missing.join(",")
            ))
        }
    }
    pub fn audit(
        pack: &FirstTurnKnowledge,
        suite: &NativeCases,
        report: &NativeVerificationReport,
        environment: &NativeEnvironment<'_>,
        evidence_dir: &Path,
        audit_dir: &Path,
    ) -> Result<Self, String> {
        let mut view = Self::uncertified(pack.clone())?;
        view.reviewed.validate_suite(pack, suite)?;
        report.validate_contract(pack, suite)?;
        // Required qualification replay belongs to the same logical case cap.
        // Repeated diagnostics have their own declared audit ledgers.
        if report
            .cases
            .iter()
            .any(|c| c.ledger.consumed + if c.after_call.is_some() { 4 } else { 3 } > 512)
        {
            return Err("insufficient per-case budget for required qualification audit".into());
        }
        let audit = verify_report(pack, suite, report, environment, evidence_dir, audit_dir)?;
        for (case, result) in suite.cases.iter().zip(&audit.cases) {
            let (before, after) = persisted_observations(case, result, audit_dir)?;
            let certificate = CaseCertificate {
                case_id: case.id.clone(),
                case_sha256: result.case_sha256.clone(),
                rule_id: case.rule_id.clone(),
                kind: case.kind,
                branch: case.branch.clone(),
                limitations: case.limitations.clone(),
                before_sha256: observation_hash(&before),
                after_sha256: observation_hash(&after),
                ash: if case.kind == CaseKind::AshResponse {
                    ash_legality(pack.rule(&case.rule_id).unwrap(), &after)?
                } else {
                    None
                },
            };
            view.cases.insert(case.id.clone(), certificate);
        }
        view.audits.push(audit);
        view.rebuild();
        Ok(view)
    }
    pub fn merge(&mut self, other: Self) -> Result<(), String> {
        if self.knowledge.id() != other.knowledge.id() || self.reviewed.id() != other.reviewed.id()
        {
            return Err("native qualification sources differ".into());
        }
        for (id, new) in &other.cases {
            if self.cases.get(id).is_some_and(|old| old != new) {
                return Err("same reviewed case has different actual observations".into());
            }
        }
        self.cases.extend(other.cases);
        self.audits.extend(other.audits);
        self.rebuild();
        Ok(())
    }
    fn rebuild(&mut self) {
        self.certificates.clear();
        for rule in self.knowledge.rules.iter().filter(|r| r.applicable) {
            let cases = self
                .cases
                .values()
                .filter(|c| c.rule_id == rule.id)
                .collect::<Vec<_>>();
            let positive_cases = cases
                .iter()
                .filter(|c| c.kind.positive())
                .map(|c| (*c).clone())
                .collect::<Vec<_>>();
            let counterexamples = cases
                .iter()
                .filter(|c| c.kind.negative())
                .map(|c| (*c).clone())
                .collect::<Vec<_>>();
            if positive_cases.is_empty() || counterexamples.is_empty() {
                continue;
            }
            let card = self
                .knowledge
                .cards
                .iter()
                .find(|c| c.card_id == rule.card_id)
                .unwrap();
            self.certificates.insert(
                rule.id.clone(),
                RuleCertificate {
                    rule_id: rule.id.clone(),
                    text_sha256: card.text_sha256.clone(),
                    script_sha256: card.script_sha256.clone(),
                    positive_cases,
                    counterexamples,
                    ash_cases: cases
                        .into_iter()
                        .filter(|c| c.ash.is_some())
                        .cloned()
                        .collect(),
                },
            );
        }
    }
}

fn observation_hash(result: &DuelResult) -> String {
    let mut normalized = result.clone();
    normalized.peak_working_set_bytes = None;
    crate::hash(&serde_json::to_vec(&normalized).unwrap())
}

pub(super) fn ash_legality(
    rule: &FirstTurnRule,
    result: &DuelResult,
) -> Result<Option<AshLegality>, String> {
    if !rule.deck_interaction.is_ash_candidate() {
        return Ok(None);
    }
    let events = result
        .events
        .iter()
        .map(|e| {
            if !ygo_engine_adapter::frame_matches_raw(e)? {
                return Err("raw native response evidence differs".into());
            }
            Ok(e.clone())
        })
        .collect::<Result<Vec<_>, String>>()?;
    let Some(target) = events.iter().find(|e| {
        e.opcode == 70
            && e.fields["player"] == 0
            && e.fields["code"] == rule.card_id
            && e.fields["description"].as_u64() == rule.description
            && e.fields["trigger_location"]
                .as_u64()
                .is_some_and(|z| z as u8 & rule.source_locations != 0)
    }) else {
        return Ok(None);
    };
    let ashes = events
        .iter()
        .filter(|e| e.opcode == 70 && e.fields["player"] == 1 && e.fields["code"] == 14558127)
        .collect::<Vec<_>>();
    if ashes.is_empty() {
        return Ok(None);
    }
    if ashes.len() != 1 {
        return Err("native certificate has multiple opponent Ash activations".into());
    }
    let ash = ashes[0];
    let chain = target.fields["chain"]
        .as_u64()
        .ok_or("missing target chain")?;
    if ash.fields["description"].as_u64() != Some(14558127u64 << 20)
        || ash.fields["trigger_location"] != 2
    {
        return Err("response is not the frozen Ash hand effect".into());
    }
    if ash.sequence <= target.sequence
        || ash.fields["chain"].as_u64() != Some(chain + 1)
        || events
            .iter()
            .filter(|e| e.sequence > target.sequence && e.sequence < ash.sequence && e.opcode == 70)
            .count()
            != 0
    {
        return Ok(None);
    }
    let Some(decision) = result
        .resolved_decisions
        .iter()
        .filter(|d| d.player == 1 && d.prompt_id > target.sequence && d.prompt_id < ash.sequence)
        .find(|d| {
            events
                .iter()
                .find(|e| e.sequence == d.prompt_id)
                .and_then(|e| prompt_metadata(e.sequence, &e.raw).ok())
                .is_some_and(|ms| {
                    ms.into_iter().any(|m| {
                        m.choice == d.choice
                            && m.source.is_some_and(|s| {
                                s.code == 14558127 && s.player == 1 && s.location == 2
                            })
                    })
                })
        })
    else {
        return Err("Ash lacks its actual legal response prompt".into());
    };
    let Some(cost) = events.iter().find(|e| {
        e.sequence > ash.sequence
            && e.opcode == 50
            && e.fields["code"] == 14558127
            && e.fields["from"]["player"] == 1
            && e.fields["from"]["location"] == 2
            && e.fields["to"]["location"] == 16
            && e.fields["reason"].as_u64().is_some_and(|r| r & 128 != 0)
    }) else {
        return Err("Ash lacks its actual discard cost".into());
    };
    let end = events
        .iter()
        .find(|e| e.sequence > cost.sequence && e.opcode == 74)
        .ok_or("Ash response chain not finished")?;
    if cost.fields["from"] != ash.fields["location"]
        || events.iter().any(|e| {
            e.sequence > ash.sequence
                && e.sequence < cost.sequence
                && e.opcode == 50
                && (e.fields["from"]["player"] == 1 && e.fields["from"]["location"] == 2
                    || e.fields["to"]["player"] == 1 && e.fields["to"]["location"] == 2)
        })
    {
        return Err("Ash discard does not bind its pre-cost source coordinate".into());
    }
    if !events.iter().any(|e| {
        e.opcode == 71
            && e.sequence > cost.sequence
            && e.sequence < end.sequence
            && e.fields["chain"].as_u64() == Some(chain + 1)
    }) {
        return Err("Ash cost lacks its completed chain registration".into());
    }
    let solving = events
        .iter()
        .find(|e| {
            e.sequence > cost.sequence
                && e.sequence < end.sequence
                && e.opcode == 72
                && e.fields["chain"].as_u64() == Some(chain + 1)
        })
        .ok_or("Ash never started resolving")?;
    let negation = events
        .iter()
        .find(|e| {
            e.sequence > solving.sequence
                && e.sequence < end.sequence
                && e.opcode == 76
                && e.fields["chain"].as_u64() == Some(chain)
        })
        .ok_or("target lacks actual Ash effect negation")?;
    let resolution = events
        .iter()
        .find(|e| {
            e.sequence > negation.sequence
                && e.sequence < end.sequence
                && e.opcode == 73
                && e.fields["chain"].as_u64() == Some(chain + 1)
        })
        .ok_or("Ash never completed resolving")?;
    Ok(Some(AshLegality {
        target_activation: target.sequence,
        target_chain: chain,
        response_prompt: decision.prompt_id,
        response_activation: ash.sequence,
        response_chain: chain + 1,
        discard_cost: cost.sequence,
        chain_end: end.sequence,
        solving: solving.sequence,
        negation: negation.sequence,
        resolution: resolution.sequence,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn ash_record() -> DuelResult {
        let mut value: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../tests/fixtures/tournament-2026.trace-ash.json"
        ))
        .unwrap();
        value["result"]["events"] = serde_json::json!([]);
        let mut result: DuelResult = serde_json::from_value(value["result"].clone()).unwrap();
        result.events = value["frames"]
            .as_array()
            .unwrap()
            .iter()
            .enumerate()
            .map(|(i, raw)| {
                decode_frame(
                    i as u64 + 1,
                    &serde_json::from_value::<Vec<u8>>(raw.clone()).unwrap(),
                )
                .unwrap()
            })
            .collect();
        result
    }
    #[test]
    fn ash_qualification_requires_the_legal_response_cost_and_exact_target_chain() {
        let pack = FirstTurnKnowledge::builtin().unwrap();
        let rule = pack.rule("78449284:deck_special").unwrap();
        let mut result = ash_record();
        let witness = ash_legality(rule, &result).unwrap().unwrap();
        assert_eq!(witness.target_activation, 67);
        assert_eq!(witness.response_activation, 73);
        assert_eq!(witness.discard_cost, 74);
        assert_eq!(witness.chain_end, 83);
        for d in result
            .resolved_decisions
            .iter_mut()
            .filter(|d| d.player == 1)
        {
            d.choice = Choice::Chain { index: None };
        }
        assert!(ash_legality(rule, &result).is_err());
    }
    #[test]
    fn cost_milling_does_not_gain_ash_qualification_from_an_unrelated_response() {
        let pack = FirstTurnKnowledge::builtin().unwrap();
        let rule = pack
            .rules
            .iter()
            .find(|r| r.operation == super::super::Operation::CostMillBoost)
            .unwrap();
        assert!(ash_legality(rule, &ash_record()).unwrap().is_none());
    }
    #[test]
    fn an_ash_branch_requires_actual_negation_and_its_own_discard_coordinates() {
        let pack = FirstTurnKnowledge::builtin().unwrap();
        let rule = pack.rule("78449284:deck_special").unwrap();
        let mut r = ash_record();
        r.events.retain(|e| e.opcode != 76);
        assert!(
            ash_legality(rule, &r).is_err(),
            "cost plus chain end does not prove negation"
        );
        let mut r = ash_record();
        let e = r
            .events
            .iter_mut()
            .find(|e| e.opcode == 50 && e.fields["code"] == 14558127)
            .unwrap();
        let mut raw = e.raw.clone();
        raw[7..11].copy_from_slice(&1u32.to_le_bytes());
        *e = decode_frame(e.sequence, &raw).unwrap();
        assert!(
            ash_legality(rule, &r).is_err(),
            "another hand coordinate is not this handler's fee"
        );
    }
}
