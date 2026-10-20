use std::time::Instant;
use serde_json::{json, Value};

pub fn tester_probe_endpoint(
    url: &str,
    method_opt: Option<&str>,
    expected_status_opt: Option<u16>,
    payload_opt: Option<&str>,
    timeout_seconds_opt: Option<f64>,
) -> Value {
    let method = method_opt.unwrap_or("GET").to_uppercase();
    let expected = expected_status_opt.unwrap_or(200);
    let timeout_secs = timeout_seconds_opt.unwrap_or(5.0);
    let timeout = std::time::Duration::from_secs_f64(timeout_secs);

    let start = Instant::now();

    let result = if method == "POST" {
        let agent = ureq::AgentBuilder::new().timeout(timeout).build();
        let body = payload_opt.unwrap_or("{}");
        agent
            .post(url)
            .set("Content-Type", "application/json")
            .send_string(body)
    } else {
        let agent = ureq::AgentBuilder::new().timeout(timeout).build();
        agent.get(url).call()
    };

    let elapsed_ms = start.elapsed().as_millis();

    match result {
        Ok(response) => {
            let status = response.status();
            let matched = status == expected;
            json!({
                "url": url,
                "method": method,
                "status": status,
                "expected_status": expected,
                "passed": matched,
                "latency_ms": elapsed_ms
            })
        }
        Err(e) => {
            json!({
                "url": url,
                "method": method,
                "passed": false,
                "error": e.to_string(),
                "latency_ms": elapsed_ms
            })
        }
    }
}
