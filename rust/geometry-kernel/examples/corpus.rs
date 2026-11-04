// SPDX-License-Identifier: LGPL-2.1-or-later
//! One process per fixture lets the driver bound failed or stalled operations.
use rustcad_geometry_kernel::{Kernel, Shape};
use serde_json::{Value, json};
use std::{collections::BTreeMap, error::Error, path::Path};

fn point(p: [f64; 3], state: &str) -> Value {
    json!({"point":p,"state":state})
}

fn manifold(mesh: &ogeom::topo::Triangulation) -> (bool, usize) {
    let mut edges: BTreeMap<(u32, u32), Vec<(usize, bool)>> = BTreeMap::new();
    let mut adjacency = vec![Vec::new(); mesh.triangles.len()];
    let mut valid = true;
    for (index, t) in mesh.triangles.iter().enumerate() {
        let [a, b, c] = t.map(|i| mesh.positions[i as usize]);
        valid &= (b - a).cross(c - a).magnitude() > 0.0;
        for i in 0..3 {
            let (a, b) = (t[i], t[(i + 1) % 3]);
            edges
                .entry((a.min(b), a.max(b)))
                .or_default()
                .push((index, a < b));
        }
    }
    for uses in edges.values() {
        if let [(a, forward), (b, reverse)] = uses.as_slice() {
            valid &= forward != reverse;
            adjacency[*a].push(*b);
            adjacency[*b].push(*a);
        } else {
            valid = false;
        }
    }
    let mut seen = vec![false; adjacency.len()];
    let mut components = 0;
    for i in 0..seen.len() {
        if seen[i] {
            continue;
        }
        components += 1;
        let mut stack = vec![i];
        seen[i] = true;
        while let Some(j) = stack.pop() {
            for &next in &adjacency[j] {
                if !seen[next] {
                    seen[next] = true;
                    stack.push(next);
                }
            }
        }
    }
    (valid, components)
}

fn execute(name: &str, s: f64, gap_factor: f64, out: &Path) -> Result<Value, Box<dyn Error>> {
    let criteria: Value = serde_json::from_str(include_str!("../criteria.json"))?;
    let tolerance = criteria["modeling_tolerance_mm"]
        .as_f64()
        .ok_or("missing tolerance")?;
    if !s.is_finite() || s <= 0.0 || !gap_factor.is_finite() || gap_factor < 0.0 {
        return Err("invalid fixture scale or gap".into());
    }
    let mut kernel = Kernel::new(tolerance)?;
    let runtime_settings = json!({
        "units": "mm",
        "native_confusion_mm": ogeom::core::Tolerances::millimetres().confusion(),
        "entity_tolerance_budget_mm": tolerance,
        "entity_tolerance_policy": "validate_native_claims_without_normalization",
        "analytic_geometry_policy": "preserve_distinct_supports",
    });
    let gap = gap_factor * tolerance;
    let diagnostic = name.contains("gap") && gap_factor > 0.0 && gap_factor <= 1.0;
    let (base, tool, expected): (Shape, Shape, Value) = if name == "plate"
        || name.starts_with("cylinder-gap")
    {
        let a = kernel.box_shape([0.0; 3], [100.0 * s, 60.0 * s, 10.0 * s])?;
        let x = if name == "plate" {
            50.0 * s
        } else if name == "cylinder-gap-in" {
            105.0 * s - gap
        } else {
            105.0 * s + gap
        };
        let b = kernel.cylinder([x, 30.0 * s, -5.0 * s], 5.0 * s, 20.0 * s)?;
        let mut points = vec![point([40.0 * s, 30.0 * s, 5.0 * s], "In")];
        let removed = if name == "plate" {
            points.push(point([50.0 * s, 30.0 * s, 5.0 * s], "Out"));
            250.0 * std::f64::consts::PI * s.powi(3)
        } else if name == "cylinder-gap-in" {
            let r = 5.0 * s;
            let segment =
                r * r * ((r - gap) / r).acos() - (r - gap) * (2.0 * r * gap - gap * gap).sqrt();
            if !diagnostic && gap > 0.0 {
                points.push(point([100.0 * s - gap / 2.0, 30.0 * s, 5.0 * s], "Out"));
            }
            segment * 10.0 * s
        } else {
            0.0
        };
        (
            a,
            b,
            json!({"solids":1,"volume":60000.0*s.powi(3)-removed,"bounds":[0,0,0,100.0*s,60.0*s,10.0*s],"points":points,"cylinder":name=="plate"}),
        )
    } else {
        let a = kernel.box_shape([0.0; 3], [s, 2.0 * s, 3.0 * s])?;
        let origin = match name {
            "overlap" | "reverse" => [0.0, s, 0.0],
            "disjoint" => [0.0, 3.0 * s, 0.0],
            "face-contact" => [0.0, 2.0 * s, 0.0],
            "edge-contact" => [s, 2.0 * s, 0.0],
            "identical" => [0.0; 3],
            "enclosing" => [-s, -s, -s],
            "box-gap-out" => [0.0, 2.0 * s + gap, 0.0],
            "box-gap-in" => [0.0, 2.0 * s - gap, 0.0],
            _ => return Err(format!("unknown fixture {name}").into()),
        };
        let size = if name == "enclosing" {
            [3.0 * s, 4.0 * s, 5.0 * s]
        } else {
            [s, 2.0 * s, 3.0 * s]
        };
        let b = kernel.box_shape(origin, size)?;
        let empty = name == "identical" || name == "enclosing";
        let (low_y, high_y, volume) = match name {
            "overlap" => (0.0, s, 3.0 * s.powi(3)),
            "reverse" => (2.0 * s, 3.0 * s, 3.0 * s.powi(3)),
            "box-gap-in" => (0.0, 2.0 * s - gap, 6.0 * s.powi(3) - 3.0 * s * s * gap),
            _ => (0.0, 2.0 * s, 6.0 * s.powi(3)),
        };
        let mut points = vec![point(
            [s / 2.0, (low_y + high_y) / 2.0, 1.5 * s],
            if empty { "Out" } else { "In" },
        )];
        if name == "box-gap-in" && !diagnostic {
            points.push(point([s / 2.0, 2.0 * s - gap / 2.0, 1.5 * s], "Out"));
        }
        let expected = json!({"solids":if empty {0} else {1},"volume":if empty {0.0} else {volume},"bounds":if empty {Value::Null} else {json!([0.0,low_y,0.0,s,high_y,3.0*s])},"points":points,"cylinder":false});
        if name == "reverse" {
            (b, a, expected)
        } else {
            (a, b, expected)
        }
    };
    let mut expected = expected;
    let volume_absolute = 1e-8 * s.powi(3);
    expected["volume_absolute"] = json!(volume_absolute);
    std::fs::create_dir_all(out)?;
    std::fs::write(
        out.join("expected.json"),
        serde_json::to_string_pretty(&expected)?,
    )?;
    let result = match kernel.subtract(&base, &tool) {
        Ok(shape) => shape,
        Err(error) => {
            return Ok(
                json!({"status":"error","stage":"boolean","case":name,"scale":s,"gap_factor":gap_factor,"runtime_settings":runtime_settings,"expected":expected,"diagnostic":diagnostic,"error":error.to_string(),"precision_error":matches!(error,ogeom::core::OgeomError::Numeric(_)|ogeom::core::OgeomError::NotDone(_))}),
            );
        }
    };
    let solid_count = kernel.solid_count(&result)?;
    let max_entity_tolerance_mm = kernel.max_entity_tolerance_mm(&result)?;
    let (valid, diagnosis) = kernel.validity(&result)?;
    let chord = criteria["tessellation_chord_mm_at_scale_1"]
        .as_f64()
        .ok_or("missing chord")?
        * s;
    let volume = kernel.volume(&result, chord)?;
    let bounds = kernel.bounds(&result)?;
    let mesh = kernel.tessellate(&result, chord)?;
    let (mesh_manifold, components) = manifold(&mesh);
    let mut classes = Vec::new();
    for sample in expected["points"].as_array().ok_or("missing points")? {
        let p = sample["point"].as_array().ok_or("missing point")?;
        classes.push(kernel.classify(
            &result,
            [
                p[0].as_f64().ok_or("invalid x")?,
                p[1].as_f64().ok_or("invalid y")?,
                p[2].as_f64().ok_or("invalid z")?,
            ],
        )?);
    }
    let empty = expected["solids"] == 0;
    let mut errors = Vec::new();
    if !valid {
        errors.push(format!("invalid BRep: {diagnosis}"));
    }
    if solid_count as u64 != expected["solids"].as_u64().ok_or("invalid solid count")? {
        errors.push(format!("solid count {solid_count}"));
    }
    let expected_volume = expected["volume"].as_f64().ok_or("invalid volume")?;
    if (volume - expected_volume).abs() > volume_absolute + 1e-7 * expected_volume.abs() {
        errors.push(format!("volume {volume} != {expected_volume}"));
    }
    match (bounds, expected["bounds"].as_array()) {
        (Some(actual), Some(want)) => {
            for (a, b) in actual.iter().zip(want) {
                if (a - b.as_f64().ok_or("invalid bound")?).abs() > 2e-6 {
                    errors.push(format!("bounds envelope {actual:?} != {want:?}"));
                    break;
                }
            }
        }
        (None, None) => {}
        _ => errors.push("empty bounds mismatch".into()),
    }
    for (actual, want) in classes
        .iter()
        .zip(expected["points"].as_array().ok_or("missing points")?)
    {
        if *actual != want["state"] {
            errors.push(format!("classification {actual} != {}", want["state"]));
        }
    }
    if !empty && (!mesh_manifold || components != 1 || !mesh.deflection_met || mesh.volume() <= 0.0)
    {
        errors.push(format!(
            "mesh manifold={mesh_manifold} components={components} deflection={} volume={}",
            mesh.deflection_met,
            mesh.volume()
        ));
    }
    if !empty
        && (mesh.volume() - expected_volume).abs() > volume_absolute + 1e-3 * expected_volume.abs()
    {
        errors.push("mesh volume outside declared tolerance".into());
    }
    if empty && (!mesh.triangles.is_empty() || !mesh.positions.is_empty()) {
        errors.push("empty result contains tessellation".into());
    }
    let mut obj = String::new();
    use std::fmt::Write;
    for p in &mesh.positions {
        writeln!(obj, "v {} {} {}", p.x, p.y, p.z)?;
    }
    for t in &mesh.triangles {
        writeln!(obj, "f {} {} {}", t[0] + 1, t[1] + 1, t[2] + 1)?;
    }
    std::fs::write(out.join("mesh.obj"), obj)?;
    if !empty {
        match kernel.into_step(result) {
            Ok(text) => std::fs::write(out.join("shape.step"), text)?,
            Err(error) => errors.push(format!("STEP export: {error}")),
        }
    }
    Ok(
        json!({"status":if errors.is_empty() {"pass"} else {"fail"},"diagnostic":diagnostic,"case":name,"scale":s,"gap_factor":gap_factor,"runtime_settings":runtime_settings,"expected":expected,"actual":{"volume":volume,"bounds":bounds,"bounds_kind":"tolerance_envelope","max_entity_tolerance_mm":max_entity_tolerance_mm,"solids":solid_count,"valid":valid,"diagnosis":diagnosis,"classifications":classes,"mesh_manifold":mesh_manifold,"mesh_components":components,"mesh_volume":mesh.volume(),"triangles":mesh.triangles.len()},"errors":errors}),
    )
}

fn main() {
    let args: Vec<_> = std::env::args().collect();
    let result = (|| -> Result<Value, Box<dyn Error>> {
        if args.len() != 5 {
            return Err("usage: corpus CASE SCALE GAP_FACTOR OUTPUT_DIRECTORY".into());
        }
        execute(
            &args[1],
            args[2].parse()?,
            args[3].parse()?,
            Path::new(&args[4]),
        )
    })();
    let report = match result {
        Ok(value) => value,
        Err(error) => {
            json!({"status":"error","stage":"measurement_or_input","error":error.to_string()})
        }
    };
    println!("{report}");
    if report["status"] != "pass" {
        std::process::exit(1);
    }
}
