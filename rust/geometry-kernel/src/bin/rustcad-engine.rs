// SPDX-License-Identifier: LGPL-2.1-or-later
//! One isolated, millimetre-based plate evaluation per process. See README.md.

use rustcad_geometry_kernel::Kernel;
use serde_json::{Value, json};
use std::io::{self, Read, Write};

fn number(request: &Value, name: &str) -> Result<f64, String> {
    request[name]
        .as_f64()
        .filter(|v| v.is_finite())
        .ok_or_else(|| format!("{name} must be a finite number"))
}

fn array<const N: usize>(request: &Value, name: &str) -> Result<[f64; N], String> {
    let values = request[name]
        .as_array()
        .filter(|v| v.len() == N)
        .ok_or_else(|| format!("{name} must contain {N} finite numbers"))?;
    let mut result = [0.0; N];
    for (out, value) in result.iter_mut().zip(values) {
        *out = value
            .as_f64()
            .filter(|v| v.is_finite())
            .ok_or_else(|| format!("{name} must contain {N} finite numbers"))?;
    }
    Ok(result)
}

fn evaluate(request: &Value) -> Result<Value, Box<dyn std::error::Error>> {
    if request["version"].as_u64() != Some(1) {
        return Err("unsupported request version; expected 1".into());
    }
    let size: [f64; 3] = array(request, "plate_mm")?;
    let center: [f64; 2] = array(request, "hole_center_mm")?;
    let radius = number(request, "hole_radius_mm")?;
    let translation = array(request, "translation_mm")?;
    let rotation = array(request, "rotation_xyzw")?;
    if size.iter().any(|v| *v <= 0.0) || radius <= 0.0 {
        return Err("plate dimensions and hole radius must be positive".into());
    }
    if center
        .iter()
        .zip(size)
        .any(|(c, side)| c - radius <= 0.0 || c + radius >= side)
    {
        return Err("the through-hole must fit strictly inside the plate".into());
    }
    let mut kernel = Kernel::new(1e-6)?;
    let plate = kernel.box_shape([0.0; 3], size)?;
    let drill = kernel.cylinder([center[0], center[1], -size[2]], radius, 3.0 * size[2])?;
    let result = kernel.subtract(&plate, &drill)?;
    if kernel.solid_count(&result)? != 1 {
        return Err("plate evaluation must produce one solid".into());
    }
    let mesh = kernel.tessellate(&result, 0.02)?;
    if mesh.positions.is_empty() || mesh.triangles.is_empty() || !mesh.deflection_met {
        return Err("kernel did not produce a complete display mesh".into());
    }
    let vertices: Vec<[f64; 3]> = mesh.positions.iter().map(|p| [p.x, p.y, p.z]).collect();
    if vertices.iter().flatten().any(|v| !v.is_finite())
        || mesh
            .triangles
            .iter()
            .flatten()
            .any(|i| *i as usize >= vertices.len())
    {
        return Err("kernel produced an invalid display mesh".into());
    }
    let volume = kernel.volume(&result, 0.001)?;
    if !volume.is_finite() || volume <= 0.0 {
        return Err("kernel produced an invalid volume".into());
    }
    let placed = kernel.placed(&result, translation, rotation)?;
    let bounds = kernel
        .bounds(&placed)?
        .ok_or("kernel produced empty bounds")?;
    let step = kernel.into_step(placed)?;
    Ok(json!({
        "version": 1,
        "ok": true,
        "mesh": {"vertices": vertices, "triangles": mesh.triangles},
        "volume_mm3": volume,
        "bounds_mm": bounds,
        "step": step
    }))
}

fn main() {
    let result = (|| -> Result<Value, Box<dyn std::error::Error>> {
        let mut input = String::new();
        io::stdin().read_to_string(&mut input)?;
        evaluate(&serde_json::from_str(&input)?)
    })();
    let (reply, code) = match result {
        Ok(reply) => (reply, 0),
        Err(error) => {
            eprintln!("{error}");
            (
                json!({"version": 1, "ok": false, "error": error.to_string()}),
                1,
            )
        }
    };
    let mut stdout = io::stdout().lock();
    if serde_json::to_writer(&mut stdout, &reply).is_err() || stdout.write_all(b"\n").is_err() {
        std::process::exit(1);
    }
    std::process::exit(code);
}
