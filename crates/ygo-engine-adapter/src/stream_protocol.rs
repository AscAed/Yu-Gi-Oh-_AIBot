use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    io::BufReader,
    io::{BufRead, Write},
    sync::{Arc, Mutex},
};

pub const STREAM_VERSION: u16 = 1;
pub const MAX_FRAME_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_EVENT_FRAME_BYTES: usize = 64 * 1024;
const CALL_ID_DOMAIN: &[u8] = b"ygo-worker-ffi-call-id-v1\0";
pub type WorkerSession = SharedWorkerStream<BufReader<std::io::Stdin>, std::io::Stdout>;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StreamRequest {
    pub version: u16,
    pub attempt_id: String,
    pub request: crate::RunDuelRequest,
}

impl StreamRequest {
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.version != STREAM_VERSION
            || self.attempt_id.is_empty()
            || self.attempt_id.len() > 4096
        {
            return Err("invalid stream request");
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StreamResult {
    pub version: u16,
    pub attempt_id: String,
    pub result: crate::DuelResult,
}

impl StreamResult {
    pub fn validate(&self, expected_attempt_id: &str) -> Result<(), &'static str> {
        if self.version != STREAM_VERSION || self.attempt_id != expected_attempt_id {
            return Err("invalid stream result");
        }
        Ok(())
    }
}

pub struct WorkerStream<R, W> {
    attempt_id: String,
    sequence: u64,
    stack: Vec<String>,
    poisoned: bool,
    input: R,
    output: W,
}

pub type SharedWorkerStream<R, W> = Arc<Mutex<WorkerStream<R, W>>>;

pub fn shared_worker_stream<R, W>(
    attempt_id: String,
    input: R,
    output: W,
) -> Result<SharedWorkerStream<R, W>, &'static str>
where
    R: BufRead,
    W: Write,
{
    Ok(Arc::new(Mutex::new(WorkerStream::new(
        attempt_id, input, output,
    )?)))
}

pub fn ffi_call_shared<R: BufRead, W: Write, T>(
    stream: Option<&SharedWorkerStream<R, W>>,
    direction: FfiDirection,
    name: &str,
    call: impl FnOnce() -> T,
) -> Result<T, &'static str> {
    let Some(stream) = stream else {
        return Ok(call());
    };
    let token = stream
        .lock()
        .map_err(|_| "worker stream poisoned")?
        .enter(direction, name)?;
    let value = call();
    stream
        .lock()
        .map_err(|_| "worker stream poisoned")?
        .returned(token)?;
    Ok(value)
}

impl<R: BufRead, W: Write> WorkerStream<R, W> {
    pub fn new(attempt_id: String, input: R, output: W) -> Result<Self, &'static str> {
        if attempt_id.is_empty() {
            return Err("empty attempt id");
        }
        Ok(Self {
            attempt_id,
            sequence: 0,
            stack: Vec::new(),
            poisoned: false,
            input,
            output,
        })
    }

    pub fn ffi<T>(
        &mut self,
        direction: FfiDirection,
        name: &str,
        call: impl FnOnce() -> T,
    ) -> Result<T, &'static str> {
        if self.poisoned {
            return Err("worker stream is poisoned");
        }
        if name.is_empty() || name.len() > 4096 || self.attempt_id.len() > 4096 {
            return Err("empty FFI name");
        }
        self.sequence = self.sequence.checked_add(1).ok_or("sequence overflow")?;
        let sequence = self.sequence;
        let call_id = call_id(&self.attempt_id, sequence);
        self.event(
            sequence,
            &call_id,
            direction,
            name,
            WorkerFrameKind::FfiEntered,
        )?;
        self.stack.push(call_id.clone());
        let value = call();
        self.event(
            sequence,
            &call_id,
            direction,
            name,
            WorkerFrameKind::FfiReturned,
        )?;
        if self.stack.pop().as_deref() != Some(&call_id) {
            return Err("FFI return stack mismatch");
        }
        Ok(value)
    }

    pub fn enter(
        &mut self,
        direction: FfiDirection,
        name: &str,
    ) -> Result<CallToken, &'static str> {
        if self.poisoned {
            return Err("worker stream is poisoned");
        }
        if name.is_empty() || name.len() > 4096 || self.attempt_id.len() > 4096 {
            return Err("empty FFI name");
        }
        self.sequence = self.sequence.checked_add(1).ok_or("sequence overflow")?;
        let token = CallToken {
            sequence: self.sequence,
            call_id: call_id(&self.attempt_id, self.sequence),
            direction,
            name: name.to_owned(),
        };
        self.event(
            token.sequence,
            &token.call_id,
            token.direction,
            &token.name,
            WorkerFrameKind::FfiEntered,
        )?;
        self.stack.push(token.call_id.clone());
        Ok(token)
    }

    pub fn returned(&mut self, token: CallToken) -> Result<(), &'static str> {
        if self.poisoned {
            return Err("worker stream is poisoned");
        }
        if self.stack.last().map(String::as_str) != Some(token.call_id.as_str()) {
            return Err("FFI return stack mismatch");
        }
        self.event(
            token.sequence,
            &token.call_id,
            token.direction,
            &token.name,
            WorkerFrameKind::FfiReturned,
        )?;
        self.stack.pop();
        Ok(())
    }

    fn event(
        &mut self,
        sequence: u64,
        call_id: &str,
        direction: FfiDirection,
        name: &str,
        kind: WorkerFrameKind,
    ) -> Result<(), &'static str> {
        let frame = WorkerFrame {
            version: STREAM_VERSION,
            attempt_id: self.attempt_id.clone(),
            sequence,
            call_id: call_id.to_owned(),
            direction,
            name: name.to_owned(),
            kind,
        };
        let result = (|| {
            let bytes = serde_json::to_vec(&frame).map_err(|_| "frame serialization failed")?;
            if bytes.len() > MAX_EVENT_FRAME_BYTES {
                return Err("event frame size limit");
            }
            self.output
                .write_all(&bytes)
                .and_then(|_| self.output.write_all(b"\n"))
                .and_then(|_| self.output.flush())
                .map_err(|_| "frame write failed")?;
            let ack: HostAck = read_frame(&mut self.input)?;
            if !ack.matches(&self.attempt_id, sequence, call_id) {
                return Err("host acknowledgement mismatch");
            }
            Ok(())
        })();
        if result.is_err() {
            self.poisoned = true;
        }
        result
    }

    pub fn into_parts(self) -> (R, W) {
        (self.input, self.output)
    }

    pub fn send_result<T: Serialize>(&mut self, result: &T) -> Result<(), &'static str> {
        write_frame(&mut self.output, result)
    }
}

#[derive(Clone, Debug)]
pub struct CallToken {
    sequence: u64,
    call_id: String,
    direction: FfiDirection,
    name: String,
}

pub fn call_id(attempt_id: &str, sequence: u64) -> String {
    let mut hash = Sha256::new();
    hash.update(CALL_ID_DOMAIN);
    hash.update((attempt_id.len() as u64).to_be_bytes());
    hash.update(attempt_id.as_bytes());
    hash.update(sequence.to_be_bytes());
    hash.finalize()[..16]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

pub fn write_frame<W: Write, T: Serialize>(output: &mut W, frame: &T) -> Result<(), &'static str> {
    let bytes = serde_json::to_vec(frame).map_err(|_| "frame serialization failed")?;
    if bytes.is_empty() || bytes.len() > MAX_FRAME_BYTES {
        return Err("frame size limit");
    }
    output.write_all(&bytes).map_err(|_| "frame write failed")?;
    output.write_all(b"\n").map_err(|_| "frame write failed")?;
    output.flush().map_err(|_| "frame flush failed")
}

pub fn read_frame<R: BufRead, T: for<'de> Deserialize<'de>>(input: R) -> Result<T, &'static str> {
    let mut bytes = Vec::new();
    let read = input
        .take((MAX_FRAME_BYTES + 1) as u64)
        .read_until(b'\n', &mut bytes)
        .map_err(|_| "frame read failed")?;
    if read == 0 || bytes.len() > MAX_FRAME_BYTES + 1 || bytes.last() != Some(&b'\n') {
        return Err("frame size or termination invalid");
    }
    bytes.pop();
    serde_json::from_slice(&bytes).map_err(|_| "frame validation failed")
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "WorkerFrameRepr", into = "WorkerFrameRepr")]
pub struct WorkerFrame {
    pub version: u16,
    pub attempt_id: String,
    pub sequence: u64,
    pub call_id: String,
    pub direction: FfiDirection,
    pub name: String,
    pub kind: WorkerFrameKind,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkerFrameRepr {
    version: u16,
    attempt_id: String,
    sequence: u64,
    call_id: String,
    direction: FfiDirection,
    name: String,
    kind: WorkerFrameKind,
}

impl TryFrom<WorkerFrameRepr> for WorkerFrame {
    type Error = &'static str;

    fn try_from(frame: WorkerFrameRepr) -> Result<Self, Self::Error> {
        if frame.version != STREAM_VERSION
            || frame.attempt_id.is_empty()
            || frame.sequence == 0
            || frame.call_id.is_empty()
            || frame.call_id.len() > 4096
            || frame.name.is_empty()
            || frame.name.len() > 4096
        {
            return Err("invalid worker frame");
        }
        Ok(Self {
            version: frame.version,
            attempt_id: frame.attempt_id,
            sequence: frame.sequence,
            call_id: frame.call_id,
            direction: frame.direction,
            name: frame.name,
            kind: frame.kind,
        })
    }
}

impl From<WorkerFrame> for WorkerFrameRepr {
    fn from(frame: WorkerFrame) -> Self {
        Self {
            version: frame.version,
            attempt_id: frame.attempt_id,
            sequence: frame.sequence,
            call_id: frame.call_id,
            direction: frame.direction,
            name: frame.name,
            kind: frame.kind,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FfiDirection {
    IntoCore,
    OutOfCore,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkerFrameKind {
    FfiEntered,
    FfiReturned,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HostAck {
    pub version: u16,
    pub attempt_id: String,
    pub sequence: u64,
    pub call_id: String,
    pub accepted: bool,
}

impl HostAck {
    pub fn matches(&self, attempt_id: &str, sequence: u64, call_id: &str) -> bool {
        self.version == STREAM_VERSION
            && self.accepted
            && self.attempt_id.len() <= 4096
            && self.call_id.len() <= 4096
            && self.attempt_id == attempt_id
            && self.sequence == sequence
            && self.call_id == call_id
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::io::Cursor;

    #[test]
    fn event_frames_reject_unknown_fields_and_wrong_version() {
        let valid = json!({
            "version": 1,
            "attempt_id": "attempt-1",
            "sequence": 1,
            "call_id": "call-1",
            "direction": "into_core",
            "name": "OCG_DuelProcess",
            "kind": "ffi_entered"
        });
        assert!(serde_json::from_value::<WorkerFrame>(valid.clone()).is_ok());

        let mut extra = valid.clone();
        extra["unexpected"] = json!(true);
        assert!(serde_json::from_value::<WorkerFrame>(extra).is_err());

        let mut wrong_version = valid;
        wrong_version["version"] = json!(2);
        assert!(serde_json::from_value::<WorkerFrame>(wrong_version).is_err());
    }

    #[test]
    fn acknowledgements_bind_to_the_exact_event_sequence_and_call() {
        let ack = HostAck {
            version: 1,
            attempt_id: "attempt-1".into(),
            sequence: 1,
            call_id: "call-1".into(),
            accepted: true,
        };
        assert!(ack.matches("attempt-1", 1, "call-1"));
        assert!(!ack.matches("attempt-1", 2, "call-1"));
        assert!(!ack.matches("attempt-1", 1, "other-call"));
        assert!(!ack.matches("other-attempt", 1, "call-1"));
    }

    #[test]
    fn call_ids_are_stable_domain_separated_128_bit_digests() {
        let id = call_id("attempt-1", 1);
        assert_eq!(id.len(), 32);
        assert!(id
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)));
        assert_eq!(id, call_id("attempt-1", 1));
        assert_ne!(id, call_id("attempt-1", 2));
        assert_ne!(id, call_id("attempt-2", 1));
    }

    #[test]
    fn worker_waits_for_both_persistable_event_acknowledgements() {
        let ack = |sequence| HostAck {
            version: 1,
            attempt_id: "attempt-1".into(),
            sequence,
            call_id: call_id("attempt-1", sequence),
            accepted: true,
        };
        let mut input = Cursor::new(
            format!(
                "{}\n{}\n",
                serde_json::to_string(&ack(1)).unwrap(),
                serde_json::to_string(&ack(1)).unwrap()
            )
            .into_bytes(),
        );
        let output = Vec::new();
        let mut stream = WorkerStream::new("attempt-1".into(), &mut input, output).unwrap();
        let value = stream
            .ffi(FfiDirection::IntoCore, "OCG_DuelProcess", || 7)
            .unwrap();
        assert_eq!(value, 7);
        let (_, output) = stream.into_parts();
        let frames = output
            .split(|byte| *byte == b'\n')
            .filter(|line| !line.is_empty())
            .map(|line| serde_json::from_slice::<WorkerFrame>(line).unwrap())
            .collect::<Vec<_>>();
        assert_eq!(frames.len(), 2);
        assert_eq!(frames[0].kind, WorkerFrameKind::FfiEntered);
        assert_eq!(frames[1].kind, WorkerFrameKind::FfiReturned);
        assert_eq!(frames[0].call_id, frames[1].call_id);
    }

    #[test]
    fn shared_session_preserves_nested_callback_event_order() {
        let ack = |sequence| HostAck {
            version: STREAM_VERSION,
            attempt_id: "attempt-1".into(),
            sequence,
            call_id: call_id("attempt-1", sequence),
            accepted: true,
        };
        let input = Cursor::new(
            (1..=2)
                .chain([2, 1])
                .map(|sequence| serde_json::to_string(&ack(sequence)).unwrap() + "\n")
                .collect::<String>()
                .into_bytes(),
        );
        let session = shared_worker_stream("attempt-1".into(), input, Vec::new()).unwrap();
        let outer = ffi_call_shared(
            Some(&session),
            FfiDirection::IntoCore,
            "OCG_DuelProcess",
            || {
                ffi_call_shared(
                    Some(&session),
                    FfiDirection::OutOfCore,
                    "card_reader",
                    || 17,
                )
            },
        )
        .unwrap()
        .unwrap();
        assert_eq!(outer, 17);
        let output = session.lock().unwrap().output.clone();
        let frames = output
            .split(|byte| *byte == b'\n')
            .filter(|line| !line.is_empty())
            .map(|line| serde_json::from_slice::<WorkerFrame>(line).unwrap())
            .collect::<Vec<_>>();
        assert_eq!(
            frames.iter().map(|frame| frame.kind).collect::<Vec<_>>(),
            [
                WorkerFrameKind::FfiEntered,
                WorkerFrameKind::FfiEntered,
                WorkerFrameKind::FfiReturned,
                WorkerFrameKind::FfiReturned,
            ]
        );
        assert_eq!(
            frames
                .iter()
                .map(|frame| frame.sequence)
                .collect::<Vec<_>>(),
            [1, 2, 2, 1]
        );
    }

    #[test]
    fn invalid_ack_prevents_the_ffi_call() {
        let ack = HostAck {
            version: 1,
            attempt_id: "attempt-1".into(),
            sequence: 9,
            call_id: "wrong".into(),
            accepted: true,
        };
        let mut input = Cursor::new(format!("{}\n", serde_json::to_string(&ack).unwrap()));
        let mut called = false;
        let mut stream = WorkerStream::new("attempt-1".into(), &mut input, Vec::new()).unwrap();
        let result = stream.ffi(FfiDirection::IntoCore, "OCG_DuelProcess", || called = true);
        assert!(result.is_err());
        assert!(!called);
    }

    #[test]
    fn frame_reader_rejects_oversized_unterminated_and_invalid_json_frames() {
        let oversized = vec![b'a'; MAX_FRAME_BYTES + 1];
        assert!(read_frame::<_, HostAck>(Cursor::new(oversized)).is_err());
        assert!(read_frame::<_, HostAck>(Cursor::new(b"{}".to_vec())).is_err());
        assert!(read_frame::<_, HostAck>(Cursor::new(b"{bad}\n".to_vec())).is_err());
    }
}
