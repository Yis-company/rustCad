// SPDX-License-Identifier: LGPL-2.1-or-later
//! Rust solid-modeling boundary. Coordinates and STEP output are millimetres.
//! Shapes are owned handles into the Kernel that created them, not persisted IDs.

pub use ogeom::topo::Shape;
use ogeom::{
    algo, boolean,
    core::{OgeomError, OgeomResult, Tolerances},
    doc::Document,
    io,
    math::{Direction, Frame, Point, Quaternion, Transform, Vector},
    mesh::{self, Deflection},
    topo::{Model, ShapeType, Triangulation, explore_unique},
};

pub struct Kernel {
    model: Model,
    tolerances: Tolerances,
    tolerance_budget_mm: f64,
}

// The pinned ogeom STEP writer emits this fixed uncertainty in millimetres.
const STEP_UNCERTAINTY_MM: f64 = 1e-6;

impl Kernel {
    /// Accept entities only within this declared tolerance budget, in millimetres.
    /// This is not a guarantee that every feature of that size can be resolved.
    pub fn new(tolerance_budget_mm: f64) -> OgeomResult<Self> {
        if !tolerance_budget_mm.is_finite() || tolerance_budget_mm <= 0.0 {
            return Err(OgeomError::Construction(
                "tolerance must be finite and positive".into(),
            ));
        }
        Ok(Self {
            model: Model::new(),
            tolerances: Tolerances::millimetres(),
            tolerance_budget_mm,
        })
    }

    fn frame(&self, origin: [f64; 3]) -> OgeomResult<Frame> {
        if !origin.iter().all(|x| x.is_finite()) {
            return Err(OgeomError::Construction("origin must be finite".into()));
        }
        Frame::new(
            Point::new(origin[0], origin[1], origin[2]),
            Direction::Z,
            Direction::X,
            self.tolerances,
        )
    }

    fn checked_tolerance_mm(&self, shape: &Shape, limit_mm: f64) -> OgeomResult<f64> {
        if self.model.node(shape).is_none() {
            return Err(OgeomError::Dangling(
                "shape belongs to another kernel".into(),
            ));
        }
        let mut maximum: f64 = 0.0;
        for kind in [ShapeType::Vertex, ShapeType::Edge, ShapeType::Face] {
            for entity in explore_unique(&self.model, shape, kind)? {
                let node = self.model.node(&entity).ok_or_else(|| {
                    OgeomError::Dangling("shape contains a missing entity".into())
                })?;
                if let Some(tolerance) = node.data().tolerance() {
                    let world_mm = tolerance.get()
                        * entity.transform(self.model.datums())?.scale_factor().abs();
                    if !world_mm.is_finite() {
                        return Err(OgeomError::Numeric(
                            "non-finite entity tolerance in millimetres".into(),
                        ));
                    }
                    maximum = maximum.max(world_mm);
                }
            }
        }
        if maximum > limit_mm {
            return Err(OgeomError::Numeric(
                format!(
                    "precision budget exceeded: declared entity tolerance {maximum} mm > {limit_mm} mm"
                )
                .into(),
            ));
        }
        Ok(maximum)
    }

    /// Maximum declared entity tolerance, including placements; refuses over-budget shapes.
    pub fn max_entity_tolerance_mm(&self, shape: &Shape) -> OgeomResult<f64> {
        self.checked_tolerance_mm(shape, self.tolerance_budget_mm)
    }

    fn validate(&self, shape: &Shape, limit_mm: f64) -> OgeomResult<()> {
        self.checked_tolerance_mm(shape, limit_mm)?;
        let diagnosis = algo::check(&self.model, shape, self.tolerances)?;
        if !diagnosis.is_valid() {
            return Err(OgeomError::Invariant(diagnosis.to_string().into()));
        }
        Ok(())
    }

    pub fn box_shape(&mut self, origin: [f64; 3], size: [f64; 3]) -> OgeomResult<Shape> {
        let frame = self.frame(origin)?;
        let shape = algo::make_box(
            &mut self.model,
            frame,
            (size[0], size[1], size[2]),
            self.tolerances,
        )?
        .shape;
        self.validate(&shape, self.tolerance_budget_mm)?;
        Ok(shape)
    }

    pub fn cylinder(&mut self, origin: [f64; 3], radius: f64, height: f64) -> OgeomResult<Shape> {
        let frame = self.frame(origin)?;
        let shape =
            algo::make_cylinder(&mut self.model, frame, radius, height, self.tolerances)?.shape;
        self.validate(&shape, self.tolerance_budget_mm)?;
        Ok(shape)
    }

    pub fn subtract(&mut self, base: &Shape, tool: &Shape) -> OgeomResult<Shape> {
        self.max_entity_tolerance_mm(base)?;
        self.max_entity_tolerance_mm(tool)?;
        let shape = boolean::cut(
            &mut self.model,
            base,
            tool,
            self.tolerances.preserving_analytic_geometry(),
        )?
        .shape;
        self.validate(&shape, self.tolerance_budget_mm)?;
        Ok(shape)
    }

    /// Return a rigidly placed shape; rotation is a unit quaternion in XYZW order.
    /// The original shape and its object-local geometry remain unchanged.
    pub fn placed(
        &mut self,
        shape: &Shape,
        translation_mm: [f64; 3],
        rotation_xyzw: [f64; 4],
    ) -> OgeomResult<Shape> {
        self.max_entity_tolerance_mm(shape)?;
        self.frame(translation_mm)?;
        let [x, y, z, w] = rotation_xyzw;
        let rotation = Quaternion::new(w, x, y, z);
        if !rotation_xyzw.iter().all(|v| v.is_finite())
            || (rotation.square_norm() - 1.0).abs() > 1e-10
        {
            return Err(OgeomError::Construction(
                "rotation must be a finite unit quaternion".into(),
            ));
        }
        let [x, y, z] = translation_mm;
        let transform = Transform::translation(Vector::new(x, y, z))
            * Transform::from_quaternion(rotation.normalized(self.tolerances)?);
        let placed = self.model.placed(shape, transform);
        self.validate(&placed, self.tolerance_budget_mm)?;
        Ok(placed)
    }

    pub fn solid_count(&self, shape: &Shape) -> OgeomResult<usize> {
        self.max_entity_tolerance_mm(shape)?;
        Ok(explore_unique(&self.model, shape, ShapeType::Solid)?.len())
    }

    pub fn validity(&self, shape: &Shape) -> OgeomResult<(bool, String)> {
        self.max_entity_tolerance_mm(shape)?;
        let diagnosis = algo::check(&self.model, shape, self.tolerances)?;
        Ok((diagnosis.is_valid(), diagnosis.to_string()))
    }

    /// Conservative bounds including entity tolerances, not tight geometric extrema.
    pub fn bounds(&self, shape: &Shape) -> OgeomResult<Option<[f64; 6]>> {
        self.max_entity_tolerance_mm(shape)?;
        let bounds = algo::shape_bounds(&self.model, shape, self.tolerances)?;
        Ok(bounds
            .low()
            .zip(bounds.high())
            .map(|(a, b)| [a.x, a.y, a.z, b.x, b.y, b.z]))
    }

    pub fn volume(&self, shape: &Shape, chord_mm: f64) -> OgeomResult<f64> {
        let deflection = Deflection::with_chord(chord_mm)?;
        if self.solid_count(shape)? == 0 {
            return Ok(0.0);
        }
        Ok(algo::volume_properties(&self.model, shape, deflection, self.tolerances)?.mass)
    }

    pub fn classify(&self, shape: &Shape, point: [f64; 3]) -> OgeomResult<&'static str> {
        self.frame(point)?;
        if self.solid_count(shape)? == 0 {
            return Ok("Out");
        }
        let state = algo::classify_in_solid_exact_banded(
            &self.model,
            shape,
            Point::new(point[0], point[1], point[2]),
            self.tolerances.confusion(),
            self.tolerances,
        )?;
        Ok(match state {
            algo::Containment::In => "In",
            algo::Containment::Out => "Out",
            algo::Containment::On => "On",
        })
    }

    pub fn tessellate(&self, shape: &Shape, chord_mm: f64) -> OgeomResult<Triangulation> {
        self.max_entity_tolerance_mm(shape)?;
        mesh::triangulate(
            &self.model,
            shape,
            Deflection::with_chord(chord_mm)?,
            self.tolerances,
        )
    }

    /// Export only the requested result; no input tools or intermediate solids.
    pub fn into_step(self, shape: Shape) -> OgeomResult<String> {
        self.validate(&shape, self.tolerance_budget_mm.min(STEP_UNCERTAINTY_MM))?;
        let mut document = Document::over(self.model);
        document.add_part("rustCad result", shape);
        io::write_step(&document, self.tolerances)
    }
}

#[cfg(test)]
mod precision_tests {
    use super::*;

    fn legacy_cut(kernel: &mut Kernel) -> OgeomResult<(Shape, Shape)> {
        // Reproduce the former unit/precision mix-up without using the adapter's builder.
        let loose = Tolerances::with_scale(0.1)?;
        let a = algo::make_box(&mut kernel.model, Frame::WORLD, (0.01, 0.02, 0.03), loose)?.shape;
        let at = Frame::new(
            Point::new(0.0, 0.01999, 0.0),
            Direction::Z,
            Direction::X,
            loose,
        )?;
        let b = algo::make_box(&mut kernel.model, at, (0.01, 0.02, 0.03), loose)?.shape;
        let bad = boolean::cut(&mut kernel.model, &a, &b, loose)?.shape;
        Ok((bad, a))
    }

    #[test]
    fn an_over_toleranced_native_result_cannot_escape_the_boundary() -> OgeomResult<()> {
        let mut kernel = Kernel::new(1e-6)?;
        let (bad, a) = legacy_cut(&mut kernel)?;
        assert!(algo::check(&kernel.model, &bad, Tolerances::with_scale(0.1)?)?.is_valid());
        // Its topology still reaches the old Y face even though the cut surface moved.
        let top_y = explore_unique(&kernel.model, &bad, ShapeType::Vertex)?
            .iter()
            .filter_map(|v| kernel.model.node(v)?.data().as_vertex().map(|d| d.point.y))
            .fold(f64::NEG_INFINITY, f64::max);
        assert!((top_y - 0.02).abs() < 1e-12);
        assert!(kernel.bounds(&bad).is_err());
        assert!(kernel.volume(&bad, 1e-5).is_err());
        assert!(kernel.classify(&bad, [0.005, 0.019995, 0.015]).is_err());
        assert!(kernel.tessellate(&bad, 1e-5).is_err());
        assert!(kernel.validity(&bad).is_err());
        assert!(kernel.solid_count(&bad).is_err());
        assert!(kernel.subtract(&bad, &a).is_err());
        assert!(kernel.into_step(bad).is_err());
        Ok(())
    }

    #[test]
    fn step_export_refuses_tolerances_above_its_declared_uncertainty() -> OgeomResult<()> {
        let mut kernel = Kernel::new(1e-3)?;
        let (shape, _) = legacy_cut(&mut kernel)?;
        assert!(kernel.validity(&shape)?.0);
        assert!(kernel.max_entity_tolerance_mm(&shape)? > STEP_UNCERTAINTY_MM);
        assert!(matches!(
            kernel.into_step(shape),
            Err(OgeomError::Numeric(_))
        ));
        Ok(())
    }
}
