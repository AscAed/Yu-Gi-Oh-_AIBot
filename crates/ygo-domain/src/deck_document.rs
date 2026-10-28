use crate::{CardId, Deck};
use serde::{
    de::{DeserializeSeed, MapAccess, SeqAccess, Visitor},
    Deserialize, Serialize,
};
use std::{collections::BTreeSet, fmt};

/// An editable ordered deck draft. It is not evidence that the deck is legal.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DeckDocumentV1 {
    pub schema_version: u16,
    pub kind: String,
    pub title: String,
    pub main: Vec<CardId>,
    pub extra: Vec<CardId>,
    pub side: Vec<CardId>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DeckZone {
    Main,
    Extra,
    Side,
}

impl DeckZone {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "main" => Ok(Self::Main),
            "extra" => Ok(Self::Extra),
            "side" => Ok(Self::Side),
            _ => Err(format!("unknown deck zone: {value}")),
        }
    }
}

impl DeckDocumentV1 {
    pub fn new(
        title: impl Into<String>,
        main: Vec<u32>,
        extra: Vec<u32>,
        side: Vec<u32>,
    ) -> Result<Self, String> {
        let draft = Self {
            schema_version: 1,
            kind: "deck_draft".into(),
            title: title.into(),
            main: main.into_iter().map(CardId).collect(),
            extra: extra.into_iter().map(CardId).collect(),
            side: side.into_iter().map(CardId).collect(),
        };
        draft.validate()?;
        Ok(draft)
    }

    pub fn from_deck(title: impl Into<String>, deck: Deck) -> Result<Self, String> {
        let draft = Self {
            schema_version: 1,
            kind: "deck_draft".into(),
            title: title.into(),
            main: deck.main,
            extra: deck.extra,
            side: deck.side,
        };
        draft.validate()?;
        Ok(draft)
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.schema_version != 1 || self.kind != "deck_draft" {
            return Err("unsupported deck draft schema_version or kind".into());
        }
        for (zone, cards) in [
            ("main", &self.main),
            ("extra", &self.extra),
            ("side", &self.side),
        ] {
            if cards.iter().any(|card| card.0 == 0) {
                return Err(format!("{zone} contains zero card id"));
            }
        }
        Ok(())
    }

    pub fn to_json(&self) -> Result<String, String> {
        self.validate()?;
        serde_json::to_string_pretty(self).map_err(|error| error.to_string())
    }

    pub fn from_json(text: &str) -> Result<Self, String> {
        let draft: Self = serde_json::from_str(text).map_err(|error| {
            format!(
                "JSON line {} column {}: {error}",
                error.line(),
                error.column()
            )
        })?;
        draft.validate()?;
        Ok(draft)
    }

    /// Import either this versioned draft or the legacy bare Deck object.
    pub fn import_json(text: &str) -> Result<Self, String> {
        validate_unique_json_keys(text)?;
        let value: serde_json::Value = serde_json::from_str(text).map_err(|error| {
            format!(
                "JSON line {} column {}: {error}",
                error.line(),
                error.column()
            )
        })?;
        let object = value.as_object().ok_or("JSON deck must be an object")?;
        if ["schema_version", "kind", "title"]
            .iter()
            .any(|key| object.contains_key(*key))
        {
            return Self::from_json(text);
        }
        #[derive(Deserialize)]
        #[serde(deny_unknown_fields)]
        struct LegacyDeck {
            main: Vec<CardId>,
            extra: Vec<CardId>,
            side: Vec<CardId>,
        }
        let deck: LegacyDeck = serde_json::from_value(value).map_err(|error| error.to_string())?;
        Self::from_deck("Imported deck", Deck::new(deck.main, deck.extra, deck.side))
    }

    pub fn from_ydk(text: &str) -> Result<Self, String> {
        let mut main = Vec::new();
        let mut extra = Vec::new();
        let mut side = Vec::new();
        let mut zone = None;
        for (index, raw) in text.trim_start_matches('\u{feff}').lines().enumerate() {
            let line_number = index + 1;
            let line = raw.trim();
            if line.is_empty() {
                continue;
            }
            match line {
                "#main" => zone = Some(DeckZone::Main),
                "#extra" => zone = Some(DeckZone::Extra),
                "!side" => zone = Some(DeckZone::Side),
                value if value.starts_with('#') => continue,
                value if value.starts_with('!') => {
                    return Err(format!(
                        "YDK line {line_number}: unsupported section {value}"
                    ));
                }
                value => {
                    let card = value
                        .parse::<u32>()
                        .map_err(|_| format!("YDK line {line_number}: invalid card id {value}"))?;
                    if card == 0 {
                        return Err(format!("YDK line {line_number}: card id must be nonzero"));
                    }
                    match zone {
                        Some(DeckZone::Main) => main.push(CardId(card)),
                        Some(DeckZone::Extra) => extra.push(CardId(card)),
                        Some(DeckZone::Side) => side.push(CardId(card)),
                        None => return Err(format!("YDK line {line_number}: section missing")),
                    }
                }
            }
        }
        Ok(Self {
            schema_version: 1,
            kind: "deck_draft".into(),
            title: "Imported YDK deck".into(),
            main,
            extra,
            side,
        })
    }

    pub fn to_ydk(&self) -> String {
        let mut output = String::from("#created by ygo deck draft\n#main\n");
        for card in &self.main {
            output.push_str(&format!("{}\n", card.0));
        }
        output.push_str("#extra\n");
        for card in &self.extra {
            output.push_str(&format!("{}\n", card.0));
        }
        output.push_str("!side\n");
        for card in &self.side {
            output.push_str(&format!("{}\n", card.0));
        }
        output
    }

    pub fn edit(
        &mut self,
        zone: DeckZone,
        operation: &str,
        card: u32,
        count: usize,
    ) -> Result<(), String> {
        self.validate()?;
        if card == 0 || count == 0 {
            return Err("card and count must be positive".into());
        }
        let cards = match zone {
            DeckZone::Main => &mut self.main,
            DeckZone::Extra => &mut self.extra,
            DeckZone::Side => &mut self.side,
        };
        match operation {
            "add" => cards.extend(std::iter::repeat(CardId(card)).take(count)),
            "remove" => {
                if cards.iter().filter(|entry| entry.0 == card).count() < count {
                    return Err(format!(
                        "{} has fewer than {count} copies of {card}",
                        zone.name()
                    ));
                }
                for _ in 0..count {
                    let index = cards.iter().position(|entry| entry.0 == card).unwrap();
                    cards.remove(index);
                }
            }
            _ => return Err(format!("unknown deck operation: {operation}")),
        }
        Ok(())
    }
}

fn validate_unique_json_keys(text: &str) -> Result<(), String> {
    struct UniqueValue;
    impl<'de> DeserializeSeed<'de> for UniqueValue {
        type Value = ();
        fn deserialize<D: serde::Deserializer<'de>>(self, deserializer: D) -> Result<(), D::Error> {
            deserializer.deserialize_any(UniqueVisitor)
        }
    }
    struct UniqueVisitor;
    impl<'de> Visitor<'de> for UniqueVisitor {
        type Value = ();
        fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
            formatter.write_str("a JSON value without duplicate object keys")
        }
        fn visit_bool<E: serde::de::Error>(self, _: bool) -> Result<(), E> {
            Ok(())
        }
        fn visit_i64<E: serde::de::Error>(self, _: i64) -> Result<(), E> {
            Ok(())
        }
        fn visit_u64<E: serde::de::Error>(self, _: u64) -> Result<(), E> {
            Ok(())
        }
        fn visit_f64<E: serde::de::Error>(self, _: f64) -> Result<(), E> {
            Ok(())
        }
        fn visit_str<E: serde::de::Error>(self, _: &str) -> Result<(), E> {
            Ok(())
        }
        fn visit_string<E: serde::de::Error>(self, _: String) -> Result<(), E> {
            Ok(())
        }
        fn visit_unit<E: serde::de::Error>(self) -> Result<(), E> {
            Ok(())
        }
        fn visit_none<E: serde::de::Error>(self) -> Result<(), E> {
            Ok(())
        }
        fn visit_some<D: serde::Deserializer<'de>>(self, deserializer: D) -> Result<(), D::Error> {
            UniqueValue.deserialize(deserializer)
        }
        fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<(), A::Error> {
            while seq.next_element_seed(UniqueValue)?.is_some() {}
            Ok(())
        }
        fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<(), A::Error> {
            let mut keys = BTreeSet::new();
            while let Some(key) = map.next_key::<String>()? {
                if !keys.insert(key.clone()) {
                    return Err(serde::de::Error::custom(format!(
                        "duplicate JSON key {key}"
                    )));
                }
                map.next_value_seed(UniqueValue)?;
            }
            Ok(())
        }
    }
    let mut deserializer = serde_json::Deserializer::from_str(text);
    UniqueValue
        .deserialize(&mut deserializer)
        .map_err(|error| {
            format!(
                "JSON line {} column {}: {error}",
                error.line(),
                error.column()
            )
        })?;
    deserializer.end().map_err(|error| {
        format!(
            "JSON line {} column {}: {error}",
            error.line(),
            error.column()
        )
    })
}

impl DeckZone {
    fn name(self) -> &'static str {
        match self {
            Self::Main => "main",
            Self::Extra => "extra",
            Self::Side => "side",
        }
    }
}
