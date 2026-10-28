use std::{collections::BTreeMap, fs, path::PathBuf};
use ygo_domain::{Catalog, DeckDocumentV1, DeckZone};
use ygo_storage::publish_deck_document;

fn arguments(args: &[String]) -> Result<(&str, BTreeMap<String, String>, bool), String> {
    let command = args
        .first()
        .map(String::as_str)
        .ok_or("missing deck draft action")?;
    if !matches!(command, "create" | "show" | "edit" | "import" | "export") {
        return Err(format!("unknown deck draft action: {command}"));
    }
    let mut values = BTreeMap::new();
    let mut replace = false;
    let mut index = 1;
    while index < args.len() {
        let key = &args[index];
        if key == "--replace" {
            if replace {
                return Err("duplicate flag --replace".into());
            }
            replace = true;
            index += 1;
            continue;
        }
        if !key.starts_with("--") || index + 1 >= args.len() || args[index + 1].starts_with("--") {
            return Err(format!("flag {key} requires a value"));
        }
        if values
            .insert(key.clone(), args[index + 1].clone())
            .is_some()
        {
            return Err(format!("duplicate flag {key}"));
        }
        index += 2;
    }
    let allowed: &[&str] = match command {
        "create" => &["--output", "--title"],
        "show" => &["--input", "--store", "--catalog-id"],
        "edit" => &[
            "--input",
            "--output",
            "--zone",
            "--operation",
            "--card",
            "--count",
        ],
        "import" => &["--input", "--output", "--format", "--title"],
        "export" => &["--input", "--output", "--format"],
        _ => unreachable!(),
    };
    if replace && !matches!(command, "create" | "edit" | "import" | "export") {
        return Err("--replace is only valid when writing a draft or export".into());
    }
    for key in values.keys() {
        if !allowed.contains(&key.as_str()) {
            return Err(format!("unknown flag {key}"));
        }
    }
    Ok((command, values, replace))
}

fn required<'a>(values: &'a BTreeMap<String, String>, key: &str) -> Result<&'a str, String> {
    values
        .get(key)
        .map(String::as_str)
        .ok_or_else(|| format!("missing {key}"))
}

fn read_json(path: &str) -> Result<DeckDocumentV1, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{path}: {error}"))?;
    DeckDocumentV1::import_json(&text).map_err(|error| format!("{path}: {error}"))
}

fn format(values: &BTreeMap<String, String>) -> Result<&str, String> {
    match required(values, "--format")? {
        "json" => Ok("json"),
        "ydk" => Ok("ydk"),
        value => Err(format!("unsupported deck format: {value}")),
    }
}

fn card_check(draft: &DeckDocumentV1, catalog: Option<(&str, &Catalog)>) -> serde_json::Value {
    if let Some((catalog_id, cards)) = catalog {
        let mut unknown = Vec::new();
        for id in draft.main.iter().chain(&draft.extra).chain(&draft.side) {
            if !cards.contains_key(id) && !unknown.contains(&id.0) {
                unknown.push(id.0);
            }
        }
        serde_json::json!({"status":"checked","catalog_id":catalog_id,"unknown_card_ids":unknown})
    } else {
        serde_json::json!({"status":"unverified","reason":"no local catalog was selected"})
    }
}

pub(super) fn execute(args: &[String]) -> Result<(), String> {
    let (command, values, replace) = arguments(args)?;
    match command {
        "create" => {
            let draft = DeckDocumentV1::new(
                values
                    .get("--title")
                    .cloned()
                    .unwrap_or_else(|| "Untitled deck".into()),
                vec![],
                vec![],
                vec![],
            )?;
            publish_deck_document(
                required(&values, "--output")?,
                draft.to_json()?.as_bytes(),
                replace,
            )
        }
        "show" => {
            let draft = read_json(required(&values, "--input")?)?;
            let card_check = if let Some(catalog_id) = values.get("--catalog-id") {
                let store = ygo_storage::SnapshotStore::new(
                    values
                        .get("--store")
                        .map(PathBuf::from)
                        .or_else(|| std::env::var_os("YGO_SNAPSHOT_STORE").map(PathBuf::from))
                        .unwrap_or_else(|| "data/snapshots".into()),
                );
                let catalog = store.catalog(catalog_id)?;
                card_check(&draft, Some((&catalog.id, &catalog.data)))
            } else {
                card_check(&draft, None)
            };
            println!(
                "{}",
                serde_json::to_string_pretty(&serde_json::json!({
                    "draft":draft,
                    "legality":"not_checked",
                    "card_check":card_check
                }))
                .map_err(|error| error.to_string())?
            );
            Ok(())
        }
        "edit" => {
            let mut draft = read_json(required(&values, "--input")?)?;
            let zone = DeckZone::parse(required(&values, "--zone")?)?;
            let card = required(&values, "--card")?
                .parse::<u32>()
                .map_err(|_| "--card must be a nonzero u32")?;
            let count = required(&values, "--count")?
                .parse::<usize>()
                .map_err(|_| "--count must be a positive integer")?;
            draft
                .edit(zone, required(&values, "--operation")?, card, count)
                .map_err(|error| format!("{}: {error}", values["--input"]))?;
            publish_deck_document(
                required(&values, "--output")?,
                draft.to_json()?.as_bytes(),
                replace,
            )
        }
        "import" => {
            let input = required(&values, "--input")?;
            let draft = match format(&values)? {
                "json" => {
                    let text =
                        fs::read_to_string(input).map_err(|error| format!("{input}: {error}"))?;
                    let mut draft = DeckDocumentV1::import_json(&text)
                        .map_err(|error| format!("{input}: {error}"))?;
                    if let Some(title) = values.get("--title") {
                        draft.title = title.clone();
                    }
                    draft
                }
                "ydk" => {
                    let text =
                        fs::read_to_string(input).map_err(|error| format!("{input}: {error}"))?;
                    let mut draft = DeckDocumentV1::from_ydk(&text)
                        .map_err(|error| format!("{input}: {error}"))?;
                    if let Some(title) = values.get("--title") {
                        draft.title = title.clone();
                    }
                    draft
                }
                _ => unreachable!(),
            };
            publish_deck_document(
                required(&values, "--output")?,
                draft.to_json()?.as_bytes(),
                replace,
            )
        }
        "export" => {
            let draft = read_json(required(&values, "--input")?)?;
            let bytes = match format(&values)? {
                "json" => draft.to_json()?,
                "ydk" => draft.to_ydk(),
                _ => unreachable!(),
            };
            publish_deck_document(
                PathBuf::from(required(&values, "--output")?).as_path(),
                bytes.as_bytes(),
                replace,
            )
        }
        _ => unreachable!(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ygo_domain::{Card, CardId, CardKind};

    #[test]
    fn unknown_card_ids_are_preserved_and_reported_only_when_catalog_is_selected() {
        let draft = DeckDocumentV1::new("partial", vec![7, 999, 999], vec![], vec![]).unwrap();
        assert_eq!(card_check(&draft, None)["status"], "unverified");
        let catalog = Catalog::from([(
            CardId(7),
            Card {
                id: CardId(7),
                name: "known".into(),
                kind: CardKind::Monster,
                ..Default::default()
            },
        )]);
        let report = card_check(&draft, Some(("local-test", &catalog)));
        assert_eq!(report["status"], "checked");
        assert_eq!(report["unknown_card_ids"], serde_json::json!([999]));
        assert_eq!(draft.main, vec![CardId(7), CardId(999), CardId(999)]);
    }
}
