//! Versioned goal expressions. Unknown evidence never proves a goal.
use serde::{Deserialize, Serialize};
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Truth {
    Yes,
    No,
    Unknown,
}
impl Truth {
    pub fn negate(self) -> Self {
        match self {
            Self::Yes => Self::No,
            Self::No => Self::Yes,
            Self::Unknown => Self::Unknown,
        }
    }
    pub fn all(items: impl IntoIterator<Item = Self>) -> Self {
        let xs: Vec<_> = items.into_iter().collect();
        if xs.contains(&Self::No) {
            Self::No
        } else if xs.contains(&Self::Unknown) {
            Self::Unknown
        } else {
            Self::Yes
        }
    }
    pub fn any(items: impl IntoIterator<Item = Self>) -> Self {
        let xs: Vec<_> = items.into_iter().collect();
        if xs.contains(&Self::Yes) {
            Self::Yes
        } else if xs.contains(&Self::Unknown) {
            Self::Unknown
        } else {
            Self::No
        }
    }
}

mod model;
pub use model::*;
mod facts;
pub use facts::*;
