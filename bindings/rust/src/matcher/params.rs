use std::{collections::HashMap, str::FromStr};

pub struct MatchParam {
    value: usize,
}
impl MatchParam {
    pub fn get_value(&self) -> &usize {
        &self.value
    }
}
#[derive(Eq, PartialEq, Hash)]
pub enum MatchParamsType {
    IgnoreCase,
    WordBoundary,
    ElideWhitespace,
    LongestOnly,
    NoOverlap,
    WordPrefix,
    WordSuffix,
    LineStart,
    LineEnd,
    Threads,
    ChunkSize,
    OutputToFile,
}
impl FromStr for MatchParamsType {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let clean_str = s.replace("-", "");
        match clean_str.as_str() {
            "ignorecase" => Ok(MatchParamsType::IgnoreCase),
            "wordboundary" => Ok(MatchParamsType::WordBoundary),
            "elidewhitespace" => Ok(MatchParamsType::ElideWhitespace),
            "longestonly" => Ok(MatchParamsType::LongestOnly),
            "nooverlap" => Ok(MatchParamsType::NoOverlap),
            "wordprefix" => Ok(MatchParamsType::WordPrefix),
            "wordsuffix" => Ok(MatchParamsType::WordSuffix),
            "linestart" => Ok(MatchParamsType::LineStart),
            "lineend" => Ok(MatchParamsType::LineEnd),
            "threads" => Ok(MatchParamsType::Threads),
            "chunksize" => Ok(MatchParamsType::ChunkSize),
            "outputtofile" => Ok(MatchParamsType::OutputToFile),
            _ => Err(format!("{} is not a valid match modifier", s)),
        }
    }
}
pub struct MatchParams {
    set_params: HashMap<MatchParamsType, usize>,
}
impl MatchParams {
    fn new() -> Self {
        Self {
            set_params: HashMap::new(),
        }
    }
    fn from(params: HashMap<MatchParamsType, usize>) -> Self {
        Self { set_params: params }
    }
    pub fn get(&self, param_name: &str) -> usize {
        let param = MatchParamsType::from_str(param_name)
            .expect(format!("Parameter {} is invalid", param_name).as_str());
        self.set_params[&param]
    }
    pub fn len(&self) -> usize {
        self.set_params.len()
    }
}

pub struct MatchParamsBuilder {
    params: HashMap<MatchParamsType, usize>,
}
impl MatchParamsBuilder {
    pub fn new() -> Self {
        Self {
            params: HashMap::new(),
        }
    }
    pub fn set(&mut self, param_name: &str, value: usize) -> &mut Self {
        self.params
            .insert(MatchParamsType::from_str(param_name).unwrap(), value);
        self
    }
}
impl<'a, I> From<I> for MatchParamsBuilder
where
    I: Iterator<Item = &'a str>,
{
    fn from(iter: I) -> Self {
        let mut ret = Self::new();
        iter.for_each(|param_name| {
            let clean_name = param_name.replace("-", "");
            ret.set(&clean_name, 1);
        });
        return ret;
    }
}
impl Into<MatchParams> for MatchParamsBuilder {
    fn into(self) -> MatchParams {
        MatchParams {
            set_params: self.params,
        }
    }
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn param_types_init_with_value() {
        let mut builder = MatchParamsBuilder::new();
        builder.set("ignorecase", 1).set("threads", 2);
        let params: MatchParams = builder.into();
        assert_eq!(params.get("ignorecase"), 1);
        assert_eq!(params.get("threads"), 2);
    }

    #[test]
    fn can_build_from_cli_args() {
        let args = vec!["--ignore-case", "--word-boundary", "--elide-whitespace"];
        let mut builder = MatchParamsBuilder::from(args.into_iter());
        let params: MatchParams = builder.into();

        assert_eq!(params.get("ignorecase"), 1);
    }

    #[test]
    fn can_build_from_split_iter() {
        let args = vec![
            "olm",
            "match",
            "--ignore-case",
            "--word-boundary",
            "--elide-whitespace",
            "file1",
            "file2",
        ];

        let opts = args.iter().filter_map(|&s| match s.starts_with("--") {
            true => Some(s),
            false => None,
        });
        let mut builder = MatchParamsBuilder::from(opts);
        let params: MatchParams = builder.into();
        assert_eq!(params.get("ignorecase"), 1);
        assert_eq!(params.get("wordboundary"), 1);
    }
}
