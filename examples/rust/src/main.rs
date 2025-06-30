use std::{error::Error, rc::Rc, str::FromStr};

use rolm::ProgramArgs;

fn get_app_mode_arg(arg: &str) -> rolm::config::modes::AppModes {
    match rolm::config::modes::AppModes::from_str(&arg) {
        Ok(mode) => mode,
        Err(mode) => mode,
    }
}

fn main() -> Result<(), &'static str> {
    let ver = rolm::version();
    println!("Version {}", ver);

    let mut argPos = 0;

    let cli_args: Vec<String> = std::env::args().collect();
    if cli_args.len() < 2 {
        return Err("Invalid arg count");
    }
    let mode = get_app_mode_arg(&cli_args[1]);
    let mut prog = ProgramArgs::new(mode);

    argPos = argPos + 2;

    println!("App Mode: {}", &prog.app_mode.to_string());

    if cli_args.len() > 2 {
        cli_args.iter().for_each(|arg_str| {
            if arg_str.starts_with("--") {
                argPos = argPos + 1;
                match rolm::config::modifiers::ModifierParser::get(&arg_str) {
                    Ok(modifier) => prog.add_modifiers(modifier),
                    Err(e) => panic!("{}", e),
                }
            }
        });
    }

    if cli_args.len() - argPos != 2 {
        return Err("No filepaths detected in arguments");
    }
    let match_file_idx = cli_args.len() - 1;
    let match_config_idx = cli_args.len() - 2;
    let matchFile = std::path::Path::new(&cli_args[match_file_idx]);
    let matchConfig = std::path::Path::new(&cli_args[match_config_idx]);

    println!("Config filepath: {:?}", matchConfig);
    println!("Match-file filepath: {:?}", matchFile);

    let match_ptr = rolm::create_matcher(&matchConfig).expect("Couldn't create matcher");

    rolm::match_compile_patterns(&matchConfig, &matchFile, &prog).expect("comp failed");
    // let mode = rolm::dispatch::OmegaAppMode::MODE_UNDEFINED;

    /*
        olm
            match
                --no-overlap
                --word-boundary
                --longest
            ../../data/names.txt
            ../../data/kjv.txt
    */

    // rolm::execute(match, [<opts>], <arg1>, <arg2>)
    Ok(())
}
