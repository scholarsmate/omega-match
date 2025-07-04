use super::params;
use std::{
    cell::Cell,
    str::FromStr,
    sync::atomic::{AtomicBool, Ordering},
};

pub(crate) struct ModifierTable {
    flags: [AtomicBool; MatchModifiers::COUNT],
}
impl ModifierTable {
    const fn new() -> Self {
        Self {
            flags: [
                AtomicBool::new(false),
                AtomicBool::new(false),
                AtomicBool::new(false),
            ],
        }
    }
    pub fn enable(&self, modifier: MatchModifiers) {
        self.flags[modifier as usize].store(true, Ordering::Relaxed);
    }
    pub fn is_enabled(&self, modifier: MatchModifiers) -> bool {
        return self.flags[modifier as usize].load(Ordering::Relaxed);
    }
}
pub(crate) static ENABLED_MODIFIERS: ModifierTable = ModifierTable::new();

impl Default for ModifierTable {
    fn default() -> Self {
        Self::new()
    }
}
pub enum MatchModifiers {
    Verbose,
}
impl MatchModifiers {
    const COUNT: usize = 3;
}
impl FromStr for MatchModifiers {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let clean_str = s.replace("-", "");
        match clean_str.as_str() {
            "v" | "verbose" => Ok(MatchModifiers::Verbose),
            _ => Err(format!("{} is not a valid match modifier", s)),
        }
    }
}

#[cfg(test)]
mod test {

    use super::*;
}
