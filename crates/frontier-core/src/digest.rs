//! Content addressing: SHA-256 over a canonical JSON encoding.
//!
//! Canonical form = `serde_json::Value` re-serialized compactly. `serde_json`
//! is built without `preserve_order`, so object keys are emitted in sorted
//! order and two structurally equal values always hash identically.

use std::fmt;

use serde::{Deserialize, Deserializer, Serialize, Serializer};
use sha2::{Digest as _, Sha256};

#[derive(Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Digest([u8; 32]);

#[derive(Debug, thiserror::Error)]
pub enum DigestError {
    #[error("digest must be 64 lowercase hex characters, got {0:?}")]
    Malformed(String),
    #[error("canonical encoding failed: {0}")]
    Encoding(#[from] serde_json::Error),
}

impl Digest {
    pub const ZERO: Digest = Digest([0u8; 32]);

    pub fn of_bytes(bytes: &[u8]) -> Self {
        let out = Sha256::digest(bytes);
        let mut d = [0u8; 32];
        d.copy_from_slice(&out);
        Digest(d)
    }

    /// Hash of the canonical JSON encoding of `value`.
    pub fn of_canonical<T: Serialize + ?Sized>(value: &T) -> Result<Self, DigestError> {
        Ok(Self::of_bytes(&canonical_json(value)?))
    }

    pub fn to_hex(&self) -> String {
        const HEX: &[u8; 16] = b"0123456789abcdef";
        let mut s = String::with_capacity(64);
        for b in self.0 {
            s.push(HEX[(b >> 4) as usize] as char);
            s.push(HEX[(b & 0x0f) as usize] as char);
        }
        s
    }

    pub fn from_hex(s: &str) -> Result<Self, DigestError> {
        let bytes = s.as_bytes();
        if bytes.len() != 64 {
            return Err(DigestError::Malformed(s.to_owned()));
        }
        let nibble = |c: u8| match c {
            b'0'..=b'9' => Some(c - b'0'),
            b'a'..=b'f' => Some(c - b'a' + 10),
            _ => None,
        };
        let mut d = [0u8; 32];
        for (i, pair) in bytes.chunks(2).enumerate() {
            match (nibble(pair[0]), nibble(pair[1])) {
                (Some(h), Some(l)) => d[i] = (h << 4) | l,
                _ => return Err(DigestError::Malformed(s.to_owned())),
            }
        }
        Ok(Digest(d))
    }

    /// First 8 bytes as a little-endian integer; used to derive RNG streams.
    pub fn prefix_u64(&self) -> u64 {
        let mut b = [0u8; 8];
        b.copy_from_slice(&self.0[..8]);
        u64::from_le_bytes(b)
    }
}

pub fn canonical_json<T: Serialize + ?Sized>(value: &T) -> Result<Vec<u8>, serde_json::Error> {
    let v = serde_json::to_value(value)?;
    serde_json::to_vec(&v)
}

impl fmt::Debug for Digest {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Digest({})", &self.to_hex()[..12])
    }
}

impl fmt::Display for Digest {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.to_hex())
    }
}

impl Serialize for Digest {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_hex())
    }
}

impl<'de> Deserialize<'de> for Digest {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let s = String::deserialize(d)?;
        Digest::from_hex(&s).map_err(serde::de::Error::custom)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn known_vector() {
        assert_eq!(Digest::of_bytes(b"abc").to_hex(), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    }

    #[test]
    fn canonical_is_key_order_independent() {
        let a: serde_json::Value = serde_json::from_str(r#"{"b":1,"a":{"y":2,"x":3}}"#).unwrap();
        let b = json!({"a": {"x": 3, "y": 2}, "b": 1});
        assert_eq!(Digest::of_canonical(&a).unwrap(), Digest::of_canonical(&b).unwrap());
    }

    #[test]
    fn hex_roundtrip_and_rejection() {
        let d = Digest::of_bytes(b"x");
        assert_eq!(Digest::from_hex(&d.to_hex()).unwrap(), d);
        assert!(Digest::from_hex("ABC").is_err());
        assert!(Digest::from_hex(&d.to_hex().to_uppercase()).is_err());
    }
}
