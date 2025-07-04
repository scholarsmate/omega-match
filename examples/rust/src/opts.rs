use std::{
    collections::HashMap,
    str::FromStr,
    sync::atomic::{AtomicBool, Ordering},
};
#[derive(Clone, Copy)]
pub enum CLIOptions {
    Verbose,
}
impl CLIOptions {
    pub fn set(opt: CLIOptions) {
        SET_OPTS[opt as usize].store(true, Ordering::Relaxed);
        println!("Opt set? {:?}", SET_OPTS[opt as usize]);
    }
    pub fn is_set(opt: CLIOptions) -> bool {
        println!("Opt set? {:?}", SET_OPTS[opt as usize]);
        SET_OPTS[opt as usize].load(Ordering::Relaxed)
    }
    pub fn if_set_then<F>(opt: CLIOptions, op: F)
    where
        F: FnOnce(),
    {
        match SET_OPTS[opt as usize].load(Ordering::Relaxed) {
            true => {
                op();
            }
            false => {
                println!("Option {} is not set", opt.to_string())
            }
        }
    }
}
impl ToString for CLIOptions {
    fn to_string(&self) -> String {
        match self {
            CLIOptions::Verbose => "Verbose".to_string(),
        }
    }
}
pub struct CLIOptionCommands;
static OPT_COUNT: usize = 1;
static SET_OPTS: [AtomicBool; 1] = [AtomicBool::new(false)];

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn cli_opts_interface_through_enum() {
        CLIOptions::set(CLIOptions::Verbose);
        assert_eq!(CLIOptions::is_set(CLIOptions::Verbose), true)
    }
}
