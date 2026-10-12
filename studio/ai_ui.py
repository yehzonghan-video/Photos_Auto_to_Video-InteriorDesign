"""只有使用者明確按分析時才呼叫 API；確認表單一次匯入。"""
import streamlit as st
from .ai import (AIError, DEFAULT_MODEL, MAX_BATCH, analyze_batch,
                 content_hash, queue_import, settings)


def ai_panel(photos, state):
    with st.expander("AI 分析裝修項目（選用）", expanded=False):
        st.caption("照片會傳送至 Google Gemini API。免費方案可能使用輸入及回覆改善產品，並由人工審閱；請勿傳送敏感、機密或個人資訊。")
        st.markdown("[資料使用政策](https://ai.google.dev/gemini-api/terms) · [免費層與價格](https://ai.google.dev/gemini-api/docs/pricing)")
        try:
            secret_values = st.secrets.to_dict()
        except FileNotFoundError:
            secret_values = {}
        try:
            key, model = settings(secret_values)
            ready = True
            st.caption(f"模型：{model} · 每批最多 {MAX_BATCH} 張 · 本工作階段最多 20 次呼叫。使用未啟用帳務的免費專案金鑰；程式不切換模型或開通帳務。")
        except AIError as error:
            key, model, ready = "", DEFAULT_MODEL, False
            st.info(str(error))
        locked = state.get("editor_busy", False) or state.get("pending_export") is not None
        consent = st.checkbox("我了解 Google 免費方案的資料使用政策，並有權傳送所選照片", key="ai_consent")
        chosen = st.multiselect("要分析的照片（單張或批次）", [p.id for p in photos],
            default=[photos[0].id], max_selections=MAX_BATCH,
            format_func=lambda ident: next(p.name for p in photos if p.id == ident), key="ai_chosen")
        force = st.checkbox("重新分析（忽略此工作階段快取，會再次使用 API 額度）", key="ai_force")
        if st.button("AI 分析裝修項目", disabled=not ready or not consent or not chosen or locked):
            bar = st.progress(0., text="準備分析…")
            try:
                state["ai_reports"] = analyze_batch([p for p in photos if p.id in chosen], key, model,
                    state, force=force, progress=lambda value, text: bar.progress(value, text=text))
            except AIError as exc:
                st.error(str(exc))
            finally:
                bar.empty()
        names = {p.id: p.name for p in photos}
        for report in state.get("ai_reports", []):
            if report["photo_id"] not in names:
                continue
            if report["ok"]:
                st.success(f"{names[report['photo_id']]}：{'使用工作階段快取' if report['cached'] else '分析完成'}")
            else:
                st.error(f"{names[report['photo_id']]}：{report['error']}")
        for photo in photos:
            result = state.get("ai_results", {}).get(photo.id)
            if not result or result["content_hash"] != content_hash(photo):
                continue
            st.markdown(f"**{photo.name} · 建議清單（{result['model']}）**")
            if not result["items"]:
                st.info("未辨識到適合介紹的裝修項目，請手動新增標籤。")
                continue
            with st.form(f"ai_review_{photo.id}_{result['id']}"):
                edited = []
                for index, item in enumerate(result["items"]):
                    prefix = f"{photo.id}_{result['id']}_{index}"
                    if prefix in state.get("ai_removed", []):
                        continue
                    adopt = st.checkbox(f"採用項目 {index+1}", value=True, key=f"adopt_{prefix}")
                    name = st.text_input("標籤名稱", item["label"], max_chars=40, key=f"name_{prefix}")
                    desc = st.text_input("簡短說明", item["description"], max_chars=200, key=f"desc_{prefix}")
                    st.caption(f"{item['category']} · 信心 {item['confidence_level']} · {'待人工確認' if item['needs_review'] else '請確認後採用'}")
                    with st.expander(f"查看項目 {index+1} 建議位置"):
                        from PIL import Image, ImageOps, ImageDraw
                        from io import BytesIO
                        with Image.open(BytesIO(photo.original)) as original:
                            preview = ImageOps.exif_transpose(original).convert("RGB")
                            preview.thumbnail((640, 640))
                        draw = ImageDraw.Draw(preview)
                        y0, x0, y1, x1 = item["box_2d"]
                        draw.rectangle((x0*preview.width, y0*preview.height, x1*preview.width, y1*preview.height), outline="#ffcc00", width=3)
                        for x, y, color in ((item['anchor_x'], item['anchor_y'], '#ffcc00'),
                                             (item['suggested_label_x'], item['suggested_label_y'], '#00ffff')):
                            px, py = x*preview.width, y*preview.height
                            draw.ellipse((px-6, py-6, px+6, py+6), fill=color)
                        st.image(preview, width=320)
                        st.caption("黃框／黃點：物件範圍與定位點；藍點：文字位置。皆以完整原圖為基準，匯入時依編輯器最新構圖換算；裁切外的項目不匯入。")
                    edited.append((index, {"label": name, "description": desc}, adopt))
                    if st.form_submit_button(f"刪除建議 {index+1}", key=f"delete_{prefix}", disabled=locked):
                        state["ai_removed"] = state.get("ai_removed", []) + [prefix]
                        st.rerun()
                all_button = st.form_submit_button("全部採用", disabled=locked)
                selected_button = st.form_submit_button("套用所選標籤", disabled=locked)
                if all_button or selected_button:
                    try:
                        queue_import(state, photo, result, [(i, values) for i, values, checked in edited if all_button or checked])
                        st.success("已送出一批建議。請查看下方編輯器的匯入結果；確認後按「套用變更」，輸出前也會自動同步。")
                    except AIError as exc:
                        st.error(str(exc))
