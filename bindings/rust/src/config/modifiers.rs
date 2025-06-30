use std::{str::FromStr, vec};

pub enum ProgramModifier {
    Verbose(VerboseModifier),
    IgnoreCase,
    WordBoundary,
}

pub struct VerboseModifier;
pub struct IgnoreCaseModifier;
pub struct WordBoundaryModifier;
impl VerboseModifier {
    const KEYS: [&str; 2] = ["-h", "--verbose"];
    pub fn is_key(key: &str) -> bool {
        match key {
            "-v" | "--verbose" => true,
            _ => false,
        }
    }
}
impl IgnoreCaseModifier {
    const KEYS: &str = "--ignore-case";
    pub fn is_key(key: &str) -> bool {
        match key {
            "-v" | "--verbose" => true,
            _ => false,
        }
    }
}
impl WordBoundaryModifier {
    const KEYS: &str = "--word-boundary";
    pub fn is_key(key: &str) -> bool {
        match key {
            "-v" | "--verbose" => true,
            _ => false,
        }
    }
}
pub trait IsModifier {
    fn id(&self) -> &'static str;
}

impl IsModifier for VerboseModifier {
    fn id(&self) -> &'static str {
        "verbose"
    }
}
impl IsModifier for IgnoreCaseModifier {
    fn id(&self) -> &'static str {
        "ignore-case"
    }
}
impl IsModifier for WordBoundaryModifier {
    fn id(&self) -> &'static str {
        "word-boundary"
    }
}

pub struct ModifierParser;
impl ModifierParser {
    pub fn get(s: &str) -> Result<Box<dyn IsModifier>, String> {
        match s {
            "-v" | "--verbose" => Ok(Box::new(VerboseModifier {})),
            "--ignore-case" => Ok(Box::new(IgnoreCaseModifier {})),
            "--word-boundary" => Ok(Box::new(WordBoundaryModifier {})),
            _ => Err(format!("Key: {} is not a modifier option", s)),
        }
    }
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn can_resolve_modifer_string() {
        let mut modStr = "-v";
        let modifer: Box<dyn IsModifier> = ModifierParser::get(&modStr).unwrap();
        assert_eq!(modifer.id(), "verbose");
    }

    #[test]
    fn can_resolve_multiple_modifiers() {
        let modStrs: Vec<&str> = vec!["-v", "--ignore-case"];

        let strs: Vec<Box<dyn IsModifier>> = modStrs
            .into_iter()
            .map(|id| match ModifierParser::get(id) {
                Ok(ret) => ret,
                Err(e) => panic!("{}", e),
            })
            .collect();
        let mut modifiers: Vec<Box<dyn IsModifier>>;

        assert_eq!(strs.len(), 2);
    }

    #[test]
    fn errors_on_invalid_modifier_parse() {
        let modStrs: Vec<&str> = vec!["-v", "--invalid"];
        let mut errOccured = false;

        let mut mods: Vec<Box<dyn IsModifier>> = Vec::new();
        for modStr in modStrs {
            match ModifierParser::get(&modStr) {
                Ok(modifier) => mods.push(modifier),
                Err(e) => {
                    println!("{}", e);
                    errOccured = true
                }
            }
        }
        assert!(errOccured);
    }
}
