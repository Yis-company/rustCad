// SPDX-License-Identifier: LGPL-2.1-or-later
use serde_json::{Value, json};
use std::{
    io::Write,
    process::{Command, Stdio},
};

fn request() -> Value {
    json!({
        "version": 1,
        "plate_mm": [90.0, 45.0, 8.0],
        "hole_center_mm": [32.0, 22.0],
        "hole_radius_mm": 5.0,
        "translation_mm": [14.0, -9.0, 7.0],
        "rotation_xyzw": [0.0, 0.0, std::f64::consts::FRAC_1_SQRT_2, std::f64::consts::FRAC_1_SQRT_2]
    })
}

fn run(input: &str) -> (bool, Value, String) {
    let mut child = Command::new(env!("CARGO_BIN_EXE_rustcad-engine"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(input.as_bytes())
        .unwrap();
    let output = child.wait_with_output().unwrap();
    (
        output.status.success(),
        serde_json::from_slice(&output.stdout).unwrap(),
        String::from_utf8(output.stderr).unwrap(),
    )
}

#[test]
fn the_application_boundary_returns_local_mesh_and_placed_step() {
    let (success, response, stderr) = run(&request().to_string());
    assert!(success, "{stderr}");
    assert_eq!(response["version"], 1);
    assert_eq!(response["ok"], true);
    let expected = (90.0 * 45.0 - 25.0 * std::f64::consts::PI) * 8.0;
    assert!((response["volume_mm3"].as_f64().unwrap() - expected).abs() < expected * 1e-7);
    for (actual, expected) in response["bounds_mm"]
        .as_array()
        .unwrap()
        .iter()
        .zip([-31.0, -9.0, 7.0, 14.0, 81.0, 15.0])
    {
        assert!((actual.as_f64().unwrap() - expected).abs() < 2e-6);
    }
    let vertices = response["mesh"]["vertices"].as_array().unwrap();
    let triangles = response["mesh"]["triangles"].as_array().unwrap();
    assert!(!vertices.is_empty() && !triangles.is_empty());
    for vertex in vertices {
        for (axis, max) in [90.0, 45.0, 8.0].into_iter().enumerate() {
            let value = vertex[axis].as_f64().unwrap();
            assert!(
                (-1e-6..=max + 1e-6).contains(&value),
                "mesh was placed twice"
            );
        }
    }
    for triangle in triangles {
        for index in triangle.as_array().unwrap() {
            assert!((index.as_u64().unwrap() as usize) < vertices.len());
        }
    }
    assert!(!response["step"].as_str().unwrap().is_empty());
}

#[test]
fn invalid_requests_never_return_success_or_geometry() {
    let mut cases = vec!["{".into(), "null".into()];
    for (key, value) in [
        ("version", json!(2)),
        ("plate_mm", json!([90, -45, 8])),
        ("hole_radius_mm", json!(0)),
        ("hole_center_mm", json!([2, 22])),
        ("translation_mm", json!([0, 0])),
        ("rotation_xyzw", json!([0, 0, 0, 0])),
    ] {
        let mut input = request();
        input[key] = value;
        cases.push(input.to_string());
    }
    for input in cases {
        let (success, response, stderr) = run(&input);
        assert!(!success, "{input}");
        assert_eq!(response["ok"], false);
        assert!(response["error"].as_str().is_some_and(|s| !s.is_empty()));
        assert!(!stderr.is_empty());
        assert!(response.get("mesh").is_none() && response.get("step").is_none());
    }
}
