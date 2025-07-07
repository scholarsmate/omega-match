#![allow(warnings)]

use std::str::FromStr;

#[derive(Debug)]
pub enum AppModes {
    UNDEFINED,
    COMPILE,
    MATCH,
}
pub enum AppModeErr {
    INVALID,
}

impl Default for AppModes {
    fn default() -> Self {
        Self::UNDEFINED
    }
}

impl PartialEq for AppModes {
    fn eq(&self, other: &Self) -> bool {
        self.to_string() == other.to_string()
    }
}

impl FromStr for AppModes {
    type Err = AppModes;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "compile" => Ok(Self::COMPILE),
            "match" => Ok(Self::MATCH),
            _ => Err(Self::UNDEFINED),
        }
    }
}

impl From<&str> for AppModes {
    fn from(value: &str) -> Self {
        match AppModes::from_str(value) {
            Ok(ret) => ret,
            Err(_) => Self::UNDEFINED,
        }
    }
}

impl ToString for AppModes {
    fn to_string(&self) -> String {
        match self {
            AppModes::COMPILE => String::from("compile"),
            AppModes::MATCH => String::from("match"),
            _ => String::from("undefined"),
        }
    }
}

#[cfg(test)]
mod test {
    use super::*;
    #[test]
    fn mode_from_string() {
        let inMode = "match";
        let mode = AppModes::from("match");
        assert_eq!(mode.to_string(), inMode);
    }
    #[test]
    fn mode_undefined_when_invalid() {
        let inMode = "invalid";
        let mode = AppModes::from(inMode);
        assert_eq!(mode, AppModes::UNDEFINED {});
    }

    #[test]
    fn default_mode_is_undefined() {
        let mode = AppModes::default();
        assert_eq!(mode, AppModes::UNDEFINED {});
    }
}
