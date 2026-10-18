use crate::Choice;
use serde::{Deserialize, Serialize};
#[derive(Clone, Debug, Serialize, Deserialize, Eq, PartialEq)]
pub struct CardReference {
    pub code: u32,
    pub player: u8,
    pub location: u8,
    pub sequence: u32,
    pub position: u32,
}
#[derive(Clone, Debug, Serialize, Deserialize, Eq, PartialEq)]
pub struct ActionMetadata {
    pub choice: Choice,
    pub source: Option<CardReference>,
    pub effect_description: Option<u64>,
    pub selected: Vec<CardReference>,
    pub selection_group: Option<u8>,
}
fn reference(r: &mut crate::codec::Reader<'_>, code: u32) -> Result<CardReference, String> {
    Ok(CardReference {
        code,
        player: r.u8()?,
        location: r.u8()?,
        sequence: r.u32()?,
        position: r.u32()?,
    })
}
/// A side-channel decoder: legacy events, actions and response bytes are unchanged.
pub fn prompt_metadata(id: u64, raw: &[u8]) -> Result<Vec<ActionMetadata>, String> {
    let p = crate::parse_prompt(id, raw)?.ok_or("unsupported prompt metadata")?;
    let mut out: Vec<_> = p
        .actions
        .iter()
        .map(|a| ActionMetadata {
            choice: a.choice.clone(),
            source: None,
            effect_description: None,
            selected: vec![],
            selection_group: None,
        })
        .collect();
    let mut r = crate::codec::Reader::new(raw);
    let opcode = r.u8()?;
    r.u8()?;
    match opcode {
        11 => {
            for command in 0..6 {
                for index in 0..r.count()? {
                    let code = r.u32()?;
                    let source = CardReference {
                        code,
                        player: r.u8()?,
                        location: r.u8()?,
                        sequence: r.u32()?,
                        position: 0,
                    };
                    let desc = if command == 5 {
                        let d = r.u64()?;
                        r.u8()?;
                        Some(d)
                    } else {
                        None
                    };
                    let m = out
                        .iter_mut()
                        .find(|m| {
                            m.choice
                                == crate::Choice::Command {
                                    command,
                                    index: index as u32,
                                }
                        })
                        .ok_or("metadata command mismatch")?;
                    m.source = Some(source);
                    m.effect_description = desc;
                }
            }
        }
        12 | 13 => {
            let source = if opcode == 12 {
                let code = r.u32()?;
                Some(reference(&mut r, code)?)
            } else {
                None
            };
            let desc = r.u64()?;
            for m in &mut out {
                m.source = source.clone();
                m.effect_description = Some(desc);
            }
        }
        14 => {
            let n = r.u8()?;
            for index in 0..n {
                let desc = r.u64()?;
                if let Some(m) = out.iter_mut().find(|m| {
                    m.choice
                        == crate::Choice::Option {
                            index: index as u32,
                        }
                }) {
                    m.effect_description = Some(desc);
                }
            }
        }
        15 | 26 => {
            r.u8()?;
            if opcode == 26 {
                r.u8()?;
            }
            r.u32()?;
            r.u32()?;
            let mut candidates = vec![];
            for group in 0..if opcode == 26 { 2 } else { 1 } {
                for _ in 0..r.count()? {
                    let code = r.u32()?;
                    candidates.push((reference(&mut r, code)?, group));
                }
            }
            for m in &mut out {
                match &m.choice {
                    crate::Choice::Cards { indices } => {
                        for i in indices {
                            m.selected.push(
                                candidates
                                    .get(*i as usize)
                                    .ok_or("metadata selection index")?
                                    .0
                                    .clone(),
                            );
                        }
                    }
                    crate::Choice::Toggle { index } => {
                        let (card, group) = candidates
                            .get(*index as usize)
                            .ok_or("metadata toggle index")?;
                        m.selected.push(card.clone());
                        m.selection_group = Some(*group);
                    }
                    _ => (),
                }
            }
        }
        16 => {
            r.u8()?;
            r.u8()?;
            r.u32()?;
            r.u32()?;
            for index in 0..r.count()? {
                let code = r.u32()?;
                let source = reference(&mut r, code)?;
                let desc = r.u64()?;
                r.u8()?;
                let m = out
                    .iter_mut()
                    .find(|m| {
                        m.choice
                            == crate::Choice::Chain {
                                index: Some(index as u32),
                            }
                    })
                    .ok_or("metadata chain mismatch")?;
                m.source = Some(source);
                m.effect_description = Some(desc);
            }
        }
        _ => (),
    }
    Ok(out)
}
