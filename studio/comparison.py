"""前後對比複合片段：引用既有 Photo，不複製照片或另建影片管線。"""
from dataclasses import replace
import math
import uuid
from PIL import Image, ImageDraw
from .models import number, validate_label, new_label
from .rendering import crop_photo

MAX_CLIPS = 24


def crop_settings(raw):
    if not isinstance(raw, dict) or raw.get("fit", "contain") not in ("contain", "cover"):
        raise ValueError("對比照片裁切設定不正確。")
    return dict(fit=raw.get("fit", "contain"), zoom=number(raw.get("zoom", 1), 1, 3),
                crop_x=number(raw.get("crop_x", .5), 0, 1), crop_y=number(raw.get("crop_y", .5), 0, 1))


def new_comparison(before, after):
    clip = dict(id=uuid.uuid4().hex, type="comparison", before_id=before.id, after_id=after.id,
        name=(before.name+" → "+after.name)[:80], mode="switch", transition="fade", direction="ltr", duration=5.,
        before_time=2., transition_time=1., split=.5, show_line=True,
        before_crop=crop_settings(before.metadata()), after_crop=crop_settings(after.metadata()), labels=[])
    for side, text, start, end in (("before", "施工前", 0, 2), ("after", "施工後", 2, 5)):
        label=new_label(5)
        label.update(text=text,x=.06,y=.08,font_size=72,line=False,opacity=0,radius=0,
                     animation="fade" if side=="after" else "none",enter=.35 if side=="after" else 0,
                     exit=.35 if side=="before" else 0,start=start,end=end,
                     comparison_side=side,auto_timing=True,comparison_title_version=2)
        clip["labels"].append(label)
    return clip


def auto_pair(photos, existing=()):
    before=[p for p in photos if p.role=="before"]
    after=[p for p in photos if p.role=="after"]
    result=list(existing)
    seen={(c["before_id"],c["after_id"]) for c in result}
    for b,a in zip(before,after):
        if (b.id,a.id) not in seen:
            result.append(new_comparison(b,a));seen.add((b.id,a.id))
    return result, abs(len(before)-len(after))


def validate_comparisons(rows, photos):
    if not isinstance(rows,list) or len(rows)>MAX_CLIPS:
        raise ValueError("最多24組對比片段。")
    bank={p.id:p for p in photos};result=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError("對比片段格式不正確。")
        ident=row.get("id")
        if not isinstance(ident,str) or not 1<=len(ident)<=64 or ident in seen:
            raise ValueError("對比片段 ID 不正確或重複。")
        seen.add(ident)
        b,a=row.get("before_id"),row.get("after_id")
        if not isinstance(b,str) or not isinstance(a,str) or b not in bank or a not in bank or bank[b].role!="before" or bank[a].role!="after":
            raise ValueError("請指定有效的施工前與施工後照片。")
        mode,transition,direction=row.get("mode"),row.get("transition"),row.get("direction")
        if row.get("type")!="comparison" or mode not in ("switch","split","reveal") or transition not in ("cut","fade","slide") or direction not in ("ltr","rtl"):
            raise ValueError("不支援的對比動畫設定。")
        duration=number(row["duration"],1,20)
        before=number(row["before_time"],0,duration)
        change=number(row["transition_time"],0,duration)
        if before+change>duration-1/30+1e-7 or (mode=="reveal" and change<1/30-1e-7) or (mode=="switch" and transition=="cut" and change!=0):
            raise ValueError("請保留至少一影格施工後停留；揭露動畫至少一影格，直接切換轉場為0秒。")
        labels=row.get("labels",[])
        if not isinstance(labels,list) or len(labels)>12:raise ValueError("每組對比最多12個標籤。")
        labels=[validate_label(l,duration) for l in labels]
        if len({l["id"] for l in labels})!=len(labels):raise ValueError("對比標籤 ID 重複。")
        name=str(row.get("name","裝修前後對比")).strip()
        if not name or len(name)>80:raise ValueError("對比名稱需為1～80字。")
        result.append(dict(id=ident,type="comparison",before_id=b,after_id=a,name=name,mode=mode,
            transition=transition,direction=direction,duration=duration,before_time=before,transition_time=change,
            split=number(row.get("split",.5),.1,.9),show_line=bool(row.get("show_line",True)),
            before_crop=crop_settings(row["before_crop"]),after_crop=crop_settings(row["after_crop"]),labels=labels))
    if sum(c["duration"] for c in result)>120:raise ValueError("對比影片總長最多120秒。")
    return result


def comparison_pose(clip,time,width=1080):
    before,change=clip["before_time"],clip["transition_time"]
    fraction=max(0,min(1,(time-before)/change)) if change else float(time>=before)
    progress=fraction*fraction*(3-2*fraction)
    split=math.floor(width*clip["split"]+.5)
    count=math.floor(width*progress+.5)
    rtl=clip["direction"]=="rtl"
    return dict(progress=progress,split=split,reveal_left=width-count if rtl else 0,reveal_width=count,
                divider=width-count if rtl else count,
                before_x=(-count if rtl else count),after_x=(width-count if rtl else count-width))


def prepare_comparison(clip,photos):
    bank={p.id:p for p in photos};split=comparison_pose(clip,0)["split"]
    frames=[]
    for side,width in (("before",split),("after",1080-split)):
        photo=replace(bank[clip[side+"_id"]],**clip[side+"_crop"])
        frames.append(crop_photo(photo,width if clip["mode"]=="split" else 1080,1920))
    return frames


def comparison_frame(clip,frames,time):
    b,a=frames;p=comparison_pose(clip,time);mode=clip["mode"]
    frame=Image.new("RGBA",(1080,1920),"black");divider=None
    if mode=="split":
        frame.paste(b,(0,0));frame.paste(a,(p["split"],0));divider=p["split"]
    elif mode=="reveal":
        frame.paste(b,(0,0));left=p["reveal_left"];right=left+p["reveal_width"]
        if right>left:frame.paste(a.crop((left,0,right,1920)),(left,0))
        if 0<p["progress"]<1:divider=p["divider"]
    elif clip["transition"]=="slide":
        frame.alpha_composite(b,(p["before_x"],0));frame.alpha_composite(a,(p["after_x"],0))
    elif clip["transition"]=="fade":
        frame=Image.blend(b,a,p["progress"])
    else:frame=b.copy() if time<clip["before_time"] else a.copy()
    if divider is not None and clip["show_line"]:
        ImageDraw.Draw(frame).rectangle((divider-2,0,divider+1,1919),fill="#f4f0e8")
    return frame
