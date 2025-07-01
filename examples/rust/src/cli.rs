use std::str::FromStr;
pub fn validate_args(args: &Vec<String>) -> Result<(), &'static str> {
    if args.len() < 2 {
        return Err("Invalid arg count");
    }
    Ok(())
}

pub fn get_app_mode_arg(arg: &str) -> Result<rolm::config::modes::AppModes, String> {
    match rolm::config::modes::AppModes::from_str(arg) {
        Ok(mode) => Ok(mode),
        Err(mode) => Err(format!("Could not parse mode type {}", mode.to_string())),
    }
}

pub fn extract_match_options(
    args: &Vec<String>,
) -> Result<rolm::matcher::params::MatchParams, &'static str> {
    if args.len() > 2 {
        let opts = args
            .iter()
            .filter_map(|s| match rolm::matcher::is_match_option(s.as_str()) {
                true => Some(s.as_str()),
                false => None,
            });
        let match_params = rolm::matcher::get_options(opts);
        return Ok(match_params);
    }
    Err("Could not parse into match options")
}

pub fn extract_match_file(
    args: &Vec<String>,
    arg_pos: &usize,
) -> Result<std::path::PathBuf, String> {
    if args.len() - arg_pos != 2 {
        return Err("no match file found".to_string());
    }

    let match_file_idx = args.len() - 1;
    Ok(std::path::PathBuf::from(&args[match_file_idx]))
}

pub fn extract_config_file(
    args: &Vec<String>,
    arg_pos: &usize,
) -> Result<std::path::PathBuf, String> {
    if args.len() - arg_pos != 2 {
        return Err("no config file found".to_string());
    }

    let match_file_idx = args.len() - 2;
    Ok(std::path::PathBuf::from(&args[match_file_idx]))
}
