//! Budgets, resource usage and a reservation-based ledger.
//!
//! Compute is charged in abstract *compute units* (CU). In simulation one CU
//! is one simulated worker-second; for live workers a rate card converts
//! measured GPU-seconds, tokens and tool calls into CU and into USD. Both the
//! physical quantities and the CU charge are recorded.

use std::collections::BTreeMap;
use std::ops::AddAssign;

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Budget {
    pub compute_units: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub wall_seconds: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_attempts: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_tool_calls: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_usd: Option<f64>,
}

impl Budget {
    pub fn validate(&self) -> Result<(), String> {
        if !(self.compute_units.is_finite() && self.compute_units > 0.0) {
            return Err("compute_units must be finite and > 0".into());
        }
        if let Some(w) = self.wall_seconds {
            if !(w.is_finite() && w > 0.0) {
                return Err("wall_seconds must be finite and > 0".into());
            }
        }
        if let Some(u) = self.max_usd {
            if !(u.is_finite() && u >= 0.0) {
                return Err("max_usd must be finite and >= 0".into());
            }
        }
        Ok(())
    }
}

/// Physical resource usage of one action. All fields are additive.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Usage {
    /// Charged compute units (the budgeted quantity).
    pub compute_units: f64,
    #[serde(default)]
    pub gpu_seconds: f64,
    #[serde(default)]
    pub cpu_seconds: f64,
    #[serde(default)]
    pub input_tokens: u64,
    #[serde(default)]
    pub output_tokens: u64,
    #[serde(default)]
    pub latent_steps: u64,
    #[serde(default)]
    pub tool_calls: u64,
    #[serde(default)]
    pub usd: f64,
}

impl AddAssign<&Usage> for Usage {
    fn add_assign(&mut self, o: &Usage) {
        self.compute_units += o.compute_units;
        self.gpu_seconds += o.gpu_seconds;
        self.cpu_seconds += o.cpu_seconds;
        self.input_tokens += o.input_tokens;
        self.output_tokens += o.output_tokens;
        self.latent_steps += o.latent_steps;
        self.tool_calls += o.tool_calls;
        self.usd += o.usd;
    }
}

#[derive(Debug, PartialEq, thiserror::Error)]
pub enum LedgerError {
    #[error("insufficient budget: requested {requested}, available {available}")]
    Insufficient { requested: f64, available: f64 },
    #[error("reservation {0} already exists")]
    DuplicateReservation(u64),
    #[error("unknown reservation {0}")]
    UnknownReservation(u64),
    #[error("charge {actual} exceeds reservation {reserved} for {id}")]
    Overrun { id: u64, reserved: f64, actual: f64 },
    #[error("amount must be finite and >= 0, got {0}")]
    InvalidAmount(f64),
}

/// Hard-cap ledger. Work must reserve its worst-case charge before it starts;
/// the actual charge is settled afterwards and the remainder released.
/// Invariant: `committed + reserved <= cap` at all times.
#[derive(Clone, Debug)]
pub struct BudgetLedger {
    cap: f64,
    committed: f64,
    reservations: BTreeMap<u64, f64>,
}

impl BudgetLedger {
    pub fn new(cap: f64) -> Self {
        assert!(cap.is_finite() && cap >= 0.0, "ledger cap must be finite and >= 0");
        Self { cap, committed: 0.0, reservations: BTreeMap::new() }
    }

    pub fn cap(&self) -> f64 {
        self.cap
    }

    pub fn committed(&self) -> f64 {
        self.committed
    }

    pub fn reserved(&self) -> f64 {
        self.reservations.values().sum()
    }

    pub fn available(&self) -> f64 {
        (self.cap - self.committed - self.reserved()).max(0.0)
    }

    pub fn reserve(&mut self, id: u64, amount: f64) -> Result<(), LedgerError> {
        if !(amount.is_finite() && amount >= 0.0) {
            return Err(LedgerError::InvalidAmount(amount));
        }
        if self.reservations.contains_key(&id) {
            return Err(LedgerError::DuplicateReservation(id));
        }
        let available = self.available();
        if amount > available {
            return Err(LedgerError::Insufficient { requested: amount, available });
        }
        self.reservations.insert(id, amount);
        Ok(())
    }

    /// Convert part of a reservation into a committed charge; the rest is
    /// released. Charges above the reservation are refused, never absorbed.
    pub fn settle(&mut self, id: u64, actual: f64) -> Result<(), LedgerError> {
        if !(actual.is_finite() && actual >= 0.0) {
            return Err(LedgerError::InvalidAmount(actual));
        }
        let reserved = *self.reservations.get(&id).ok_or(LedgerError::UnknownReservation(id))?;
        if actual > reserved * (1.0 + 1e-12) {
            return Err(LedgerError::Overrun { id, reserved, actual });
        }
        self.reservations.remove(&id);
        self.committed += actual.min(reserved);
        Ok(())
    }

    pub fn release(&mut self, id: u64) -> Result<(), LedgerError> {
        self.reservations.remove(&id).map(|_| ()).ok_or(LedgerError::UnknownReservation(id))
    }

    pub fn open_reservations(&self) -> usize {
        self.reservations.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rng::SplitMix64;

    #[test]
    fn reserve_settle_release() {
        let mut l = BudgetLedger::new(10.0);
        l.reserve(1, 6.0).unwrap();
        assert_eq!(l.reserve(2, 5.0), Err(LedgerError::Insufficient { requested: 5.0, available: 4.0 }));
        assert_eq!(l.reserve(1, 1.0), Err(LedgerError::DuplicateReservation(1)));
        l.settle(1, 2.5).unwrap();
        assert_eq!(l.committed(), 2.5);
        assert_eq!(l.available(), 7.5);
        l.reserve(2, 7.5).unwrap();
        assert!(matches!(l.settle(2, 8.0), Err(LedgerError::Overrun { .. })));
        l.release(2).unwrap();
        assert_eq!(l.available(), 7.5);
        assert_eq!(l.settle(9, 0.0), Err(LedgerError::UnknownReservation(9)));
        assert!(l.reserve(3, f64::NAN).is_err());
    }

    /// Randomised operation sequences never break the hard-cap invariant.
    #[test]
    fn cap_invariant_under_random_operations() {
        for seed in 0..200 {
            let mut r = SplitMix64::new(seed);
            let cap = 1.0 + r.next_f64() * 100.0;
            let mut l = BudgetLedger::new(cap);
            let mut open: Vec<u64> = vec![];
            for id in 0..300u64 {
                match r.below(3) {
                    0 => {
                        if l.reserve(id, r.next_f64() * cap * 0.3).is_ok() {
                            open.push(id);
                        }
                    }
                    1 if !open.is_empty() => {
                        let k = open.swap_remove(r.below(open.len() as u64) as usize);
                        let reserved = l.reservations[&k];
                        // Attempt both legal and illegal settlements.
                        let actual = reserved * r.next_f64() * 1.2;
                        if l.settle(k, actual).is_err() {
                            l.release(k).unwrap();
                        }
                    }
                    _ if !open.is_empty() => {
                        let k = open.swap_remove(0);
                        l.release(k).unwrap();
                    }
                    _ => {}
                }
                assert!(l.committed() + l.reserved() <= cap * (1.0 + 1e-9), "seed {seed}");
            }
        }
    }
}
