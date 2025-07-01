#![allow(warnings)]
mod cli;
mod opts;
use rolm::config::modes::AppModes;
use std::str::FromStr;

use crate::{cli::validate_args, opts::CLIOptions};

fn main() -> Result<(), String> {
    let ver = rolm::version();
    println!("Version {}", ver);

    let cli_args: Vec<String> = std::env::args().collect();
    validate_args(&cli_args);
    let mode = cli::get_app_mode_arg(&cli_args[1])?;

    let mut arg_pos: usize = 3;

    let match_options = cli::extract_match_options(&cli_args)?;
    arg_pos = arg_pos + match_options.len();

    let matchFile = cli::extract_match_file(&cli_args, &arg_pos)?;
    let matchConfig = cli::extract_config_file(&cli_args, &arg_pos)?;

    rolm::matcher::enable_modifier("verbose");
    match mode {
        AppModes::MATCH => {
            let mut olm_matcher =
                rolm::matcher::Matcher::new(&matchConfig, &matchFile, match_options);

            CLIOptions::if_set_then(CLIOptions::Verbose, || olm_matcher.emit_header_info());

            let mut haystack_size: usize = 0;
            olm_matcher.execute(&mut haystack_size);
        }
        AppModes::COMPILE => {
            println!("Compile exec")
        }
        AppModes::UNDEFINED => panic!("Cannot execute w/ undefined mode"),
    }

    Ok(())
}
