//! Deterministic pseudo-random numbers (SplitMix64) with labelled substreams.
//!
//! Implemented in-tree so that replays do not depend on the stream stability
//! of an external crate across versions (see ADR-0003).

use crate::detmath;
use crate::digest::Digest;

#[derive(Clone, Debug)]
pub struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    pub fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    /// Independent stream for `label` under `seed`. The same (seed, label)
    /// always yields the same stream, regardless of what else was drawn.
    pub fn derive(seed: u64, label: &str) -> Self {
        let mut buf = Vec::with_capacity(8 + label.len());
        buf.extend_from_slice(&seed.to_le_bytes());
        buf.extend_from_slice(label.as_bytes());
        Self::new(Digest::of_bytes(&buf).prefix_u64())
    }

    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9e37_79b9_7f4a_7c15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
        z ^ (z >> 31)
    }

    /// Uniform in [0, 1).
    pub fn next_f64(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
    }

    /// Uniform integer in [0, n). `n` must be > 0.
    pub fn below(&mut self, n: u64) -> u64 {
        assert!(n > 0, "below(0)");
        // Rejection sampling removes modulo bias.
        let zone = u64::MAX - (u64::MAX % n);
        loop {
            let x = self.next_u64();
            if x < zone {
                return x % n;
            }
        }
    }

    pub fn bernoulli(&mut self, p: f64) -> bool {
        self.next_f64() < p
    }

    /// Marsaglia polar method. Uses only `detmath::ln` and `sqrt` (which
    /// IEEE-754 requires to be correctly rounded), so it is portable.
    pub fn standard_normal(&mut self) -> f64 {
        loop {
            let u = 2.0 * self.next_f64() - 1.0;
            let v = 2.0 * self.next_f64() - 1.0;
            let s = u * u + v * v;
            if s > 0.0 && s < 1.0 {
                return u * (-2.0 * detmath::ln(s) / s).sqrt();
            }
        }
    }

    pub fn lognormal(&mut self, mu: f64, sigma: f64) -> f64 {
        detmath::exp(mu + sigma * self.standard_normal())
    }

    /// Gamma(shape, 1) via Marsaglia–Tsang, with the shape < 1 boost.
    pub fn gamma(&mut self, shape: f64) -> f64 {
        assert!(shape > 0.0, "gamma shape must be positive");
        if shape < 1.0 {
            let u = 1.0 - self.next_f64();
            return self.gamma(shape + 1.0) * detmath::exp(detmath::ln(u) / shape);
        }
        let d = shape - 1.0 / 3.0;
        let c = 1.0 / (9.0 * d).sqrt();
        loop {
            let x = self.standard_normal();
            let w = 1.0 + c * x;
            let v = w * w * w;
            if v <= 0.0 {
                continue;
            }
            let u = 1.0 - self.next_f64();
            if detmath::ln(u) < 0.5 * x * x + d - d * v + d * detmath::ln(v) {
                return d * v;
            }
        }
    }

    pub fn beta(&mut self, a: f64, b: f64) -> f64 {
        let x = self.gamma(a);
        let y = self.gamma(b);
        x / (x + y)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deterministic_and_label_separated() {
        let a: Vec<u64> = (0..4)
            .map({
                let mut r = SplitMix64::derive(7, "x");
                move |_| r.next_u64()
            })
            .collect();
        let mut r = SplitMix64::derive(7, "x");
        let b: Vec<u64> = (0..4).map(|_| r.next_u64()).collect();
        assert_eq!(a, b);
        assert_ne!(SplitMix64::derive(7, "x").next_u64(), SplitMix64::derive(7, "y").next_u64());
    }

    #[test]
    fn moments_are_plausible() {
        let mut r = SplitMix64::new(42);
        let n = 20_000;
        let mean_u: f64 = (0..n).map(|_| r.next_f64()).sum::<f64>() / n as f64;
        assert!((mean_u - 0.5).abs() < 0.01);
        let mean_b: f64 = (0..n).map(|_| r.beta(2.0, 6.0)).sum::<f64>() / n as f64;
        assert!((mean_b - 0.25).abs() < 0.01, "beta mean {mean_b}");
        let mean_g: f64 = (0..n).map(|_| r.gamma(0.5)).sum::<f64>() / n as f64;
        assert!((mean_g - 0.5).abs() < 0.03, "gamma mean {mean_g}");
        for _ in 0..1000 {
            assert!(r.below(3) < 3);
        }
    }
}
