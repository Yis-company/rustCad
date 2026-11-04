// SPDX-License-Identifier: LGPL-2.1-or-later
use rustcad_geometry_kernel::Kernel;

const TOLERANCE: f64 = 1e-6;

#[test]
fn a_rigid_placement_preserves_local_geometry_and_precision()
-> Result<(), Box<dyn std::error::Error>> {
    let mut kernel = Kernel::new(TOLERANCE)?;
    let original = kernel.box_shape([0.0; 3], [1.0, 2.0, 3.0])?;
    let before = kernel.bounds(&original)?;
    let tolerance = kernel.max_entity_tolerance_mm(&original)?;
    let half = std::f64::consts::FRAC_1_SQRT_2;
    let moved = kernel.placed(&original, [10.0, 20.0, 30.0], [0.0, 0.0, half, half])?;
    let bounds = kernel.bounds(&moved)?.ok_or("empty placed bounds")?;
    for (actual, expected) in bounds.into_iter().zip([8.0, 20.0, 30.0, 10.0, 21.0, 33.0]) {
        assert!((actual - expected).abs() < 2e-6, "{bounds:?}");
    }
    assert_eq!(kernel.classify(&moved, [9.0, 20.5, 31.5])?, "In");
    assert_eq!(kernel.classify(&moved, [10.5, 20.5, 31.5])?, "Out");
    assert_eq!(kernel.bounds(&original)?, before);
    assert_eq!(kernel.max_entity_tolerance_mm(&moved)?, tolerance);
    assert_eq!(kernel.max_entity_tolerance_mm(&original)?, tolerance);
    Ok(())
}

#[test]
fn invalid_rigid_placements_are_refused() -> Result<(), Box<dyn std::error::Error>> {
    let mut kernel = Kernel::new(TOLERANCE)?;
    let shape = kernel.box_shape([0.0; 3], [1.0; 3])?;
    for rotation in [[0.0; 4], [0.0, 0.0, 0.0, 2.0], [f64::NAN, 0.0, 0.0, 1.0]] {
        assert!(kernel.placed(&shape, [0.0; 3], rotation).is_err());
    }
    assert!(
        kernel
            .placed(&shape, [f64::INFINITY, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0])
            .is_err()
    );
    let mut other = Kernel::new(TOLERANCE)?;
    assert!(
        other
            .placed(&shape, [0.0; 3], [0.0, 0.0, 0.0, 1.0])
            .is_err()
    );
    Ok(())
}

#[test]
fn a_plate_has_a_real_through_hole() -> Result<(), Box<dyn std::error::Error>> {
    let mut kernel = Kernel::new(TOLERANCE)?;
    let plate = kernel.box_shape([0.0; 3], [100.0, 60.0, 10.0])?;
    let drill = kernel.cylinder([50.0, 30.0, -5.0], 5.0, 20.0)?;
    let cut = kernel.subtract(&plate, &drill)?;
    assert!(kernel.validity(&cut)?.0);
    assert_eq!(kernel.solid_count(&cut)?, 1);
    let expected = 60000.0 - 250.0 * std::f64::consts::PI;
    assert!((kernel.volume(&cut, 0.001)? - expected).abs() < expected * 1e-7);
    assert_eq!(kernel.classify(&cut, [50.0, 30.0, 5.0])?, "Out");
    assert_eq!(kernel.classify(&cut, [40.0, 30.0, 5.0])?, "In");
    Ok(())
}

#[test]
fn subtraction_can_return_nothing() -> Result<(), Box<dyn std::error::Error>> {
    let mut kernel = Kernel::new(TOLERANCE)?;
    let a = kernel.box_shape([0.0; 3], [1.0, 2.0, 3.0])?;
    let b = kernel.box_shape([0.0; 3], [1.0, 2.0, 3.0])?;
    let cut = kernel.subtract(&a, &b)?;
    assert_eq!(kernel.solid_count(&cut)?, 0);
    assert_eq!(kernel.volume(&cut, 0.001)?, 0.0);
    assert_eq!(kernel.bounds(&cut)?, None);
    assert_eq!(kernel.classify(&cut, [0.5, 1.0, 1.5])?, "Out");
    assert!(
        kernel.into_step(cut).is_err(),
        "an empty result must not export a fabricated solid"
    );
    Ok(())
}

#[test]
fn inputs_and_shape_ownership_are_checked() -> Result<(), Box<dyn std::error::Error>> {
    for invalid in [0.0, -1.0, f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        assert!(Kernel::new(invalid).is_err());
        let mut kernel = Kernel::new(TOLERANCE)?;
        for axis in 0..3 {
            let mut size = [1.0; 3];
            size[axis] = invalid;
            assert!(kernel.box_shape([0.0; 3], size).is_err());
        }
        assert!(kernel.cylinder([0.0; 3], invalid, 1.0).is_err());
        assert!(kernel.cylinder([0.0; 3], 1.0, invalid).is_err());
        if !invalid.is_finite() {
            for axis in 0..3 {
                let mut origin = [0.0; 3];
                origin[axis] = invalid;
                assert!(kernel.box_shape(origin, [1.0; 3]).is_err());
                assert!(kernel.cylinder(origin, 1.0, 1.0).is_err());
            }
        }
    }
    let mut a = Kernel::new(TOLERANCE)?;
    let mut b = Kernel::new(TOLERANCE)?;
    let own = a.box_shape([0.0; 3], [1.0; 3])?;
    let foreign = b.box_shape([0.0; 3], [1.0; 3])?;
    assert!(a.subtract(&own, &foreign).is_err());
    assert!(a.into_step(foreign).is_err());
    Ok(())
}

#[test]
fn a_small_overlap_keeps_its_cut_boundary() -> Result<(), Box<dyn std::error::Error>> {
    for budget in [TOLERANCE, 1e-3] {
        let mut kernel = Kernel::new(budget)?;
        let a = kernel.box_shape([0.0; 3], [0.01, 0.02, 0.03])?;
        let b = kernel.box_shape([0.0, 0.01999, 0.0], [0.01, 0.02, 0.03])?;
        let cut = kernel.subtract(&a, &b)?;
        let bounds = kernel.bounds(&cut)?.ok_or("cut unexpectedly empty")?;
        assert!((bounds[4] - 0.01999).abs() <= 2e-6, "{bounds:?}");
        assert!((kernel.volume(&cut, 1e-5)? - 5.997e-6).abs() <= 6.1e-13);
        assert_eq!(kernel.classify(&cut, [0.005, 0.019995, 0.015])?, "Out");
    }
    Ok(())
}

#[test]
fn a_budget_below_native_entity_tolerances_is_refused() -> Result<(), Box<dyn std::error::Error>> {
    let mut kernel = Kernel::new(1e-8)?;
    assert!(kernel.box_shape([0.0; 3], [1.0; 3]).is_err());
    assert!(kernel.cylinder([0.0; 3], 1.0, 1.0).is_err());
    Ok(())
}

#[test]
fn a_large_near_tangent_cut_preserves_the_budget_and_operands()
-> Result<(), Box<dyn std::error::Error>> {
    let mut kernel = Kernel::new(TOLERANCE)?;
    let plate = kernel.box_shape([0.0; 3], [10000.0, 6000.0, 1000.0])?;
    let drill = kernel.cylinder([10499.99999, 3000.0, -500.0], 500.0, 2000.0)?;
    let before = [
        (
            kernel.bounds(&plate)?,
            kernel.max_entity_tolerance_mm(&plate)?,
            kernel.volume(&plate, 0.1)?,
        ),
        (
            kernel.bounds(&drill)?,
            kernel.max_entity_tolerance_mm(&drill)?,
            kernel.volume(&drill, 0.1)?,
        ),
    ];
    let cut = kernel.subtract(&plate, &drill)?;
    assert!(kernel.max_entity_tolerance_mm(&cut)? <= TOLERANCE);
    assert!(kernel.validity(&cut)?.0);
    assert_eq!(kernel.solid_count(&cut)?, 1);
    assert_eq!(kernel.classify(&cut, [4000.0, 3000.0, 500.0])?, "In");
    assert_eq!(kernel.classify(&cut, [9999.999995, 3000.0, 500.0])?, "Out");
    let after = [
        (
            kernel.bounds(&plate)?,
            kernel.max_entity_tolerance_mm(&plate)?,
            kernel.volume(&plate, 0.1)?,
        ),
        (
            kernel.bounds(&drill)?,
            kernel.max_entity_tolerance_mm(&drill)?,
            kernel.volume(&drill, 0.1)?,
        ),
    ];
    assert_eq!(before, after, "result normalization changed an operand");
    assert!(kernel.into_step(cut).is_ok());
    Ok(())
}

#[test]
fn distinct_planes_within_native_confusion_keep_their_cut() -> Result<(), Box<dyn std::error::Error>>
{
    let confusion = ogeom::core::Tolerances::millimetres().confusion();
    for scale in [0.01, 1.0, 100.0] {
        for origin in [[0.0; 3], [10.0, 20.0, 30.0]] {
            for sign in [-1.0, 1.0] {
                for reverse in [false, true] {
                    let mut kernel = Kernel::new(TOLERANCE)?;
                    let size = [scale, 2.0 * scale, 3.0 * scale];
                    let a = kernel.box_shape(origin, size)?;
                    let mut at = origin;
                    at[1] += 2.0 * scale + sign * confusion * 0.5;
                    let b = kernel.box_shape(at, size)?;
                    let result = if reverse {
                        kernel.subtract(&b, &a)
                    } else {
                        kernel.subtract(&a, &b)
                    };
                    let result = result?;
                    assert!(kernel.validity(&result)?.0);
                    let removed = if sign < 0.0 {
                        3.0 * scale * scale * confusion * 0.5
                    } else {
                        0.0
                    };
                    let expected = 6.0 * scale.powi(3) - removed;
                    // Coordinate roundoff times the box's surface area bounds volume noise.
                    let magnitude = origin.iter().map(|x| x.abs()).sum::<f64>() + 6.0 * scale;
                    let error =
                        removed / 8.0 + 64.0 * f64::EPSILON * magnitude * 22.0 * scale * scale;
                    assert!(
                        (kernel.volume(&result, 0.001 * scale)? - expected).abs() <= error,
                        "scale={scale}, origin={origin:?}, sign={sign}, reverse={reverse}"
                    );
                }
            }
        }
    }
    Ok(())
}

#[test]
fn exact_contacts_and_disjoint_face_bounds_remain_supported()
-> Result<(), Box<dyn std::error::Error>> {
    for scale in [0.01, 1.0, 100.0] {
        for origin in [[0.0; 3], [10.0, 20.0, 30.0]] {
            for (offset, volume, solids) in [
                ([0.0, 2.0 * scale, 0.0], 6.0, 1),
                ([scale, 2.0 * scale, 0.0], 6.0, 1),
                ([0.0; 3], 0.0, 0),
                ([0.0, scale, 0.0], 3.0, 1),
                ([1000.0 * scale, 2.0 * scale - 5e-8, 0.0], 6.0, 1),
            ] {
                let mut kernel = Kernel::new(TOLERANCE)?;
                let size = [scale, 2.0 * scale, 3.0 * scale];
                let a = kernel.box_shape(origin, size)?;
                let b = kernel.box_shape(std::array::from_fn(|i| origin[i] + offset[i]), size)?;
                let cut = kernel.subtract(&a, &b)?;
                assert_eq!(kernel.solid_count(&cut)?, solids);
                let want = volume * scale.powi(3);
                assert!(
                    (kernel.volume(&cut, 0.001 * scale)? - want).abs()
                        <= 1e-8 * scale.powi(3) + 1e-7 * want.abs()
                );
            }
        }
    }
    Ok(())
}

#[test]
fn later_cuts_preserve_the_earlier_result() -> Result<(), Box<dyn std::error::Error>> {
    let mut kernel = Kernel::new(TOLERANCE)?;
    let plate = kernel.box_shape([0.0; 3], [100.0, 60.0, 10.0])?;
    let drill = kernel.cylinder([50.0, 30.0, -5.0], 5.0, 20.0)?;
    let earlier = kernel.subtract(&plate, &drill)?;
    let before = (
        kernel.bounds(&earlier)?,
        kernel.volume(&earlier, 0.001)?,
        kernel.max_entity_tolerance_mm(&earlier)?,
    );
    let next_drill = kernel.cylinder([35.0, 30.0, -5.0], 3.0, 20.0)?;
    let result = kernel.subtract(&earlier, &next_drill)?;
    assert_eq!(
        before,
        (
            kernel.bounds(&earlier)?,
            kernel.volume(&earlier, 0.001)?,
            kernel.max_entity_tolerance_mm(&earlier)?
        )
    );
    assert_eq!(kernel.classify(&earlier, [35.0, 30.0, 5.0])?, "In");
    assert_eq!(kernel.classify(&result, [35.0, 30.0, 5.0])?, "Out");
    assert_eq!(kernel.classify(&result, [50.0, 30.0, 5.0])?, "Out");
    assert!(
        (kernel.volume(&result, 0.001)? - (before.1 - 90.0 * std::f64::consts::PI)).abs()
            < before.1 * 1e-7
    );
    Ok(())
}
