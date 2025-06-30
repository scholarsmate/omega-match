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
        let inMode = "compile";
        let mode = AppModes::from_str(inMode).unwrap();
        assert_eq!(mode.to_string(), "compile");
    }
    #[test]
    fn mode_undefined_when_invalid() {
        let inMode = "invalid";
        let mode = AppModes::from_str(&inMode);
        assert!(mode.is_err());
    }
}
