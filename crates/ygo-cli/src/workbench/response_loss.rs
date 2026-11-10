//! Test-only transport failure after real routing has completed.
use super::{analysis_http::AnalysisHttpService, HttpResponse};
use std::{
    io::Write,
    net::TcpStream,
    sync::mpsc::{Receiver, SyncSender},
    time::Duration,
};
pub(super) struct ResponseFault {
    pub method: String,
    pub path: String,
    pub remaining: usize,
    pub truncate: bool,
    pub entered: SyncSender<()>,
    pub release: Receiver<()>,
}
pub(super) fn apply(
    service: &AnalysisHttpService,
    method: &str,
    path: &str,
    stream: &mut TcpStream,
    response: &HttpResponse,
) -> Result<bool, String> {
    let fault = {
        let mut guard = service
            .response_fault
            .lock()
            .map_err(|_| "response_fault_lock")?;
        if let Some(fault) = guard.as_mut() {
            if fault.method == method && fault.path == path {
                fault.remaining = fault.remaining.saturating_sub(1);
                if fault.remaining == 0 {
                    guard.take()
                } else {
                    None
                }
            } else {
                None
            }
        } else {
            None
        }
    };
    let Some(fault) = fault else {
        return Ok(false);
    };
    fault
        .entered
        .try_send(())
        .map_err(|_| "response_fault_handshake")?;
    fault
        .release
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "response_fault_timeout")?;
    if fault.truncate {
        let headers = format!("HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n",
            response.status, super::status_text(response.status), response.content_type, response.body.len());
        stream
            .write_all(headers.as_bytes())
            .map_err(|_| "response_fault_write")?;
        stream
            .write_all(&response.body[..response.body.len() / 2])
            .map_err(|_| "response_fault_write")?;
        stream.flush().map_err(|_| "response_fault_flush")?;
    }
    stream
        .shutdown(std::net::Shutdown::Both)
        .map_err(|_| "response_fault_shutdown")?;
    Ok(true)
}

// No bytes are sent, so the observed mode does not depend on sender scheduling.
#[cfg(windows)]
#[test]
fn accepted_connection_uses_blocking_reads_with_a_timeout() {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let _client = TcpStream::connect(listener.local_addr().unwrap()).unwrap();
    let deadline = std::time::Instant::now() + Duration::from_secs(2);
    let stream = loop {
        match listener.accept() {
            Ok((stream, _)) => break stream,
            Err(error)
                if error.kind() == std::io::ErrorKind::WouldBlock
                    && std::time::Instant::now() < deadline =>
            {
                std::thread::sleep(Duration::from_millis(1));
            }
            Err(error) => panic!("accept did not become ready before deadline: {error}"),
        }
    };
    super::configure_connection(&stream).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_millis(200)))
        .unwrap();
    let error = stream.peek(&mut [0]).unwrap_err();
    assert_eq!(error.kind(), std::io::ErrorKind::TimedOut);
}
