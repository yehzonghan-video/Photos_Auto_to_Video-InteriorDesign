"""AI 逐張排隊、可見的等待進度；成功結果直接送入既有前端草稿。"""
import streamlit as st
from .ai import (AIError, DEFAULT_MODEL, MODEL_CHOICES, MAX_BATCH, analyze_batch,
                 auto_import, settings, unfinished_photos)


def ai_panel(photos, state):
    with st.expander("AI 分析裝修項目（分析後直接加入標籤）", expanded=True):
        st.caption("照片會傳送至 Google Gemini API。免費方案可能使用輸入及回覆改善產品，並由人工審閱；請勿傳送敏感、機密或個人資訊。")
        st.markdown("[資料使用政策](https://ai.google.dev/gemini-api/terms) · [免費層與價格](https://ai.google.dev/gemini-api/docs/pricing)")
        try:
            secret_values = st.secrets.to_dict()
        except FileNotFoundError:
            secret_values = {}
        try:
            key, _ = settings(secret_values)
            ready = True
        except AIError as error:
            key, ready = "", False
            st.info(str(error))
        model = st.selectbox("AI 辨識模型", list(MODEL_CHOICES),
            index=list(MODEL_CHOICES).index(DEFAULT_MODEL),
            format_func=lambda value: MODEL_CHOICES[value], key="ai_model")
        locked = state.get("editor_busy", False) or state.get("pending_export") is not None
        st.caption("可選多張照片，收到一張回覆後才分析下一張；每工作階段最多20次呼叫。模型支援免費層，實際額度與可用性依帳號而異，不會自動換模型。")
        consent = st.checkbox("我了解 Google 免費方案的資料使用政策，並有權傳送所選照片", key="ai_consent")
        ids = [p.id for p in photos]
        if "ai_chosen" not in state:
            state["ai_chosen"] = ids
        elif any(ident not in ids for ident in state["ai_chosen"]):
            state["ai_chosen"] = [ident for ident in state["ai_chosen"] if ident in ids]
        chosen = st.multiselect("要分析的照片（可一次選全部）", ids,
            max_selections=MAX_BATCH, format_func=lambda ident: next(p.name for p in photos if p.id == ident), key="ai_chosen")
        force = st.checkbox("重新分析所選未完成照片（保留成功結果）", key="ai_force")
        missing = unfinished_photos(photos, model, state)
        missing_ids = {p.id for p in missing}
        selected_targets = [p for p in photos if p.id in chosen and (not force or p.id in missing_ids)]
        if force:
            st.caption(f"只重送所選未完成的 {len(selected_targets)} 張照片；已成功照片不重送。")
        primary, repair = st.columns(2)
        clicked = primary.button("AI 分析並加入標籤", disabled=not ready or not consent or not selected_targets or locked,
                                 type="primary", use_container_width=True)
        retry = repair.button(f"補查未完成照片（{len(missing)} 張）", disabled=not ready or not consent or not missing or locked,
                              use_container_width=True)
        if clicked or retry:
            targets = missing if retry else selected_targets
            bar = st.progress(0., text="照片已排入佇列…")
            table = st.empty()
            with st.status(f"正在分析 {len(targets)} 張照片", expanded=True) as waiting:
                def progress(value, message):
                    bar.progress(value, text=message)
                    waiting.update(label=message)
                    table.table([{"照片": row["name"], "狀態": row["status"], "呼叫次數": row["attempts"]}
                                 for row in state.get("ai_queue", [])])
                try:
                    with st.spinner("等待 Gemini 回覆或呼叫額度，完成後直接加入編輯器…", show_time=True):
                        reports = analyze_batch(targets, key, model, state, force=force or retry,
                            progress=progress, on_result=lambda photo, result: auto_import(state, photo, result))
                    failures = sum(not row["ok"] for row in reports)
                    waiting.update(label=f"已完成 {len(reports)-failures}/{len(reports)} 張" +
                                   ("，其餘可補查" if failures else "，標籤已送入編輯器"),
                                   state="error" if failures else "complete")
                except AIError as error:
                    waiting.update(label=str(error), state="error")
                finally:
                    bar.empty()
            st.rerun()
        names = {p.id: p.name for p in photos}
        if state.get("ai_queue"):
            with st.expander("上次分析佇列", expanded=False):
                st.caption(f"模型：{state['ai_queue'][0]['model']}")
                st.table([{"照片": row["name"], "狀態": row["status"], "呼叫次數": row["attempts"]}
                          for row in state["ai_queue"] if row["photo_id"] in names])
                diagnostics = [{"照片": names[row['photo_id']], "診斷代碼": attempt.get('request_id'),
                    "第幾次": attempt.get('attempt'), "HTTP": attempt.get('http_status'),
                    "API狀態": attempt.get('api_status'), "錯誤類型": attempt.get('error_type'),
                    "分類": attempt.get('kind', 'success'), "耗時秒": attempt.get('elapsed_seconds')}
                    for row in state['ai_queue'] if row['photo_id'] in names for attempt in row.get('attempt_logs', [])]
                if diagnostics:
                    st.table(diagnostics)
                    st.caption('HTTP空白代表未收到HTTP回覆；用診斷代碼搜尋Cloud Logs中的GEMINI_DIAGNOSTIC。')
        for report in state.get("ai_reports", []):
            if report["photo_id"] not in names:
                continue
            if report["ok"]:
                if report.get("count", 0):
                    st.success(f"{names[report['photo_id']]}：辨識到 {report['count']} 個項目，已送至編輯器自動加入；實際加入數請看編輯器提示" +
                               ("（使用快取）" if report["cached"] else ""))
                else:
                    st.info(f"{names[report['photo_id']]}：分析完成，未找到適合介紹的項目，可手動新增。")
            else:
                st.error(f"{names[report['photo_id']]}：{report['error']}")
                logs = report.get('attempt_logs', [])
                if logs:
                    last = logs[-1]
                    st.caption(f"診斷代碼：{last['request_id']} · HTTP：{last.get('http_status') or '無回覆'} · "
                               f"類型：{last.get('error_type', '未知')} · 耗時：{last.get('elapsed_seconds')}秒")
        if state.get("ai_reports"):
            st.caption("不需要另按採用。到編輯器直接刪改標籤；既有手動內容保留。低信心項目仍需你確認，裁切外的物件不加入。")
