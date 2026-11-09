//! Fault-injection helper for subprocess tests; never used for duel verification.
fn main() {
    let name = std::env::current_exe()
        .unwrap()
        .file_stem()
        .unwrap()
        .to_string_lossy()
        .into_owned();
    if std::env::var("YGO_WORKER_PROTOCOL").as_deref() == Ok("ffi-receipt-stream-v1") {
        stream_fixture(&name);
    } else if name.contains("hang") {
        std::thread::sleep(std::time::Duration::from_secs(60));
    } else if name.ends_with("-valid") {
        let mut result = ygo_engine_adapter::DuelResult::failure(
            ygo_engine_adapter::WorkerError::new("fixture", "test", ""),
        );
        result.protocol_version = 2;
        println!("{}", serde_json::to_string(&result).unwrap());
    } else if name.contains("crash") {
        std::process::exit(7);
    } else if name.contains("noise") {
        use std::io::Write;
        std::io::stderr()
            .write_all(&vec![b'x'; 512 * 1024])
            .unwrap();
        println!("{{\"protocol_version\":99}}");
    } else if name.contains("protocol") {
        let mut result = ygo_engine_adapter::DuelResult::failure(
            ygo_engine_adapter::WorkerError::new("fixture", "test", ""),
        );
        result.protocol_version = 99;
        println!("{}", serde_json::to_string(&result).unwrap());
    } else {
        println!("not-json");
    }
}

fn stream_fixture(name: &str) {
    use std::io::{BufReader, Write};
    use ygo_engine_adapter::stream_protocol::{
        read_frame, write_frame, FfiDirection, HostAck, StreamRequest, StreamResult, WorkerFrame,
        WorkerFrameKind, STREAM_VERSION,
    };
    let stdin = std::io::stdin();
    let mut input = BufReader::new(stdin);
    let request: StreamRequest = read_frame(&mut input).unwrap();
    let stdout = std::io::stdout();
    let mut output = stdout.lock();
    let frames = if name.contains("stream-no-events") {
        vec![]
    } else if name.contains("stream-invalid") {
        vec![WorkerFrame {
            version: STREAM_VERSION,
            attempt_id: request.attempt_id.clone(),
            sequence: 4,
            call_id: "invalid".into(),
            direction: FfiDirection::IntoCore,
            name: "OCG_DuelProcess".into(),
            kind: WorkerFrameKind::FfiEntered,
        }]
    } else {
        vec![
            frame(
                &request.attempt_id,
                1,
                "OCG_DuelProcess",
                WorkerFrameKind::FfiEntered,
            ),
            frame(
                &request.attempt_id,
                2,
                "card_reader",
                WorkerFrameKind::FfiEntered,
            ),
            frame(
                &request.attempt_id,
                2,
                "card_reader",
                WorkerFrameKind::FfiReturned,
            ),
            frame(
                &request.attempt_id,
                1,
                "OCG_DuelProcess",
                WorkerFrameKind::FfiReturned,
            ),
        ]
    };
    for frame in frames {
        let sequence = frame.sequence;
        let call_id = frame.call_id.clone();
        write_frame(&mut output, &frame).unwrap();
        if name.contains("stream-exit-after-entry") && frame.kind == WorkerFrameKind::FfiEntered {
            output.flush().unwrap();
            std::process::exit(9);
        }
        let ack: HostAck = read_frame(&mut input).unwrap();
        if !ack.matches(&request.attempt_id, sequence, &call_id) {
            std::process::exit(8);
        }
        if name.contains("stream-after-entry") && frame.kind == WorkerFrameKind::FfiEntered {
            std::process::exit(9);
        }
    }
    let result = StreamResult {
        version: STREAM_VERSION,
        attempt_id: request.attempt_id.clone(),
        result: ygo_engine_adapter::DuelResult::failure(ygo_engine_adapter::WorkerError::new(
            "fixture", "stream", "",
        )),
    };
    write_frame(&mut output, &result).unwrap();
    if name.contains("stream-after-result") {
        write_frame(
            &mut output,
            &frame(
                &request.attempt_id,
                3,
                "OCG_DuelProcess",
                WorkerFrameKind::FfiEntered,
            ),
        )
        .unwrap();
    }
    output.flush().unwrap();
}

fn frame(
    attempt_id: &str,
    sequence: u64,
    name: &str,
    kind: ygo_engine_adapter::stream_protocol::WorkerFrameKind,
) -> ygo_engine_adapter::stream_protocol::WorkerFrame {
    use ygo_engine_adapter::stream_protocol::{call_id, FfiDirection, WorkerFrame, STREAM_VERSION};
    WorkerFrame {
        version: STREAM_VERSION,
        attempt_id: attempt_id.into(),
        sequence,
        call_id: call_id(attempt_id, sequence),
        direction: if name == "card_reader" {
            FfiDirection::OutOfCore
        } else {
            FfiDirection::IntoCore
        },
        name: name.into(),
        kind,
    }
}
