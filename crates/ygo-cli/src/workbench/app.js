(() => {
  const tokenKey = "ygo-workbench-token";
  const fragment = new URLSearchParams(location.hash.slice(1));
  const token = fragment.get("token") || sessionStorage.getItem(tokenKey);
  if (token) sessionStorage.setItem(tokenKey, token);
  history.replaceState(null, "", location.pathname);
  const $ = (selector) => document.querySelector(selector);
  const state = { id: null, revision: null, draft: emptyDraft(), dirty: false, saving: false, cards: new Map() };
  function emptyDraft(title = "未命名牌组") { return { schema_version: 1, kind: "deck_draft", title, main: [], extra: [], side: [] }; }
  function notice(text, error = false) { const el = $("#notice"); el.textContent = text; el.dataset.error = error ? "true" : "false"; }
  async function api(path, options = {}) {
    if (!token) throw new Error("缺少本机访问令牌。请使用启动命令打印的完整浏览器地址打开页面。");
    const { responseType = "auto", ...requestOptions } = options;
    const headers = new Headers(requestOptions.headers || {}); headers.set("Authorization", `Bearer ${token}`);
    if (requestOptions.body && !(requestOptions.body instanceof Blob)) headers.set("Content-Type", "application/json");
    const response = await fetch(path, { ...requestOptions, headers });
    const type = response.headers.get("content-type") || "";
    if (!response.ok) { let info = {}; try { info = await response.json(); } catch {} throw new Error(info.error?.code || `HTTP ${response.status}`); }
    if (responseType === "blob") return response.blob();
    return type.includes("json") ? response.json() : response.blob();
  }
  function cardLabel(id) {
    const match = state.cards.get(id);
    return match?.name ? `${match.name}（${id}）` : `卡号 ${id}（名称未核验）`;
  }
  async function checkCards(ids) {
    for (const id of new Set(ids)) {
      try {
        const result = await api(`/api/cards?q=${encodeURIComponent(id)}`);
        state.cards.set(id, result.results?.[0] || null);
        if (result.status === "unverified") $("#catalog-note").textContent = "没有配置本地卡表；卡号已保留，名称未核验。";
        else if (result.status === "unknown_card_id") state.cards.set(id, { unknown: true });
        else $("#catalog-note").textContent = `名称来自所选本地快照；中文译文未核验。`;
      } catch { state.cards.set(id, null); }
    }
  }
  function render() {
    $("#title").value = state.draft.title;
    $("#title").disabled = state.saving;
    $("#save").disabled = state.saving;
    $("#new-draft").disabled = state.saving;
    $("#refresh-list").disabled = state.saving;
    $("#import-file").disabled = state.saving;
    $("#draft-list").querySelectorAll("button").forEach((button) => { button.disabled = state.saving; });
    for (const zone of ["main", "extra", "side"]) {
      $(`[data-add=${zone}]`).disabled = state.saving;
      $(`[data-add-button=${zone}]`).disabled = state.saving;
      const container = $(`#${zone}-cards`); container.replaceChildren();
      state.draft[zone].forEach((id, index) => {
        const row = document.createElement("div"); row.className = "card-row";
        const label = document.createElement("span"); label.textContent = cardLabel(id);
        const remove = document.createElement("button"); remove.textContent = "移除"; remove.disabled = state.saving; remove.addEventListener("click", () => { state.draft[zone].splice(index, 1); changed(); });
        row.append(label, remove);
        if (state.cards.get(id)?.unknown) { const warning = document.createElement("small"); warning.textContent = "此卡号不在所选本地卡表中；草稿仍予保留。"; row.append(warning); }
        container.append(row);
      });
      $(`#${zone}-count`).textContent = `${state.draft[zone].length} 张`;
    }
    if (state.dirty) notice("有未保存更改。草稿不代表牌组已通过完整合法性或规则验证。");
  }
  async function changed() { state.dirty = true; await checkCards([...state.draft.main, ...state.draft.extra, ...state.draft.side]); render(); }
  async function refreshList() {
    const result = await api("/api/drafts"); const list = $("#draft-list"); list.replaceChildren();
    if (!result.drafts.length) { const p = document.createElement("p"); p.className="empty"; p.textContent="还没有保存的草稿。"; list.append(p); return; }
    for (const entry of result.drafts) { const button=document.createElement("button"); button.className="draft-item"; button.disabled=state.saving; button.textContent=`${entry.title} · ${entry.main_count}/${entry.extra_count}/${entry.side_count}`; button.setAttribute("aria-current",String(entry.id===state.id)); button.addEventListener("click",()=>openDraft(entry.id)); list.append(button); }
  }
  async function openDraft(id) {
    if (state.saving) return;
    try { const saved=await api(`/api/drafts/${encodeURIComponent(id)}`); state.id=saved.id; state.revision=saved.revision; state.draft=saved.draft; state.dirty=false; state.cards.clear(); await checkCards([...state.draft.main,...state.draft.extra,...state.draft.side]); render(); await refreshList(); notice("已打开保存的草稿。中文译文未核验；牌组合法性未检查。"); }
    catch(error){notice(error.message,true);}
  }
  async function saveDraft() {
    if (state.saving) return;
    state.draft.title=$("#title").value;
    state.saving=true; render();
    let saveError;
    try {
      let saved;
      if (state.id) saved=await api(`/api/drafts/${encodeURIComponent(state.id)}`,{method:"PUT",body:JSON.stringify({revision:state.revision,draft:state.draft})});
      else saved=await api("/api/drafts",{method:"POST",body:JSON.stringify({title:state.draft.title})});
      if (!state.id) { state.id=saved.id; state.revision=saved.revision; if (state.draft.main.length||state.draft.extra.length||state.draft.side.length) saved=await api(`/api/drafts/${encodeURIComponent(state.id)}`,{method:"PUT",body:JSON.stringify({revision:state.revision,draft:state.draft})}); }
      state.revision=saved.revision; state.draft=saved.draft; state.dirty=false; await refreshList();
    } catch(error) { saveError=error; }
    finally { state.saving=false; render(); }
    if (saveError) notice(saveError.message==="revision_conflict"?"保存冲突：另一标签页已更新此草稿。请重新打开后合并更改。":saveError.message,true);
    else notice("保存完成。草稿没有进行完整合法性检查。");
  }
  async function importFile(file) {
    if (state.saving) return;
    const format=file.name.toLowerCase().endsWith(".ydk")?"ydk":"json";
    try { const imported=await api(`/api/import?format=${format}`,{method:"POST",body:await file.text()}); state.id=null; state.revision=null; state.draft=imported.draft; state.dirty=true; state.cards.clear(); await checkCards([...state.draft.main,...state.draft.extra,...state.draft.side]); render(); notice("导入完成，尚未保存为工作区草稿。中文译文未核验。"); }
    catch(error){notice(error.message,true);}
  }
  async function exportDraft(format) {
    state.draft.title=$("#title").value;
    try { const blob=await api(`/api/export?format=${format}`,{method:"POST",body:JSON.stringify(state.draft),responseType:"blob"}); const link=document.createElement("a"); link.href=URL.createObjectURL(blob); link.download=`deck.${format}`; link.click(); setTimeout(()=>URL.revokeObjectURL(link.href),1000); }
    catch(error){notice(error.message,true);}
  }
  $("#new-draft").addEventListener("click",async()=>{if(state.saving)return;state.id=null;state.revision=null;state.draft=emptyDraft();state.cards.clear();state.dirty=false;render();await refreshList();notice("新建空白草稿。中文译文未核验；牌组合法性未检查。");});
  $("#save").addEventListener("click",saveDraft); $("#refresh-list").addEventListener("click",()=>refreshList().catch(e=>notice(e.message,true)));
  $("#title").addEventListener("input",()=>{if(state.saving)return;state.draft.title=$("#title").value;state.dirty=true;});
  for(const zone of ["main","extra","side"]) $("[data-add-button="+zone+"]").addEventListener("click",async()=>{if(state.saving)return;const input=$(`[data-add=${zone}]`);const id=Number(input.value);if(!Number.isInteger(id)||id<=0||id>4294967295){notice("请输入非零 u32 卡号。",true);return;}state.draft[zone].push(id);input.value="";await changed();});
  $("#import-file").addEventListener("change",event=>{const file=event.target.files[0];if(file)importFile(file);event.target.value="";});
  $("#export-json").addEventListener("click",()=>exportDraft("json")); $("#export-ydk").addEventListener("click",()=>exportDraft("ydk"));
  $("#search-cards").addEventListener("click",async()=>{try{const result=await api(`/api/cards?q=${encodeURIComponent($("#card-query").value)}`);const box=$("#card-results");box.replaceChildren();if(result.status==="unverified"){$("#catalog-note").textContent="没有配置本地卡表；卡号检索仍可手动输入，名称未核验。";return;}for(const card of result.results){const row=document.createElement("div");row.className="card-result";row.textContent=`${card.name}（${card.id}）· ${card.source} · 中文未核验`;box.append(row);}if(result.status==="unknown_card_id"){$("#catalog-note").textContent="该卡号不在所选本地卡表中；可以仍将卡号加入草稿。";}}catch(error){notice(error.message,true);}});
  render();
  if(!token)notice("请使用启动命令打印的完整浏览器地址打开工作台。",true);else refreshList().catch(error=>notice(error.message,true));
})();
