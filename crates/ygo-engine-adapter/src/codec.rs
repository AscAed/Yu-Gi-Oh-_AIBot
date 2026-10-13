use crate::*;
use serde_json::json;

pub(crate) struct Reader<'a> {
    pub data: &'a [u8],
    pub pos: usize,
}
impl<'a> Reader<'a> {
    pub fn new(data: &'a [u8]) -> Self {
        Self { data, pos: 0 }
    }
    pub fn take(&mut self, n: usize) -> Result<&'a [u8], String> {
        let end = self.pos.checked_add(n).ok_or("length overflow")?;
        let bytes = self.data.get(self.pos..end).ok_or("truncated message")?;
        self.pos = end;
        Ok(bytes)
    }
    pub fn u8(&mut self) -> Result<u8, String> {
        Ok(self.take(1)?[0])
    }
    pub fn u16(&mut self) -> Result<u16, String> {
        Ok(u16::from_le_bytes(self.take(2)?.try_into().unwrap()))
    }
    pub fn u32(&mut self) -> Result<u32, String> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    pub fn u64(&mut self) -> Result<u64, String> {
        Ok(u64::from_le_bytes(self.take(8)?.try_into().unwrap()))
    }
    pub fn count(&mut self) -> Result<usize, String> {
        let n = self.u32()? as usize;
        if n > 4096 {
            return Err("message count exceeds limit".into());
        }
        Ok(n)
    }
    pub fn loc(&mut self) -> Result<serde_json::Value, String> {
        Ok(
            json!({"player":self.u8()?,"location":self.u8()?,"sequence":self.u32()?,"position":self.u32()?}),
        )
    }
    pub fn end(&self) -> Result<(), String> {
        if self.pos != self.data.len() {
            Err("unexpected message tail".into())
        } else {
            Ok(())
        }
    }
}
pub fn split_frames(raw: &[u8]) -> Result<Vec<&[u8]>, String> {
    let mut r = Reader::new(raw);
    let mut out = Vec::new();
    while r.pos < raw.len() {
        let n = r.u32()? as usize;
        if n == 0 || n > 16 * 1024 * 1024 {
            return Err("invalid frame length".into());
        }
        out.push(r.take(n)?);
    }
    Ok(out)
}
fn words(values: &[u32]) -> Vec<u8> {
    values.iter().flat_map(|n| n.to_le_bytes()).collect()
}
fn add(p: &mut Prompt, choice: Choice, label: String, cards: Vec<u32>, bytes: Vec<u8>) {
    p.actions.push(Action {
        choice,
        label,
        card_ids: cards,
        bytes,
    });
}
fn combinations(
    n: usize,
    k: usize,
    offset: usize,
    current: &mut Vec<u32>,
    out: &mut Vec<Vec<u32>>,
) -> Result<(), String> {
    if out.len() > 4096 {
        return Err("choice combinations exceed supported limit".into());
    }
    if current.len() == k {
        out.push(current.clone());
        return Ok(());
    }
    let needed = k - current.len();
    if n.saturating_sub(offset) < needed {
        return Ok(());
    }
    for i in offset..=n - needed {
        current.push(i as u32);
        combinations(n, k, i + 1, current, out)?;
        current.pop();
    }
    Ok(())
}
pub fn parse_prompt(id: u64, raw: &[u8]) -> Result<Option<Prompt>, String> {
    let mut r = Reader::new(raw);
    let opcode = r.u8()?;
    if !matches!(opcode, 11..=16 | 18 | 19 | 24 | 26) {
        return Ok(None);
    }
    let player = r.u8()?;
    if player > 1 {
        return Err("invalid prompt player".into());
    }
    let mut p = Prompt {
        id,
        player,
        opcode,
        actions: vec![],
    };
    match opcode {
        11 => {
            for command in 0..6 {
                for index in 0..r.count()? {
                    let code = r.u32()?;
                    let owner = r.u8()?;
                    let zone = r.u8()?;
                    let seq = r.u32()?;
                    if command == 5 {
                        r.u64()?;
                        r.u8()?;
                    }
                    let label = format!(
                        "{} card {code} [{owner}:{zone}:{seq}]",
                        [
                            "召唤",
                            "特殊召唤",
                            "改变表示",
                            "盖放怪兽",
                            "盖放魔陷",
                            "发动"
                        ][command as usize]
                    );
                    add(
                        &mut p,
                        Choice::Command {
                            command,
                            index: index as u32,
                        },
                        label,
                        vec![code],
                        words(&[((index as u32) << 16) | command as u32]),
                    );
                }
            }
            let _battle = r.u8()?;
            let end = r.u8()?;
            r.u8()?;
            if end != 0 {
                add(
                    &mut p,
                    Choice::Command {
                        command: 7,
                        index: 0,
                    },
                    "结束回合".into(),
                    vec![],
                    words(&[7]),
                );
            }
        }
        12 | 13 => {
            let mut codes = vec![];
            if opcode == 12 {
                codes.push(r.u32()?);
                r.loc()?;
            }
            r.u64()?;
            for yes in [false, true] {
                add(
                    &mut p,
                    Choice::YesNo { yes },
                    format!("选择 {yes}"),
                    codes.clone(),
                    words(&[yes as u32]),
                );
            }
        }
        14 => {
            let n = r.u8()?;
            for index in 0..n {
                let desc = r.u64()?;
                add(
                    &mut p,
                    Choice::Option {
                        index: index as u32,
                    },
                    format!("选项 {desc}"),
                    vec![],
                    words(&[index as u32]),
                );
            }
        }
        15 => {
            let cancel = r.u8()? != 0;
            let min = r.count()?;
            let max = r.count()?;
            let n = r.count()?;
            if min > max || max > n {
                return Err("invalid selection bounds".into());
            }
            let mut codes = vec![];
            for _ in 0..n {
                codes.push(r.u32()?);
                r.loc()?;
            }
            let mut selections = vec![];
            for k in min..=max {
                combinations(n, k, 0, &mut vec![], &mut selections)?;
            }
            for indices in selections {
                let cards = indices
                    .iter()
                    .map(|i| codes[*i as usize])
                    .collect::<Vec<_>>();
                let mut response = vec![0, indices.len() as u32];
                response.extend(&indices);
                add(
                    &mut p,
                    Choice::Cards { indices },
                    format!("选择卡片 {cards:?}"),
                    cards,
                    words(&response),
                );
            }
            if cancel {
                add(
                    &mut p,
                    Choice::Finish,
                    "取消选择".into(),
                    vec![],
                    words(&[u32::MAX]),
                );
            }
        }
        26 => {
            let finish = r.u8()? != 0;
            let cancel = r.u8()? != 0;
            r.u32()?;
            r.u32()?;
            let mut codes = vec![];
            for _ in 0..2 {
                for _ in 0..r.count()? {
                    codes.push(r.u32()?);
                    r.loc()?;
                }
            }
            for (index, code) in codes.into_iter().enumerate() {
                add(
                    &mut p,
                    Choice::Toggle {
                        index: index as u32,
                    },
                    format!("素材/选择 {code} #{index}"),
                    vec![code],
                    words(&[1, index as u32]),
                );
            }
            if finish || cancel {
                add(
                    &mut p,
                    Choice::Finish,
                    "完成/取消素材选择".into(),
                    vec![],
                    words(&[u32::MAX]),
                );
            }
        }
        16 => {
            r.u8()?;
            let forced = r.u8()? != 0;
            r.u32()?;
            r.u32()?;
            for index in 0..r.count()? {
                let code = r.u32()?;
                r.loc()?;
                let desc = r.u64()?;
                r.u8()?;
                add(
                    &mut p,
                    Choice::Chain {
                        index: Some(index as u32),
                    },
                    format!("连锁 {code} 效果 {desc}"),
                    vec![code],
                    words(&[index as u32]),
                );
            }
            if !forced {
                add(
                    &mut p,
                    Choice::Chain { index: None },
                    "不响应".into(),
                    vec![],
                    words(&[u32::MAX]),
                );
            }
        }
        18 | 24 => {
            let n = r.u8()? as usize;
            let mask = r.u32()?;
            let mut zones = vec![];
            for relative in 0..2 {
                for location in [4, 8] {
                    for sequence in 0..if location == 4 { 7 } else { 8 } {
                        let bit = sequence + if location == 8 { 8 } else { 0 } + relative * 16;
                        if mask & (1u32 << bit) == 0 {
                            zones.push(Zone {
                                player: if relative == 0 { player } else { 1 - player },
                                location,
                                sequence: sequence as u8,
                            });
                        }
                    }
                }
            }
            let mut sets = vec![];
            combinations(zones.len(), n, 0, &mut vec![], &mut sets)?;
            for set in sets {
                let chosen = set
                    .iter()
                    .map(|i| zones[*i as usize].clone())
                    .collect::<Vec<_>>();
                let bytes = chosen
                    .iter()
                    .flat_map(|z| [z.player, z.location, z.sequence])
                    .collect();
                add(
                    &mut p,
                    Choice::Place {
                        zones: chosen.clone(),
                    },
                    format!("选择区域 {chosen:?}"),
                    vec![],
                    bytes,
                );
            }
        }
        19 => {
            let code = r.u32()?;
            let mask = r.u8()?;
            for position in [1, 2, 4, 8] {
                if mask & position != 0 {
                    add(
                        &mut p,
                        Choice::Position {
                            position: position as u32,
                        },
                        format!("表示形式 {position}"),
                        vec![code],
                        words(&[position as u32]),
                    );
                }
            }
        }
        _ => unreachable!(),
    }
    r.end()?;
    if p.actions.is_empty() {
        return Err("prompt has no supported choices".into());
    }
    Ok(Some(p))
}
pub fn decode_frame(sequence: u64, raw: &[u8]) -> Result<CoreEventFrame, String> {
    let mut r = Reader::new(raw);
    let opcode = r.u8()?;
    let (supported, fields) = match opcode {
        160 => (
            true,
            json!({"location":r.loc()?,"hint_type":r.u8()?,"value":r.u64()?}),
        ),
        31 => {
            let player = r.u8()?;
            if player > 1 {
                return Err("invalid confirmation player".into());
            }
            let mut cards = vec![];
            for _ in 0..r.count()? {
                cards.push(json!({"code":r.u32()?,"player":r.u8()?,"location":r.u8()?,"sequence":r.u32()?}));
            }
            (true, json!({"player":player,"cards":cards}))
        }
        2 => (
            true,
            json!({"hint_type":r.u8()?,"player":r.u8()?,"value":r.u64()?}),
        ),
        32 => (true, json!({"player":r.u8()?})),
        33 => {
            let player = r.u8()?;
            let mut cards = vec![];
            for _ in 0..r.count()? {
                cards.push(r.u32()?);
            }
            (true, json!({"player":player,"cards":cards}))
        }
        40 => (true, json!({"player":r.u8()?})),
        41 => (true, json!({"phase":r.u16()?})),
        50 => {
            let code = r.u32()?;
            let from = r.loc()?;
            let to = r.loc()?;
            (
                true,
                json!({"code":code,"from":from,"to":to,"reason":r.u32()?}),
            )
        }
        54 | 60 | 62 => {
            let code = r.u32()?;
            (true, json!({"code":code,"location":r.loc()?}))
        }
        61 | 63 | 74 | 1 => (true, json!({})),
        53 => (
            true,
            json!({"code":r.u32()?,"player":r.u8()?,"location":r.u8()?,"sequence":r.u8()?,"previous_position":r.u8()?,"position":r.u8()?}),
        ),
        70 => {
            let code = r.u32()?;
            let loc = r.loc()?;
            let player = r.u8()?;
            let zone = r.u8()?;
            let seq = r.u32()?;
            (
                true,
                json!({"code":code,"location":loc,"player":player,"trigger_location":zone,"sequence":seq,"description":r.u64()?,"chain":r.u32()?}),
            )
        }
        71..=73 | 75 | 76 => (true, json!({"chain":r.u8()?})),
        90 => {
            let player = r.u8()?;
            let mut cards = vec![];
            for _ in 0..r.count()? {
                cards.push(json!({"code":r.u32()?,"position":r.u32()?}));
            }
            (true, json!({"player":player,"cards":cards}))
        }
        _ => {
            if let Some(p) = parse_prompt(sequence, raw)? {
                return Ok(CoreEventFrame {
                    sequence,
                    opcode,
                    raw: raw.to_vec(),
                    supported: true,
                    fields: json!({"prompt":p}),
                });
            }
            (false, json!({"unparsed":true}))
        }
    };
    if supported {
        r.end()?;
    }
    Ok(CoreEventFrame {
        sequence,
        opcode,
        raw: raw.to_vec(),
        supported,
        fields,
    })
}
