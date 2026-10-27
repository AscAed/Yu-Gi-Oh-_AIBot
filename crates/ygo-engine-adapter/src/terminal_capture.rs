use crate::*;
use serde_json::{json, Value};

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResearchCaptureV1 {
    pub schema_version: u32,
    pub objective: String,
    pub boundary: String,
}
pub fn validate_research_capture(request: &RunDuelRequest) -> Result<(), String> {
    if let Some(policy) = &request.research_capture {
        if policy.schema_version != 1
            || policy.objective != "rabbit-own-face-up-xyz-v1"
            || policy.boundary != "first-next-turn-process-return-v1"
            || request.protocol_version != 2
            || request.probe_only
            || request.opening_hand.len() != 5
            || request.scenario.is_some()
            || request.interruption.is_some()
            || request.first_turn.is_some()
        {
            return Err("unsupported research capture request".into());
        }
    }
    Ok(())
}
pub(crate) fn hash_value(value: &impl serde::Serialize) -> String {
    let value = serde_json::to_value(value).expect("serializable capture data");
    format!(
        "{:x}",
        sha2::Sha256::digest(serde_json::to_vec(&value).unwrap())
    )
}
pub(crate) fn hash_bytes(value: &[u8]) -> String {
    format!("{:x}", sha2::Sha256::digest(value))
}
#[derive(Default)]
pub(crate) struct Capture {
    pub batches: Vec<Value>,
    first_turn: bool,
    end_phase: bool,
    natural_end: bool,
    boundary: Option<u64>,
    boundary_player: Option<u8>,
    boundary_batch: Option<usize>,
    invalid: bool,
}
impl Capture {
    pub fn batch(&mut self, raw: &[u8], status: i32, start: u64, frames: &[&[u8]]) {
        if self.boundary.is_some() {
            self.invalid = true;
        }
        let mut boundary_in_batch = None;
        for (index, frame) in frames.iter().enumerate() {
            match frame.first().copied() {
                Some(40) if frame.len() == 2 => {
                    if !self.first_turn {
                        self.first_turn = frame[1] == 0;
                        if !self.first_turn {
                            self.invalid = true;
                        }
                    } else {
                        if self.boundary.is_some() || !self.end_phase || frame[1] > 1 {
                            self.invalid = true;
                        }
                        self.boundary = Some(start + index as u64);
                        self.boundary_player = Some(frame[1]);
                        self.boundary_batch = Some(self.batches.len());
                        boundary_in_batch = Some(index);
                    }
                }
                Some(41) if frame.len() == 3 => {
                    self.end_phase = u16::from_le_bytes([frame[1], frame[2]]) == 512
                        && self.first_turn
                        && self.boundary.is_none();
                }
                Some(5) => self.natural_end = true,
                _ => (),
            }
        }
        if boundary_in_batch.is_some_and(|i| i + 1 != frames.len() || status != 2) {
            self.invalid = true;
        }
        self.batches.push(json!({"index": self.batches.len(), "status":status,"raw":raw,"sha256":hash_bytes(raw),"start_sequence":start,"end_sequence":(start + frames.len() as u64).saturating_sub(1)}));
    }
    pub fn valid_boundary(&self, prompt: bool) -> bool {
        self.boundary.is_some() && !self.invalid && !self.natural_end && !prompt
    }
    pub fn observation(&self, request: &RunDuelRequest, events: &[CoreEventFrame]) -> Value {
        json!({"schema_version":1,"request_sha256":hash_value(request),"batches":self.batches,"boundary_sequence":self.boundary,"boundary_batch_index":self.boundary_batch,"event_prefix_sha256":hash_value(&events),"phase":null,"turn_index":if self.boundary.is_some(){Some(2)}else if self.first_turn{Some(1)}else{None},"turn_player":self.boundary_player,"turn_source":"raw_new_turn_events","queries":[],"snapshot":[],"capture_query_count":0,"legacy_query_count":null,"status":"failed","diagnostics":[]})
    }
}
/// Preserve every attempted FFI query, including a failing final slot.
pub(crate) fn capture_queries(
    mut query: impl FnMut(u8, u32) -> Result<Vec<u8>, String>,
) -> (Vec<Value>, Vec<Value>, Option<String>) {
    let mut queries = vec![];
    let mut cards = vec![];
    for controller in 0..2u8 {
        for sequence in 0..7 {
            let (raw, error) = match query(controller, sequence) {
                Ok(raw) => {
                    let error = match goal_card(&raw, controller, sequence) {
                        Ok(Some(card)) => {
                            cards.push(card);
                            None
                        }
                        Ok(None) => None,
                        Err(error) => Some(error),
                    };
                    (raw, error)
                }
                Err(error) => (vec![], Some(error)),
            };
            queries.push(json!({"controller":controller,"location":4,"sequence":sequence,"flags":11,"raw":raw,"sha256":hash_bytes(&raw),"error":error}));
            if error.is_some() {
                return (queries, cards, error);
            }
        }
    }
    (queries, cards, None)
}
/// Decode only the three fields requested by the production capture path.
pub(crate) fn goal_card(raw: &[u8], player: u8, sequence: u32) -> Result<Option<Value>, String> {
    if raw.is_empty() {
        return Ok(None);
    }
    let mut r = crate::codec::Reader::new(raw);
    let (mut code, mut position, mut kind) = (None, None, None);
    let mut ended = false;
    let mut public_seen = false;
    while r.pos < raw.len() {
        let size = r.u16()? as usize;
        let mut item = crate::codec::Reader::new(r.take(size)?);
        let flag = item.u32()?;
        match flag {
            1 if code.is_none() => code = Some(item.u32()?),
            2 if position.is_none() => position = Some(item.u32()?),
            8 if kind.is_none() => kind = Some(item.u32()?),
            0x100000 if !public_seen => {
                if item.u8()? > 1 {
                    return Err("invalid capture public marker".into());
                }
                public_seen = true;
            }
            0x80000000 => ended = true,
            _ => return Err("unexpected or repeated capture query field".into()),
        }
        item.end()?;
        if ended {
            r.end()?;
            break;
        }
    }
    match (code, position, kind, ended) {
        (Some(code), Some(position), Some(kind), true) if code != 0 => Ok(Some(
            json!({"code":code,"player":player,"location":4,"sequence":sequence,"position":position,"type_flags":kind}),
        )),
        _ => Err("incomplete capture query".into()),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn frame(raw: &[u8]) -> Vec<u8> {
        [&(raw.len() as u32).to_le_bytes()[..], raw].concat()
    }
    #[test]
    fn goal_query_accepts_core_public_marker_and_rejects_malformed_marker() {
        // Handwritten TLV fields: CODE42, POSITION1, TYPE_XYZ, IS_PUBLIC1, END.
        let raw = vec![
            8, 0, 1, 0, 0, 0, 42, 0, 0, 0, 8, 0, 2, 0, 0, 0, 1, 0, 0, 0, 8, 0, 8, 0, 0, 0, 1, 0,
            128, 0, 5, 0, 0, 0, 16, 0, 1, 4, 0, 0, 0, 0, 128,
        ];
        assert_eq!(goal_card(&raw, 0, 0).unwrap().unwrap()["code"], 42);
        let mut not_public = raw.clone();
        not_public[36] = 0;
        assert_eq!(
            goal_card(&not_public, 0, 0).unwrap(),
            goal_card(&raw, 0, 0).unwrap()
        );
        let mut absent = raw[..30].to_vec();
        absent.extend_from_slice(&raw[37..]);
        assert_eq!(
            goal_card(&absent, 0, 0).unwrap(),
            goal_card(&raw, 0, 0).unwrap()
        );
        let mut invalid_bool = raw.clone();
        invalid_bool[36] = 2;
        assert!(goal_card(&invalid_bool, 0, 0).is_err());
        let mut duplicate = raw[..37].to_vec();
        duplicate.extend_from_slice(&raw[30..]);
        assert!(goal_card(&duplicate, 0, 0).is_err());
        let mut wrong_length = raw.clone();
        wrong_length[30] = 6;
        assert!(goal_card(&wrong_length, 0, 0).is_err());
    }
    #[test]
    fn known_core_query_encoding_requires_an_intact_end_marker() {
        // Exact 43-byte query encoding; this is not a complete native snapshot.
        let raw = [
            8, 0, 1, 0, 0, 0, 181, 240, 1, 5, 8, 0, 2, 0, 0, 0, 1, 0, 0, 0, 8, 0, 8, 0, 0, 0, 33,
            0, 128, 0, 5, 0, 0, 0, 16, 0, 1, 4, 0, 0, 0, 0, 128,
        ];
        assert_eq!(
            goal_card(&raw, 0, 0).unwrap(),
            Some(json!({"code":84013237,"player":0,"location":4,"sequence":0,
                        "position":1,"type_flags":8388641}))
        );
        assert!(goal_card(&raw[..37], 0, 0).is_err());
        assert!(goal_card(&raw[..42], 0, 0).is_err());
        let mut trailing = raw.to_vec();
        trailing.push(0);
        assert!(goal_card(&trailing, 0, 0).is_err());
    }
    #[test]
    fn failed_query_preserves_partial_transcript() {
        let (queries, cards, error) = capture_queries(|_, sequence| {
            if sequence == 2 {
                Err("failure".into())
            } else {
                Ok(vec![])
            }
        });
        assert_eq!(queries.len(), 3);
        assert!(cards.is_empty());
        assert_eq!(error.as_deref(), Some("failure"));
        assert_eq!(queries[2]["error"], "failure");
        let (queries, _, error) = capture_queries(|_, _| Ok(vec![]));
        assert_eq!(queries.len(), 14);
        assert!(error.is_none());
    }
    #[test]
    fn phase_after_end_cancels_boundary_readiness() {
        let mut capture = Capture::default();
        capture.batch(&[], 2, 1, &[&[40, 0], &[41, 0, 2], &[41, 4, 0], &[40, 1]]);
        assert!(!capture.valid_boundary(false));
    }
    #[test]
    fn boundary_requires_end_history_and_batch_tail() {
        let mut c = Capture::default();
        c.batch(&frame(&[40, 0]), 1, 1, &[&[40, 0]]);
        c.batch(&frame(&[41, 0, 2]), 1, 2, &[&[41, 0, 2]]);
        c.batch(&frame(&[40, 1]), 2, 3, &[&[40, 1]]);
        assert!(c.valid_boundary(false));
        assert!(!c.valid_boundary(true));
        c.batch(&frame(&[40, 1]), 1, 4, &[&[40, 1]]);
        assert!(!c.valid_boundary(false));
        let mut missing = Capture::default();
        missing.batch(&[], 1, 1, &[&[40, 0], &[40, 1]]);
        assert!(!missing.valid_boundary(false));
        let mut tail = Capture::default();
        tail.batch(&[], 1, 1, &[&[40, 0], &[41, 0, 2], &[40, 1], &[41, 1, 0]]);
        assert!(!tail.valid_boundary(false));
    }
}
